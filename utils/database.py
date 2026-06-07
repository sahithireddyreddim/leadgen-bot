import sqlite3
import json
import os
from datetime import datetime
from typing import Optional
from config.settings import settings


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(settings.DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(settings.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            website TEXT,
            industry TEXT,
            region TEXT,
            status TEXT DEFAULT 'discovered',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS research (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER REFERENCES leads(id),
            company_summary TEXT,
            country TEXT,
            document_workflows TEXT,
            potential_challenges TEXT,
            use_cases TEXT,
            fit_score INTEGER DEFAULT 0,
            researched_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS outreach (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER REFERENCES leads(id),
            contact_email TEXT,
            email_subject TEXT,
            email_body TEXT,
            sent_at TEXT,
            last_contacted_at TEXT,
            follow_up_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            error_message TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # Migrate existing databases that don't have the newer columns yet
    migrations = [
        ("region",           "leads",    "TEXT"),
        ("country",          "research", "TEXT"),
        ("last_contacted_at","outreach", "TEXT"),
        ("follow_up_count",  "outreach", "INTEGER DEFAULT 0"),
    ]
    for col, table, definition in migrations:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
        except Exception:
            pass  # Column already exists
    conn.commit()
    conn.close()


def save_lead(company_name: str, website: str, industry: str, region: str = "") -> Optional[int]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM leads WHERE website = ? OR company_name = ?",
            (website, company_name),
        )
        if cursor.fetchone():
            return None  # duplicate
        cursor.execute(
            "INSERT INTO leads (company_name, website, industry, region) VALUES (?, ?, ?, ?)",
            (company_name, website, industry, region),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def save_research(lead_id: int, data: dict) -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO research
               (lead_id, company_summary, country, document_workflows,
                potential_challenges, use_cases, fit_score)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                lead_id,
                data.get("company_summary", ""),
                data.get("country", ""),
                json.dumps(data.get("document_workflows", [])),
                json.dumps(data.get("potential_challenges", [])),
                json.dumps(data.get("use_cases", [])),
                data.get("fit_score", 0),
            ),
        )
        status = "researched" if data.get("fit_score", 0) >= settings.MIN_FIT_SCORE else "rejected"
        cursor.execute(
            "UPDATE leads SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.utcnow().isoformat(), lead_id),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def save_outreach(lead_id: int, contact_email: str, subject: str, body: str) -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO outreach (lead_id, contact_email, email_subject, email_body)
               VALUES (?, ?, ?, ?)""",
            (lead_id, contact_email, subject, body),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def mark_email_sent(outreach_id: int, success: bool, error: str = ""):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        cursor.execute(
            """UPDATE outreach
               SET status = ?, sent_at = COALESCE(sent_at, ?),
                   last_contacted_at = ?, error_message = ?
               WHERE id = ?""",
            (
                "sent" if success else "failed",
                now if success else None,
                now if success else None,
                error,
                outreach_id,
            ),
        )
        if success:
            cursor.execute(
                """UPDATE leads SET status = 'emailed', updated_at = ?
                   WHERE id = (SELECT lead_id FROM outreach WHERE id = ?)""",
                (now, outreach_id),
            )
        conn.commit()
    finally:
        conn.close()


def mark_follow_up_sent(outreach_id: int, success: bool, error: str = ""):
    """Increment follow_up_count and update last_contacted_at."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        if success:
            cursor.execute(
                """UPDATE outreach
                   SET follow_up_count = follow_up_count + 1,
                       last_contacted_at = ?,
                       status = 'followed_up'
                   WHERE id = ?""",
                (now, outreach_id),
            )
        else:
            cursor.execute(
                "UPDATE outreach SET error_message = ? WHERE id = ?",
                (error, outreach_id),
            )
        conn.commit()
    finally:
        conn.close()


def get_leads_for_research(limit: int = 20) -> list:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM leads WHERE status = 'discovered' ORDER BY created_at LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_leads_for_outreach(limit: int = 20) -> list:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT l.*, r.company_summary, r.country, r.document_workflows,
                      r.potential_challenges, r.use_cases, r.fit_score
               FROM leads l
               JOIN research r ON r.lead_id = l.id
               WHERE l.status = 'researched'
               ORDER BY r.fit_score DESC
               LIMIT ?""",
            (limit,),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            for field in ("document_workflows", "potential_challenges", "use_cases"):
                if row.get(field):
                    try:
                        row[field] = json.loads(row[field])
                    except (json.JSONDecodeError, TypeError):
                        row[field] = []
        return rows
    finally:
        conn.close()


def get_leads_for_follow_up(follow_up_number: int, days_since_last: int, limit: int = 50) -> list:
    """
    Return outreach records that:
    - Were sent successfully (status in 'sent', 'followed_up')
    - Have follow_up_count == follow_up_number - 1  (ready for next follow-up)
    - Last contacted more than days_since_last days ago
    - Have not been marked as replied
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT o.*, l.company_name, l.website, l.industry, l.region,
                      r.company_summary, r.country, r.document_workflows,
                      r.potential_challenges, r.use_cases, r.fit_score
               FROM outreach o
               JOIN leads l ON l.id = o.lead_id
               LEFT JOIN research r ON r.lead_id = o.lead_id
               WHERE o.status IN ('sent', 'followed_up')
                 AND o.follow_up_count = ?
                 AND o.last_contacted_at IS NOT NULL
                 AND datetime(o.last_contacted_at) <= datetime('now', ?)
               ORDER BY o.last_contacted_at ASC
               LIMIT ?""",
            (
                follow_up_number - 1,
                f"-{days_since_last} days",
                limit,
            ),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            for field in ("document_workflows", "potential_challenges", "use_cases"):
                if row.get(field):
                    try:
                        row[field] = json.loads(row[field])
                    except (json.JSONDecodeError, TypeError):
                        row[field] = []
        return rows
    finally:
        conn.close()


def mark_replied(outreach_id: int):
    """Mark an outreach as replied (stops further follow-ups)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE outreach SET status = 'replied' WHERE id = ?",
            (outreach_id,),
        )
        cursor.execute(
            """UPDATE leads SET status = 'replied', updated_at = ?
               WHERE id = (SELECT lead_id FROM outreach WHERE id = ?)""",
            (datetime.utcnow().isoformat(), outreach_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_pipeline_stats() -> dict:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT status, COUNT(*) as count FROM leads GROUP BY status")
        stats = {row["status"]: row["count"] for row in cursor.fetchall()}
        cursor.execute("SELECT COUNT(*) as count FROM outreach WHERE status = 'sent'")
        stats["emails_sent"] = cursor.fetchone()["count"]
        cursor.execute("SELECT COUNT(*) as count FROM outreach WHERE status = 'followed_up'")
        stats["follow_ups_sent"] = cursor.fetchone()["count"]
        cursor.execute("SELECT COUNT(*) as count FROM outreach WHERE status = 'replied'")
        stats["replied"] = cursor.fetchone()["count"]
        cursor.execute("SELECT COUNT(*) as count FROM outreach WHERE status = 'failed'")
        stats["emails_failed"] = cursor.fetchone()["count"]
        return stats
    finally:
        conn.close()


def get_all_outreach(limit: int = 100) -> list:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT o.*, l.company_name, l.website, l.industry, l.region,
                      r.country
               FROM outreach o
               JOIN leads l ON l.id = o.lead_id
               LEFT JOIN research r ON r.lead_id = o.lead_id
               ORDER BY o.created_at DESC LIMIT ?""",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()
