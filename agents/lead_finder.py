"""
Agent 1: Lead Finder
Discovers companies with document-heavy operations using DuckDuckGo search.
Targets international markets: US, UK, Europe, Australia, Canada, and more.
No API key required for DuckDuckGo (completely free).
"""

import time
import logging
import re
from urllib.parse import urlparse
from utils.scraper import duckduckgo_search, google_search
from utils.database import save_lead
from config.settings import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# International region definitions
# Each entry: (location label, city/country hint for query, TLD hint)
# ---------------------------------------------------------------------------
REGIONS = [
    # United States
    ("New York",       "New York NY",      "us"),
    ("Los Angeles",    "Los Angeles CA",   "us"),
    ("Chicago",        "Chicago IL",       "us"),
    ("Houston",        "Houston TX",       "us"),
    ("San Francisco",  "San Francisco CA", "us"),
    ("Boston",         "Boston MA",        "us"),
    ("Dallas",         "Dallas TX",        "us"),
    ("Atlanta",        "Atlanta GA",       "us"),
    # United Kingdom
    ("London",         "London UK",        "uk"),
    ("Manchester",     "Manchester UK",    "uk"),
    ("Birmingham",     "Birmingham UK",    "uk"),
    ("Edinburgh",      "Edinburgh Scotland","uk"),
    # Australia
    ("Sydney",         "Sydney Australia",    "au"),
    ("Melbourne",      "Melbourne Australia", "au"),
    ("Brisbane",       "Brisbane Australia",  "au"),
    ("Perth",          "Perth Australia",     "au"),
    # Canada
    ("Toronto",        "Toronto Canada",    "ca"),
    ("Vancouver",      "Vancouver Canada",  "ca"),
    ("Montreal",       "Montreal Canada",   "ca"),
    # Germany
    ("Berlin",         "Berlin Germany",    "de"),
    ("Munich",         "Munich Germany",    "de"),
    ("Frankfurt",      "Frankfurt Germany", "de"),
    # Netherlands
    ("Amsterdam",      "Amsterdam Netherlands", "nl"),
    # France
    ("Paris",          "Paris France",      "fr"),
    # Switzerland
    ("Zurich",         "Zurich Switzerland","ch"),
    # Sweden
    ("Stockholm",      "Stockholm Sweden",  "se"),
    # Singapore (APAC hub)
    ("Singapore",      "Singapore",         "sg"),
    # UAE (Middle East hub)
    ("Dubai",          "Dubai UAE",         "ae"),
    # New Zealand
    ("Auckland",       "Auckland New Zealand", "nz"),
    # Ireland
    ("Dublin",         "Dublin Ireland",    "ie"),
]

