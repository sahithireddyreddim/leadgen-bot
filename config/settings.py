import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # LLM - Groq (free tier: generous daily limits)
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # Lead Finding - DuckDuckGo (no API key needed, free)
    # Optional: Google Custom Search (100 free queries/day)
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    GOOGLE_CSE_ID: str = os.getenv("GOOGLE_CSE_ID", "")

    # Email Finder - Hunter.io (25 free/month)
    HUNTER_API_KEY: str = os.getenv("HUNTER_API_KEY", "")

    # Email Sending
    # Options: "gmail" (500/day) | "brevo" (300/day free) | "resend" (100/day free)
    EMAIL_PROVIDER: str = os.getenv("EMAIL_PROVIDER", "gmail")
    SENDER_EMAIL: str = os.getenv("SENDER_EMAIL", "")
    SENDER_NAME: str = os.getenv("SENDER_NAME", "")

    # Gmail SMTP (create App Password at myaccount.google.com/apppasswords)
    GMAIL_APP_PASSWORD: str = os.getenv("GMAIL_APP_PASSWORD", "")

    # Brevo SMTP (sign up free at brevo.com → SMTP & API → SMTP keys)
    BREVO_SMTP_USER: str = os.getenv("BREVO_SMTP_USER", "")
    BREVO_SMTP_PASSWORD: str = os.getenv("BREVO_SMTP_PASSWORD", "")

    # Resend (sign up free at resend.com → API Keys)
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")

    # Pipeline settings
    DAILY_TARGET: int = int(os.getenv("DAILY_TARGET", "10"))
    MIN_FIT_SCORE: int = int(os.getenv("MIN_FIT_SCORE", "60"))
    DELAY_BETWEEN_EMAILS: int = int(os.getenv("DELAY_BETWEEN_EMAILS", "30"))  # seconds

    # Database
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/leads.db")

    # Web Scraping
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "10"))
    SCRAPE_DELAY: float = float(os.getenv("SCRAPE_DELAY", "2.0"))

    # Dashboard
    DASHBOARD_SECRET_KEY: str = os.getenv("DASHBOARD_SECRET_KEY", "change-me-in-production")
    DASHBOARD_PORT: int = int(os.getenv("PORT", "5000"))


settings = Settings()
