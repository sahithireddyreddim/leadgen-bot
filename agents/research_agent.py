"""
Agent 2: Research Agent
Scrapes company websites and uses Groq LLM (free tier) to analyze
document workflows, challenges, and fit score.
"""

import json
import time
import logging
from typing import Optional
from groq import Groq
from utils.scraper import extract_company_info
from utils.database import save_research, get_leads_for_research
from config.settings import settings

logger = logging.getLogger(__name__)

_groq_client: Optional[Groq] = None


def _get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=settings.GROQ_API_KEY)
    return _groq_client


RESEARCH_PROMPT = """You are a B2B sales research analyst specializing in international markets (US, UK, Europe, Australia, Canada, Singapore, UAE). Analyze this company and determine if they are a good fit for an AI document intelligence platform.

The platform provides:
- AI-powered document chat (ask questions across multiple documents)
- Multi-document querying with source citations
- Support for PDF, DOCX, TXT, and scanned documents
- Secure user-specific document access
- Admin dashboard and user management
- Context-aware conversations and voice input
- PDF export and document filtering

Company Information:
Name: {company_name}
Website: {website}
Industry: {industry}
Region/Location: {region}
Website Title: {title}
Meta Description: {meta_description}
Website Content: {body_text}
About Page: {about_text}

Based only on the information provided above, produce a JSON response with this exact structure:
{{
  "company_summary": "2-3 sentence summary of what this company does and where it operates",
  "country": "Inferred country or region (e.g. United States, United Kingdom, Australia, Germany)",
  "document_workflows": ["list of document-heavy workflows this company likely has, 3-6 items"],
  "potential_challenges": ["list of knowledge/document management challenges they face, 2-4 items"],
  "use_cases": ["specific ways the AI document platform could help them, 3-5 items"],
  "fit_score": 75
}}

Fit Score Guidelines (0-100):
- 80-100: Highly document-intensive, strong compliance/legal/research needs
- 60-79: Moderate document needs, clear use cases exist
- 40-59: Some document use, unclear direct benefit
- 0-39: Unlikely to benefit from the platform

Rules:
- Only use information from the company content provided
- Do not fabricate specific facts about the company
- Be specific and practical in use cases
- Return ONLY valid JSON, no extra text

JSON response:"""


def _analyze_with_llm(company_data: dict) -> Optional[dict]:
    client = _get_groq_client()
    prompt = RESEARCH_PROMPT.format(
        company_name=company_data.get("company_name", ""),
        website=company_data.get("website", ""),
        industry=company_data.get("industry", ""),
        region=company_data.get("region", "Unknown"),
        title=company_data.get("title", ""),
        meta_description=company_data.get("meta_description", ""),
        body_text=company_data.get("body_text", "")[:3000],
        about_text=company_data.get("about_text", "")[:1500],
    )

    try:
        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown code blocks if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip().rstrip("```").strip()

        result = json.loads(raw)
        # Validate and clamp fit_score
        result["fit_score"] = max(0, min(100, int(result.get("fit_score", 0))))
        return result

    except json.JSONDecodeError as e:
        logger.error("LLM returned invalid JSON for %s: %s", company_data.get("company_name"), e)
        return None
    except Exception as e:
        logger.error("LLM analysis failed for %s: %s", company_data.get("company_name"), e)
        return None


def _fallback_analysis(company_data: dict) -> dict:
    """Rule-based fallback when LLM is unavailable."""
    industry = company_data.get("industry", "").lower()
    body = (company_data.get("body_text", "") + company_data.get("about_text", "")).lower()

    score = 50
    workflows = []
    challenges = []
    use_cases = []

    high_score_industries = ["law", "accounting", "compliance", "insurance", "research"]
    med_score_industries = ["consulting", "hr", "healthcare", "engineering", "manufacturing"]

    if any(kw in industry for kw in high_score_industries):
        score = 72
    elif any(kw in industry for kw in med_score_industries):
        score = 65

    doc_keywords = {
        "contracts": 5, "policies": 5, "compliance": 5, "reports": 4,
        "documentation": 4, "manuals": 4, "procedures": 4, "sops": 5,
        "regulations": 5, "audits": 5, "records": 4,
    }
    for kw, pts in doc_keywords.items():
        if kw in body:
            score = min(90, score + pts)
            workflows.append(kw.capitalize())

    if not workflows:
        workflows = ["Internal documentation", "Client reports", "Compliance records"]

    challenges = [
        "Finding information across multiple documents quickly",
        "Maintaining consistent knowledge across team members",
        "Keeping document workflows efficient as volume grows",
    ]

    use_cases = [
        f"Allow {company_data.get('company_name', 'team')} staff to query internal documents in plain English",
        "Reduce time spent searching through compliance and policy documents",
        "Enable secure, role-based document access across departments",
    ]

    return {
        "company_summary": f"{company_data.get('company_name', 'This company')} is a {company_data.get('industry', 'company')} that operates in a document-intensive environment.",
        "country": company_data.get("region", ""),
        "document_workflows": list(set(workflows))[:6],
        "potential_challenges": challenges,
        "use_cases": use_cases,
        "fit_score": score,
    }


def research_company(lead: dict) -> Optional[dict]:
    """
    Scrape and analyze a single company.

    Args:
        lead: dict with id, company_name, website, industry

    Returns:
        Research result dict, or None if scraping failed.
    """
    company_name = lead["company_name"]
    website = lead["website"]
    logger.info("Researching: %s (%s)", company_name, website)

    # Scrape website
    scraped = extract_company_info(website)
    if not scraped:
        logger.warning("Could not scrape %s – skipping", website)
        return None

    company_data = {**lead, **scraped}

    # Analyze with LLM (Groq)
    if settings.GROQ_API_KEY:
        result = _analyze_with_llm(company_data)
    else:
        logger.warning("GROQ_API_KEY not set – using rule-based fallback")
        result = None

    if result is None:
        result = _fallback_analysis(company_data)

    fit_score = result.get("fit_score", 0)
    action = "QUALIFIED" if fit_score >= settings.MIN_FIT_SCORE else "REJECTED"
    logger.info(
        "%s %s (fit score: %d/100)",
        action, company_name, fit_score,
    )

    return result


def run(leads: list[dict] = None) -> list[dict]:
    """
    Research all pending leads from the database.

    Args:
        leads: Optional list of leads to research. If None, fetches from DB.

    Returns:
        List of research result dicts for qualified companies (score >= MIN_FIT_SCORE).
    """
    if leads is None:
        leads = get_leads_for_research(limit=settings.DAILY_TARGET * 2)

    if not leads:
        logger.info("No leads to research")
        return []

    logger.info("Research Agent starting – %d leads to analyze", len(leads))
    qualified = []

    for lead in leads:
        result = research_company(lead)
        if result is None:
            continue

        save_research(lead["id"], result)

        if result.get("fit_score", 0) >= settings.MIN_FIT_SCORE:
            qualified.append({**lead, **result})

        # Respectful delay between scraping
        time.sleep(settings.SCRAPE_DELAY)

    logger.info(
        "Research Agent done – %d/%d qualified", len(qualified), len(leads)
    )
    return qualified