# ---------------------------------------------------------------------------
# Industry templates – {location} is substituted per region
# Format: (query_template, industry_label)
# ---------------------------------------------------------------------------
INDUSTRY_TEMPLATES = [
    # Law Firms
    ("law firm legal services {location}",                       "Law Firm"),
    ("corporate law firm contracts compliance {location}",       "Law Firm"),
    ("litigation attorney firm {location}",                      "Law Firm"),
    ("commercial solicitors legal advisory {location}",          "Law Firm"),  # UK/AU term
    # Accounting
    ("accounting firm CPA tax advisory {location}",              "Accounting Firm"),
    ("chartered accountants audit financial reports {location}", "Accounting Firm"),
    ("tax consulting firm financial compliance {location}",      "Accounting Firm"),
    # Consulting
    ("management consulting firm strategy advisory {location}",  "Consulting Firm"),
    ("business process consulting SOPs documentation {location}","Consulting Firm"),
    ("strategy consulting firm operations {location}",           "Consulting Firm"),
    # Insurance
    ("insurance company underwriting policies {location}",       "Insurance"),
    ("commercial insurance broker risk management {location}",   "Insurance"),
    ("insurance advisory claims compliance {location}",          "Insurance"),
    # HR Agencies
    ("HR staffing agency recruitment workforce {location}",      "HR Agency"),
    ("human resources consulting employee policies {location}",  "HR Agency"),
    ("talent acquisition firm recruitment {location}",           "HR Agency"),
    # Healthcare
    ("private healthcare clinic medical records {location}",     "Healthcare"),
    ("hospital health system clinical documentation {location}", "Healthcare"),
    ("medical practice compliance documentation {location}",     "Healthcare"),
    # Manufacturing
    ("manufacturing company industrial SOPs manuals {location}", "Manufacturing"),
    ("contract manufacturer quality compliance {location}",      "Manufacturing"),
    ("industrial engineering firm technical documentation {location}", "Manufacturing"),
    # Engineering
    ("engineering consulting firm technical reports {location}", "Engineering Firm"),
    ("civil engineering infrastructure projects {location}",     "Engineering Firm"),
    ("structural engineering firm project documentation {location}", "Engineering Firm"),
    # Compliance / Regulatory
    ("compliance consulting regulatory affairs {location}",      "Compliance"),
    ("regulatory compliance policy management firm {location}",  "Compliance"),
    ("risk and compliance advisory services {location}",         "Compliance"),
    # Research
    ("research institute academic publications {location}",      "Research"),
    ("market research firm reports analytics {location}",        "Research"),
    ("think tank policy research organization {location}",       "Research"),
]

# ---------------------------------------------------------------------------
# Additional global queries (not location-specific, catch large firms)
# ---------------------------------------------------------------------------
GLOBAL_QUERIES = [
    ("international law firm global contracts compliance",           "Law Firm"),
    ("big four accounting firm global audit",                        "Accounting Firm"),
    ("global management consulting firm McKinsey Deloitte",          "Consulting Firm"),
    ("multinational insurance company global underwriting",          "Insurance"),
    ("global HR consulting firm workforce management",               "HR Agency"),
    ("international healthcare group clinical documentation",        "Healthcare"),
    ("global engineering consultancy technical documentation",       "Engineering Firm"),
    ("global compliance regulatory affairs pharmaceutical",          "Compliance"),
    ("international research institute publications knowledge",      "Research"),
    ("global manufacturing conglomerate technical manuals SOPs",     "Manufacturing"),
]

# Skip these domains – aggregators, job boards, social media, directories
SKIP_DOMAINS = {
    "linkedin.com", "indeed.com", "glassdoor.com", "facebook.com",
    "twitter.com", "x.com", "instagram.com", "youtube.com", "wikipedia.org",
    "yelp.com", "bbb.org", "yellowpages.com", "google.com", "bing.com",
    "reddit.com", "quora.com", "forbes.com", "bloomberg.com", "reuters.com",
    "businesswire.com", "prnewswire.com", "crunchbase.com", "clutch.co",
    "g2.com", "capterra.com", "trustpilot.com", "amazon.com", "github.com",
    "lawsociety.org.uk", "aicpa.org", "icaew.com", "legalservices.gov",
    "legislation.gov.uk", "lawcom.gov.uk", "sec.gov", "irs.gov",
    "companieshouse.gov.uk", "asic.gov.au", "hhs.gov",
}


def _is_valid_company_url(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "").split(".")[0]
    full_domain = parsed.netloc.replace("www.", "")

    if full_domain in SKIP_DOMAINS:
        return False
    if any(skip in full_domain for skip in SKIP_DOMAINS):
        return False
    # Must have a proper domain
    if not parsed.netloc or "." not in parsed.netloc:
        return False
    return True


def _extract_company_name(title: str, url: str, snippet: str) -> str:
    """Best-effort company name from search result title."""
    # Title often has pattern: "Company Name - Services | Company"
    parts = re.split(r"[|\-–—]", title)
    if parts:
        name = parts[0].strip()
        # Remove common suffixes
        name = re.sub(
            r"\b(LLC|LLP|Inc\.?|Ltd\.?|Corp\.?|Co\.?|Group|Associates|Partners|Services|Solutions)\b",
            "",
            name,
            flags=re.IGNORECASE,
        ).strip().rstrip(",.")
        if len(name) > 3:
            return name

    # Fall back to domain name
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "").split(".")[0]
    return domain.replace("-", " ").replace("_", " ").title()


