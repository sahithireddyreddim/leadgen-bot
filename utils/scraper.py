import requests
from bs4 import BeautifulSoup
import time
import logging
from urllib.parse import urljoin, urlparse
from typing import Optional
from config.settings import settings

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def fetch_page(url: str, timeout: int = None) -> Optional[str]:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        resp = requests.get(
            url,
            headers=HEADERS,
            timeout=timeout or settings.REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        logger.debug("Failed to fetch %s: %s", url, e)
        return None


def extract_text(html: str, max_chars: int = 5000) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())
    return text[:max_chars]


def extract_company_info(url: str) -> dict:
    """Extract key info from a company homepage."""
    html = fetch_page(url)
    if not html:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string.strip() if soup.title else ""

    # Meta description
    meta_desc = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta:
        meta_desc = meta.get("content", "")

    # Main body text
    body_text = extract_text(html, max_chars=4000)

    # Try to get About page content too
    about_text = _fetch_about_page(url, soup)

    return {
        "title": title,
        "meta_description": meta_desc,
        "body_text": body_text,
        "about_text": about_text,
        "url": url,
    }


def _fetch_about_page(base_url: str, soup: BeautifulSoup) -> str:
    about_keywords = ["about", "about-us", "about_us", "company", "who-we-are"]
    links = soup.find_all("a", href=True)
    for link in links:
        href = link["href"].lower()
        if any(kw in href for kw in about_keywords):
            about_url = urljoin(base_url, link["href"])
            parsed = urlparse(about_url)
            base_parsed = urlparse(base_url)
            if parsed.netloc == base_parsed.netloc:
                time.sleep(settings.SCRAPE_DELAY)
                html = fetch_page(about_url)
                if html:
                    return extract_text(html, max_chars=2000)
    return ""


def extract_contact_emails_from_website(url: str) -> list[str]:
    """Scrape homepage and contact page for email addresses."""
    import re

    emails = set()
    email_pattern = re.compile(
        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
    )

    pages_to_check = [url]
    html = fetch_page(url)
    if html:
        soup = BeautifulSoup(html, "html.parser")
        contact_keywords = ["contact", "contact-us", "contact_us", "reach-us", "get-in-touch"]
        for link in soup.find_all("a", href=True):
            href = link["href"].lower()
            if any(kw in href for kw in contact_keywords):
                contact_url = urljoin(url, link["href"])
                if urlparse(contact_url).netloc == urlparse(url).netloc:
                    pages_to_check.append(contact_url)
                    break

    for page_url in pages_to_check[:2]:
        page_html = fetch_page(page_url)
        if page_html:
            found = email_pattern.findall(page_html)
            for e in found:
                if not any(skip in e.lower() for skip in ["example.com", "domain.com", "email.com", "yoursite"]):
                    emails.add(e.lower())
        time.sleep(settings.SCRAPE_DELAY)

    return list(emails)


def duckduckgo_search(query: str, max_results: int = 10) -> list[dict]:
    """Search DuckDuckGo – no API key required."""
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
        return results
    except Exception as e:
        logger.error("DuckDuckGo search failed: %s", e)
        return []


def google_search(query: str, max_results: int = 10) -> list[dict]:
    """Google Custom Search JSON API (100 free/day)."""
    from config.settings import settings

    if not settings.GOOGLE_API_KEY or not settings.GOOGLE_CSE_ID:
        return []
    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": settings.GOOGLE_API_KEY,
            "cx": settings.GOOGLE_CSE_ID,
            "q": query,
            "num": min(max_results, 10),
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
            for item in data.get("items", [])
        ]
    except Exception as e:
        logger.error("Google search failed: %s", e)
        return []
