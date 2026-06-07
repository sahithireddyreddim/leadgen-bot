import requests
import re
import logging
from urllib.parse import urlparse
from typing import Optional
from config.settings import settings

logger = logging.getLogger(__name__)

COMMON_PATTERNS = [
    "info@{domain}",
    "contact@{domain}",
    "hello@{domain}",
    "team@{domain}",
    "admin@{domain}",
    "office@{domain}",
    "enquiries@{domain}",
]


def get_domain(website: str) -> str:
    if not website.startswith(("http://", "https://")):
        website = "https://" + website
    parsed = urlparse(website)
    domain = parsed.netloc.replace("www.", "")
    return domain


def hunter_find_email(domain: str, company_name: str) -> Optional[str]:
    """Hunter.io domain search – 25 free searches/month."""
    if not settings.HUNTER_API_KEY:
        return None
    try:
        resp = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={
                "domain": domain,
                "api_key": settings.HUNTER_API_KEY,
                "limit": 5,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        emails = data.get("data", {}).get("emails", [])
        if emails:
            # Prefer generic contact emails over personal ones
            for e in emails:
                email_val = e.get("value", "")
                if any(kw in email_val for kw in ["info", "contact", "hello", "admin"]):
                    return email_val
            return emails[0].get("value")
    except Exception as e:
        logger.debug("Hunter.io failed for %s: %s", domain, e)
    return None


def verify_email_exists(email: str) -> bool:
    """Quick MX record check – doesn't send any email."""
    import dns.resolver
    domain = email.split("@")[1]
    try:
        dns.resolver.resolve(domain, "MX")
        return True
    except Exception:
        return False


def find_contact_email(website: str, company_name: str, scraped_emails: list[str] = None) -> Optional[str]:
    """
    Try multiple strategies to find a valid contact email.
    Priority: scraped emails > Hunter.io > common patterns
    """
    domain = get_domain(website)

    # 1. Use emails already scraped from the website
    if scraped_emails:
        for email in scraped_emails:
            if email.endswith(domain) or email.endswith("." + domain):
                logger.info("Found scraped email for %s: %s", company_name, email)
                return email
        # Accept any non-generic email provider
        for email in scraped_emails:
            if not any(
                provider in email
                for provider in ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com"]
            ):
                return email

    # 2. Hunter.io API
    hunter_email = hunter_find_email(domain, company_name)
    if hunter_email:
        logger.info("Hunter.io found email for %s: %s", company_name, hunter_email)
        return hunter_email

    # 3. Common pattern guessing (with MX verification)
    for pattern in COMMON_PATTERNS:
        email = pattern.format(domain=domain)
        try:
            if verify_email_exists(email):
                logger.info("Pattern email found for %s: %s", company_name, email)
                return email
        except Exception:
            pass

    # 4. Return the most likely pattern without verification
    return f"info@{domain}"