def _normalize_url(url: str) -> str:
    """Return base URL (scheme + domain only)."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _build_query_list(
    regions: list = None,
    templates: list = None,
    include_global: bool = True,
) -> list[tuple[str, str]]:
    """
    Build the full query list by combining regions × industry templates.

    Args:
        regions:        List of (label, location_hint, tld) tuples. Defaults to REGIONS.
        templates:      List of (query_template, industry) tuples. Defaults to INDUSTRY_TEMPLATES.
        include_global: Whether to append GLOBAL_QUERIES.

    Returns:
        Shuffled list of (query_string, industry) tuples ready for searching.
    """
    import random

    region_list = regions or REGIONS
    template_list = templates or INDUSTRY_TEMPLATES
    queries = []

    for region_label, location_hint, _tld in region_list:
        for template, industry in template_list:
            query = template.format(location=location_hint)
            queries.append((query, industry, region_label))

    if include_global:
        for query, industry in GLOBAL_QUERIES:
            queries.append((query, industry, "Global"))

    # Shuffle so we get geographic diversity on every run, not always US-first
    random.shuffle(queries)
    return queries


def _search(query_text: str, max_results: int = 10) -> list[dict]:
    """Try Google Custom Search first; fall back to DuckDuckGo."""
    results = google_search(query_text, max_results=max_results)
    if not results:
        results = duckduckgo_search(query_text, max_results=max_results)
    return results


def run(
    target: int = None,
    regions: list = None,
    templates: list = None,
    custom_queries: list = None,
) -> list[dict]:
    """
    Run the Lead Finder agent across international markets.

    Args:
        target:         Max leads to save this run (default: DAILY_TARGET × 3).
        regions:        Override default REGIONS list.
        templates:      Override default INDUSTRY_TEMPLATES list.
        custom_queries: Fully custom [(query, industry)] list (skips template builder).

    Returns:
        List of saved lead dicts: id, company_name, website, industry, region.
    """
    max_leads = target or (settings.DAILY_TARGET * 3)

    if custom_queries:
        query_list = [(q, ind, "Custom") for q, ind in custom_queries]
    else:
        query_list = _build_query_list(regions, templates)

    saved_leads: list[dict] = []
    seen_domains: set[str] = set()

    logger.info(
        "Lead Finder starting – target: %d leads | %d queries across %d regions",
        max_leads,
        len(query_list),
        len(set(r for _, _, r in query_list)),
    )

    for query_text, industry, region in query_list:
        if len(saved_leads) >= max_leads:
            break

        logger.info("[%s] Searching: %s", region, query_text)
        results = _search(query_text, max_results=10)

        for result in results:
            if len(saved_leads) >= max_leads:
                break

            url = result.get("url", "")
            title = result.get("title", "")
            snippet = result.get("snippet", "")

            if not _is_valid_company_url(url):
                continue

            base_url = _normalize_url(url)
            domain = urlparse(base_url).netloc.replace("www.", "")

            if domain in seen_domains:
                continue
            seen_domains.add(domain)

            company_name = _extract_company_name(title, url, snippet)

            lead_id = save_lead(
                company_name=company_name,
                website=base_url,
                industry=industry,
                region=region,
            )

            if lead_id:
                lead = {
                    "id": lead_id,
                    "company_name": company_name,
                    "website": base_url,
                    "industry": industry,
                    "region": region,
                }
                saved_leads.append(lead)
                logger.info(
                    "Saved lead #%d: %s (%s, %s)",
                    lead_id, company_name, industry, region,
                )
            else:
                logger.debug("Duplicate skipped: %s", company_name)

        time.sleep(2)  # Respectful delay between searches

    logger.info("Lead Finder done – saved %d new leads", len(saved_leads))
    return saved_leads
