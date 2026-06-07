"""
Agent 3: Outreach Agent
Generates personalized outreach emails via Groq LLM and sends them
using the configured email provider (Gmail / Brevo / Resend).
"""

import json
import time
import logging
from typing import Optional
from groq import Groq
from utils.scraper import extract_contact_emails_from_website
from utils.email_finder import find_contact_email
from utils.email_sender import send_email
from utils.database import save_outreach, mark_email_sent, get_leads_for_outreach
from config.settings import settings

logger = logging.getLogger(__name__)

_groq_client: Optional[Groq] = None


def _get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=settings.GROQ_API_KEY)
    return _groq_client


EMAIL_PROMPT = """You are a B2B sales development representative writing cold outreach emails for a software company. You write for an international audience – the recipient may be in the US, UK, Australia, Europe, Canada, Singapore, or elsewhere.

Product: An AI document intelligence platform that lets teams chat with their documents, search across multiple files at once, and surface information instantly – with source citations and secure role-based access.

Company to contact:
Name: {company_name}
Industry: {industry}
Country/Region: {country}
Summary: {company_summary}
Document workflows they handle: {document_workflows}
Challenges they likely face: {potential_challenges}
How our platform could help: {use_cases}

Write a personalized cold outreach email. Requirements:
- Subject: under 6 words, specific to this company/industry (no generic phrases like "Quick Question")
- Body: under 120 words
- Tone: professional but conversational, human-sounding. Match the regional communication style
  (e.g. UK/AU: slightly more formal; US: direct; Germany/Netherlands: concise and factual)
- Mention a specific pain point from their workflow
- Reference the AI platform naturally – focus on business outcomes, not features
- No hype, no exaggerated claims
- End with one simple, low-commitment question inviting them to see a demo.
  Examples: "Would it be worth a quick demo?" / "Happy to share a short demo if that'd be useful?"
  The tone should be: "let me know if you'd like to see it in action and I'll send one over" – no pressure, no calendar link, no hard sell
- Do NOT use the words "transformative", "revolutionize", "game-changer", or "cutting-edge"
- If UK/AU/EU company: use British spelling (e.g. "organisation", "recognise") where appropriate
- Sign off with: {sender_name}

Return ONLY valid JSON in this exact format:
{{
  "email_subject": "Subject here",
  "email_body": "Full email body here including greeting and sign-off"
}}

JSON response:"""


def _generate_email_llm(lead: dict) -> Optional[dict]:
    client = _get_groq_client()

    workflows = lead.get("document_workflows", [])
    if isinstance(workflows, str):
        try:
            workflows = json.loads(workflows)
        except Exception:
            workflows = [workflows]

    challenges = lead.get("potential_challenges", [])
    if isinstance(challenges, str):
        try:
            challenges = json.loads(challenges)
        except Exception:
            challenges = [challenges]

    use_cases = lead.get("use_cases", [])
    if isinstance(use_cases, str):
        try:
            use_cases = json.loads(use_cases)
        except Exception:
            use_cases = [use_cases]

    prompt = EMAIL_PROMPT.format(
        company_name=lead["company_name"],
        industry=lead.get("industry", ""),
        country=lead.get("country", lead.get("region", "Unknown")),
        company_summary=lead.get("company_summary", ""),
        document_workflows=", ".join(workflows[:4]) if workflows else "various documents",
        potential_challenges=", ".join(challenges[:3]) if challenges else "document management",
        use_cases=", ".join(use_cases[:3]) if use_cases else "faster document search",
        sender_name=settings.SENDER_NAME,
    )

    try:
        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=400,
        )
        raw = response.choices[0].message.content.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip().rstrip("```").strip()

        result = json.loads(raw)

        # Enforce limits
        subject_words = result.get("email_subject", "").split()
        if len(subject_words) > 8:
            result["email_subject"] = " ".join(subject_words[:6])

        return result

    except json.JSONDecodeError as e:
        logger.error("LLM returned invalid JSON for %s: %s", lead["company_name"], e)
        return None
    except Exception as e:
        logger.error("Email generation failed for %s: %s", lead["company_name"], e)
        return None


