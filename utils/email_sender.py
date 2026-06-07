import smtplib
import logging
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from config.settings import settings

logger = logging.getLogger(__name__)


def send_via_gmail(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    """Send email via Gmail SMTP (500 emails/day free with personal Gmail)."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.SENDER_NAME} <{settings.SENDER_EMAIL}>"
        msg["To"] = to_email

        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(settings.SENDER_EMAIL, settings.GMAIL_APP_PASSWORD)
            server.sendmail(settings.SENDER_EMAIL, to_email, msg.as_string())

        logger.info("Gmail: Sent email to %s", to_email)
        return True, ""
    except Exception as e:
        logger.error("Gmail send failed to %s: %s", to_email, e)
        return False, str(e)


def send_via_brevo(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    """Send email via Brevo (formerly Sendinblue) SMTP – 300 free/day."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.SENDER_NAME} <{settings.SENDER_EMAIL}>"
        msg["To"] = to_email

        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP("smtp-relay.brevo.com", 587) as server:
            server.starttls()
            server.login(settings.BREVO_SMTP_USER, settings.BREVO_SMTP_PASSWORD)
            server.sendmail(settings.SENDER_EMAIL, to_email, msg.as_string())

        logger.info("Brevo: Sent email to %s", to_email)
        return True, ""
    except Exception as e:
        logger.error("Brevo send failed to %s: %s", to_email, e)
        return False, str(e)


def send_via_resend(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    """Send email via Resend – 100 free/day, 3000/month."""
    import requests

    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": f"{settings.SENDER_NAME} <{settings.SENDER_EMAIL}>",
                "to": [to_email],
                "subject": subject,
                "text": body,
            },
            timeout=15,
        )
        resp.raise_for_status()
        logger.info("Resend: Sent email to %s", to_email)
        return True, ""
    except Exception as e:
        logger.error("Resend send failed to %s: %s", to_email, e)
        return False, str(e)


def send_email(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    """Route to configured email provider."""
    provider = settings.EMAIL_PROVIDER.lower()

    if provider == "gmail":
        success, error = send_via_gmail(to_email, subject, body)
    elif provider == "brevo":
        success, error = send_via_brevo(to_email, subject, body)
    elif provider == "resend":
        success, error = send_via_resend(to_email, subject, body)
    else:
        return False, f"Unknown email provider: {provider}"

    if success:
        time.sleep(settings.DELAY_BETWEEN_EMAILS)

    return success, error
