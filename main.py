"""
B2B Lead Generation Pipeline – Main Orchestrator

Runs the full pipeline:
  Agent 1 (Lead Finder) → Agent 2 (Research) → Agent 3 (Outreach)

Usage:
  python main.py                  # Full pipeline
  python main.py --stage find     # Only find leads
  python main.py --stage research # Only research existing leads
  python main.py --stage outreach # Only send emails
  python main.py --dry-run        # Full pipeline without sending emails
  python main.py --target 20      # Override daily target
"""

import argparse
import logging
import sys
import os
from datetime import datetime

# Ensure the project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.database import init_db, get_pipeline_stats
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/pipeline.log", mode="a"),
    ],
)
logger = logging.getLogger("pipeline")


def validate_config():
    """Check required environment variables are set."""
    errors = []

    if not settings.GROQ_API_KEY:
        errors.append("GROQ_API_KEY is not set (required for AI analysis and email writing)")

    if not settings.SENDER_EMAIL:
        errors.append("SENDER_EMAIL is not set")

    if not settings.SENDER_NAME:
        errors.append("SENDER_NAME is not set")

    provider = settings.EMAIL_PROVIDER.lower()
    if provider == "gmail" and not settings.GMAIL_APP_PASSWORD:
        errors.append("GMAIL_APP_PASSWORD is not set (required for Gmail provider)")
    elif provider == "brevo" and (not settings.BREVO_SMTP_USER or not settings.BREVO_SMTP_PASSWORD):
        errors.append("BREVO_SMTP_USER / BREVO_SMTP_PASSWORD not set (required for Brevo provider)")
    elif provider == "resend" and not settings.RESEND_API_KEY:
        errors.append("RESEND_API_KEY is not set (required for Resend provider)")

    return errors


def run_pipeline(stage: str = "all", target: int = None, dry_run: bool = False):
    """
    Execute the lead generation pipeline.

    Args:
        stage: "all" | "find" | "research" | "outreach" | "followup"
        target: Override DAILY_TARGET for this run
        dry_run: Generate emails without sending
    """
    if target:
        settings.DAILY_TARGET = target

    os.makedirs("data", exist_ok=True)
    init_db()

    logger.info("=" * 60)
    logger.info("Pipeline starting at %s", datetime.utcnow().isoformat())
    logger.info("Stage: %s | Target: %d | Dry run: %s", stage, settings.DAILY_TARGET, dry_run)
    logger.info("=" * 60)

    from agents import lead_finder, research_agent, outreach_agent, follow_up_agent

    new_leads = []
    qualified = []
    outreach_result = {}
    follow_up_result = {}

    # Stage 1: Lead Finding
    if stage in ("all", "find"):
        logger.info("\n--- AGENT 1: LEAD FINDER ---")
        new_leads = lead_finder.run(target=settings.DAILY_TARGET * 3)
        logger.info("Found %d new leads", len(new_leads))

    # Stage 2: Research
    if stage in ("all", "research"):
        logger.info("\n--- AGENT 2: RESEARCH AGENT ---")
        qualified = research_agent.run()
        logger.info("Qualified leads: %d", len(qualified))

    # Stage 3: Outreach
    if stage in ("all", "outreach"):
        logger.info("\n--- AGENT 3: OUTREACH AGENT ---")
        outreach_result = outreach_agent.run(dry_run=dry_run)

    # Stage 4: Follow-ups
    if stage in ("all", "followup"):
        logger.info("\n--- AGENT 4: FOLLOW-UP AGENT ---")
        follow_up_result = follow_up_agent.run(dry_run=dry_run)
        logger.info(
            "Follow-ups sent: %d", follow_up_result.get("total_sent", 0)
        )

    # Summary
    stats = get_pipeline_stats()
    logger.info("\n%s", "=" * 60)
    logger.info("PIPELINE COMPLETE")
    logger.info("Leads discovered: %d", stats.get("discovered", 0))
    logger.info("Leads researched: %d", stats.get("researched", 0))
    logger.info("Leads rejected:   %d", stats.get("rejected", 0))
    logger.info("Emails sent:      %d", stats.get("emails_sent", 0))
    logger.info("Follow-ups sent:  %d", stats.get("follow_ups_sent", 0))
    logger.info("Replied:          %d", stats.get("replied", 0))
    logger.info("Emails failed:    %d", stats.get("emails_failed", 0))
    logger.info("=" * 60)

    return {
        "new_leads": len(new_leads),
        "qualified": len(qualified),
        "emails_sent": outreach_result.get("sent", 0),
        "emails_failed": outreach_result.get("failed", 0),
        "emails_skipped": outreach_result.get("skipped", 0),
        "follow_ups_sent": follow_up_result.get("total_sent", 0),
        "stats": stats,
    }


def main():
    parser = argparse.ArgumentParser(description="B2B Lead Generation Pipeline")
    parser.add_argument(
        "--setup-check",
        action="store_true",
        help="Verify all environment variables are configured correctly",
    )
    parser.add_argument(
        "--stage",
        choices=["all", "find", "research", "outreach", "followup"],
        default="all",
        help="Pipeline stage to run (default: all)",
    )
    parser.add_argument(
        "--target",
        type=int,
        default=None,
        help="Number of emails to send (overrides DAILY_TARGET env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pipeline without actually sending emails",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip config validation checks",
    )

    args = parser.parse_args()

    if args.setup_check:
        errors = validate_config()
        if errors:
            logger.error("Configuration errors:")
            for err in errors:
                logger.error("  ✗ %s", err)
            sys.exit(1)
        else:
            logger.info("✓ All required environment variables are set")
            logger.info("✓ Email provider: %s", settings.EMAIL_PROVIDER)
            logger.info("✓ Sender: %s <%s>", settings.SENDER_NAME, settings.SENDER_EMAIL)
            logger.info("✓ Daily target: %d emails", settings.DAILY_TARGET)
            sys.exit(0)

    if not args.skip_validation:
        errors = validate_config()
        if errors:
            logger.error("Configuration errors found:")
            for err in errors:
                logger.error("  ✗ %s", err)
            logger.error("\nSet these in your .env file or environment variables.")
            logger.error("Run with --skip-validation to bypass (not recommended).")
            sys.exit(1)

    result = run_pipeline(
        stage=args.stage,
        target=args.target,
        dry_run=args.dry_run,
    )

    return 0 if result["emails_sent"] > 0 or args.dry_run or args.stage != "all" else 1


if __name__ == "__main__":
    sys.exit(main())