def _fallback_email(lead: dict) -> dict:
    """Rule-based fallback email when LLM is unavailable."""
    company = lead["company_name"]
    industry = lead.get("industry", "your industry")

    workflows = lead.get("document_workflows", [])
    if isinstance(workflows, str):
        try:
            workflows = json.loads(workflows)
        except Exception:
            workflows = []

    doc_type = workflows[0].lower() if workflows else "documents"

    subject = f"Managing {doc_type} at {company}"
    if len(subject.split()) > 6:
        subject = f"Document workflows at {company}"

    body = f"""Hi {company} team,

I came across {company} and noticed that {industry} teams often spend significant time searching through {doc_type} to find the right information.

We've built an AI platform that lets teams ask questions directly to their documents and get instant answers with source references – across contracts, reports, and internal files.

I'd be happy to share a short demo if it looks like a fit.

Would it be worth a quick look?

Best regards,
{settings.SENDER_NAME}"""

    return {"email_subject": subject, "email_body": body}


def process_lead(lead: dict) -> Optional[dict]:
    """
    Generate email content and find contact email for one lead.
    Marks the lead as 'emailed' immediately on outreach record creation
    so re-clicking buttons never sends a duplicate.
    """
    company_name = lead["company_name"]
    website = lead["website"]

    logger.info("Generating outreach for: %s", company_name)

    # Generate email content
    if settings.GROQ_API_KEY:
        email_content = _generate_email_llm(lead)
    else:
        email_content = None

    if email_content is None:
        email_content = _fallback_email(lead)

    subject = email_content.get("email_subject", "")
    body = email_content.get("email_body", "")

    # Find contact email
    scraped_emails = extract_contact_emails_from_website(website)
    contact_email = find_contact_email(website, company_name, scraped_emails)

    if not contact_email:
        logger.warning("No email found for %s – skipping", company_name)
        return None

    # Save outreach record AND immediately mark lead as emailed
    # This prevents duplicate sends if the button is clicked again before emails go out
    outreach_id = save_outreach(
        lead_id=lead["id"],
        contact_email=contact_email,
        subject=subject,
        body=body,
    )

    return {
        "outreach_id": outreach_id,
        "lead_id": lead["id"],
        "company_name": company_name,
        "contact_email": contact_email,
        "email_subject": subject,
        "email_body": body,
    }


def run(leads: list[dict] = None, dry_run: bool = False) -> dict:
    """
    Run the Outreach Agent.

    Args:
        leads: Optional list of qualified leads. If None, fetches from DB.
        dry_run: If True, generate emails but do not actually send them.

    Returns:
        Summary dict with sent, failed, skipped counts.
    """
    if leads is None:
        leads = get_leads_for_outreach(limit=settings.DAILY_TARGET)

    if not leads:
        logger.info("No qualified leads ready for outreach")
        return {"sent": 0, "failed": 0, "skipped": 0, "emails": []}

    logger.info(
        "Outreach Agent starting – %d leads, dry_run=%s", len(leads), dry_run
    )

    sent = 0
    failed = 0
    skipped = 0
    emails = []

    for lead in leads:
        if sent >= settings.DAILY_TARGET:
            logger.info("Daily target (%d) reached – stopping", settings.DAILY_TARGET)
            break

        outreach = process_lead(lead)
        if outreach is None:
            skipped += 1
            continue

        if dry_run:
            logger.info(
                "[DRY RUN] Would send to %s (%s): %s",
                outreach["contact_email"], outreach["company_name"], outreach["email_subject"],
            )
            # Mark lead as emailed even in dry run so re-clicking doesn't duplicate
            mark_email_sent(outreach["outreach_id"], success=False, error="dry_run")
            emails.append(outreach)
            sent += 1
            continue

        success, error = send_email(
            to_email=outreach["contact_email"],
            subject=outreach["email_subject"],
            body=outreach["email_body"],
        )

        mark_email_sent(outreach["outreach_id"], success, error)
        outreach["sent"] = success
        outreach["error"] = error
        emails.append(outreach)

        if success:
            sent += 1
            logger.info(
                "Sent email to %s (%s)",
                outreach["contact_email"],
                lead["company_name"],
            )
        else:
            failed += 1
            logger.error(
                "Failed to send to %s: %s",
                outreach["contact_email"],
                error,
            )

        time.sleep(1)  # Brief pause between leads

    logger.info(
        "Outreach Agent done – sent: %d, failed: %d, skipped: %d",
        sent, failed, skipped,
    )
    return {"sent": sent, "failed": failed, "skipped": skipped, "emails": emails}
