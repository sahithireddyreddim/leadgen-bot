"""
Agent 4: Follow-Up Agent
Sends a 3-email follow-up sequence to leads that haven't replied.

Sequence (configurable via env vars):
  Email 1 (initial outreach) – Day 0
  Follow-up 1               – Day 3  (gentle bump, different angle)
  Follow-up 2               – Day 7  (short, value-focused)
  Follow-up 3               – Day 14 (final, low-pressure close)

Each follow-up has a distinct tone so it doesn't feel like spam.
"""

import json
import time
import logging
from typing import Optional
from groq import Groq
from utils.email_sender import send_email
from utils.database import get_leads_for_follow_up, mark_follow_up_sent
from config.settings import settings

logger = logging.getLogger(__name__)

_groq_client: Optional[Groq] = None


def _get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=settings.GROQ_API_KEY)
    return _groq_client


# ---------------------------------------------------------------------------
# Follow-up sequence config
# Each entry: (follow_up_number, days_to_wait, tone_instructions)
# ---------------------------------------------------------------------------
FOLLOW_UP_SEQUENCE = [
    (
        1,   # follow-up number
        3,   # days since last contact
        """This is a gentle first follow-up. Keep it under 60 words.
Tone: friendly, no pressure. Reference that you sent something a few days ago.
Don't repeat the product pitch – just ask if they had a chance to see your previous message.
End with the same demo offer: "Happy to send a quick demo if useful."
Do NOT say "just following up" – that phrase is overused. Be creative.""",
    ),
    (
        2,
        7,
        """This is the second follow-up. Keep it under 70 words.
Tone: add brief new value. Mention one specific benefit relevant to their industry
(e.g. a law firm: "We've had teams cut contract review time by half using this").
Do not fabricate specific stats – frame it as what similar teams have experienced.
End with: "Would a quick demo help clarify?" or similar.
Be concise and direct.""",
    ),
    (
        3,
        14,
        """This is the final follow-up – a polite, low-pressure closing email. Keep it under 50 words.
Tone: respectful, zero pressure. Acknowledge they may be busy or it's not the right time.
Leave the door open without being pushy.
Example ending: "If the timing ever changes, I'm happy to share more. Wishing you well either way."
No hard sell. No guilt. Just a clean close.""",
    ),
]


FOLLOW_UP_PROMPT = """You are writing a follow-up cold email for a B2B software product.

Product: An AI document intelligence platform — teams can chat with their documents, search across files, and get answers with source citations.

Original outreach was sent to:
Company: {company_name}
Industry: {industry}
Country/Region: {country}
Original email subject: {original_subject}

Follow-up instructions:
{tone_instructions}

Sender name: {sender_name}

Return ONLY valid JSON:
{{
  "email_subject": "Re: {original_subject}",
  "email_body": "Full follow-up email body including greeting and sign-off"
}}

JSON response:"""


def _generate_follow_up_llm(record: dict, tone_instructions: str) -> Optional[dict]:
    client = _get_groq_client()

    prompt = FOLLOW_UP_PROMPT.format(
        company_name=record.get("company_name", ""),
        industry=record.get("industry", ""),
        country=record.get("country", record.get("region", "Unknown")),
        original_subject=record.get("email_subject", ""),
        tone_instructions=tone_instructions,
        sender_name=settings.SENDER_NAME,
    )

    try:
        response = _get_groq_client().chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip().rstrip("```").strip()
        return json.loads(raw)
    except Exception as e:
        logger.error("Follow-up LLM failed for %s: %s", record.get("company_name"), e)
        return None


def _fallback_follow_up(record: dict, follow_up_number: int) -> dict:
    """Rule-based fallback emails for each follow-up stage."""
    company = record.get("company_name", "there")
    original_subject = record.get("email_subject", "our platform")
    subject = f"Re: {original_subject}"

    if follow_up_number == 1:
        body = f"""Hi {company} team,

Just wanted to check if my previous note landed in the right place.

Happy to share a quick demo if it's useful — no commitment needed.

Best,
{settings.SENDER_NAME}"""

    elif follow_up_number == 2:
        industry = record.get("industry", "your industry")
        body = f"""Hi {company} team,

Teams in {industry} have been using our AI document platform to cut the time spent searching through files significantly — especially for compliance and internal knowledge work.

Thought it might be relevant given what you do.

Would a short demo be worth 10 minutes?

Best,
{settings.SENDER_NAME}"""

    else:
        body = f"""Hi {company} team,

I'll keep this brief — if the timing isn't right, no worries at all.

If document search or knowledge management ever becomes a priority, I'm happy to share more. Wishing you well either way.

Best,
{settings.SENDER_NAME}"""

    return {"email_subject": subject, "email_body": body}


def run_sequence_step(follow_up_number: int, days_wait: int, tone: str, dry_run: bool = False) -> dict:
    """Run one step of the follow-up sequence."""
    records = get_leads_for_follow_up(
        follow_up_number=follow_up_number,
        days_since_last=days_wait,
        limit=settings.DAILY_TARGET,
    )

    if not records:
        logger.info("Follow-up %d: no eligible leads", follow_up_number)
        return {"follow_up_number": follow_up_number, "sent": 0, "failed": 0}

    logger.info(
        "Follow-up %d: %d leads eligible (waited %d+ days)",
        follow_up_number, len(records), days_wait,
    )

    sent = 0
    failed = 0

    for record in records:
        company = record.get("company_name", "")
        contact_email = record.get("contact_email", "")
        outreach_id = record.get("id")

        if not contact_email:
            logger.warning("No email for %s — skipping follow-up", company)
            continue

        # Generate follow-up content
        if settings.GROQ_API_KEY:
            content = _generate_follow_up_llm(record, tone)
        else:
            content = None

        if content is None:
            content = _fallback_follow_up(record, follow_up_number)

        subject = content.get("email_subject", f"Re: {record.get('email_subject', '')}")
        body = content.get("email_body", "")

        if dry_run:
            logger.info(
                "[DRY RUN] Follow-up %d to %s (%s): %s",
                follow_up_number, contact_email, company, subject,
            )
            sent += 1
            continue

        success, error = send_email(contact_email, subject, body)
        mark_follow_up_sent(outreach_id, success, error)

        if success:
            sent += 1
            logger.info(
                "Follow-up %d sent → %s (%s)",
                follow_up_number, contact_email, company,
            )
        else:
            failed += 1
            logger.error(
                "Follow-up %d failed → %s: %s",
                follow_up_number, contact_email, error,
            )

        time.sleep(settings.DELAY_BETWEEN_EMAILS)

    return {"follow_up_number": follow_up_number, "sent": sent, "failed": failed}


def run(dry_run: bool = False) -> dict:
    """
    Run all pending follow-up steps across the full sequence.

    Returns:
        Summary dict: {total_sent, total_failed, steps: [...]}
    """
    logger.info("Follow-Up Agent starting (dry_run=%s)", dry_run)

    total_sent = 0
    total_failed = 0
    steps = []

    for follow_up_number, days_wait, tone in FOLLOW_UP_SEQUENCE:
        result = run_sequence_step(follow_up_number, days_wait, tone, dry_run=dry_run)
        total_sent += result["sent"]
        total_failed += result["failed"]
        steps.append(result)

    logger.info(
        "Follow-Up Agent done — total sent: %d, failed: %d",
        total_sent, total_failed,
    )
    return {"total_sent": total_sent, "total_failed": total_failed, "steps": steps}
