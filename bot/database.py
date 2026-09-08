"""Public database API compatibility facade.

Low-level connection, transaction and backup primitives are isolated in
``database_core.py``; feature repositories remain available from this module.
"""
import sqlite3
import os
import time
from datetime import datetime
from pathlib import Path
from bot.logger import logger
from bot.config import config

from bot.database_core import (
    BACKUP_KEEP, DB_BUSY_RETRIES, DB_BUSY_BACKOFF,
    _ensure_parent, get_db_connection, run_db_transaction, _execute_write,
    _user_count, restore_from_backup_if_needed, backup_db,
)

DB_PATH = config.DB_PATH
BACKUP_DIR = Path(config.BACKUP_DIR)

def init_db():
    logger.info(f"Initializing database at {DB_PATH} ...")
    restore_from_backup_if_needed()
    # ریستور خودکار از GitHub (اگر DB خالی و تنظیمات موجود باشد)
    try:
        from bot.db_persist import auto_restore_if_empty
        auto_restore_if_empty()
    except Exception as e:
        logger.error(f"auto_restore_if_empty: {e}")

    conn = get_db_connection()
    c = conn.cursor()
    # فقط CREATE IF NOT EXISTS — هیچ‌وقت جدول users را DROP نمی‌کنیم
    c.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        "user_id INTEGER PRIMARY KEY,"
        "first_name TEXT,"
        "city TEXT DEFAULT 'قم',"
        "country TEXT DEFAULT 'Iran',"
        "language TEXT DEFAULT 'fa',"
        "subscribed INTEGER DEFAULT 1,"
        "register_date TEXT,"
        "last_active TEXT,"
        "notification_enabled INTEGER DEFAULT 0,"
        "notify_fajr INTEGER DEFAULT 0,"
        "notify_dhuhr INTEGER DEFAULT 0,"
        "notify_asr INTEGER DEFAULT 0,"
        "notify_maghrib INTEGER DEFAULT 0,"
        "notify_isha INTEGER DEFAULT 0"
        ")"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS stats ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "date TEXT,"
        "total_users INTEGER,"
        "active_users INTEGER"
        ")"
    )
    for col, default in (
        ("last_main_msg_id", "INTEGER"),
        ("notification_enabled", "INTEGER DEFAULT 0"),
        ("notify_fajr", "INTEGER DEFAULT 0"),
        ("notify_dhuhr", "INTEGER DEFAULT 0"),
        ("notify_asr", "INTEGER DEFAULT 0"),
        ("notify_maghrib", "INTEGER DEFAULT 0"),
        ("notify_isha", "INTEGER DEFAULT 0"),
        ("birth_date", "TEXT"),
    ):
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} {default}")
        except Exception:
            pass
    conn.commit()
    conn.close()
    init_extra_tables()
    # یک‌بار: اذان‌ها پیش‌فرض خاموش (مگر کاربر خودش روشن کرده باشد بعد از این)
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        c.execute("SELECT value FROM meta WHERE key = 'azan_off_by_default_v2'")
        row = c.fetchone()
        if not row:
            c.execute(
                "UPDATE users SET notification_enabled = 0, "
                "notify_fajr = 0, notify_dhuhr = 0, notify_asr = 0, "
                "notify_maghrib = 0, notify_isha = 0"
            )
            c.execute(
                "INSERT INTO meta (key, value) VALUES ('azan_off_by_default_v2', '1')"
            )
            conn.commit()
            logger.info("Migration: all azan notifications set to OFF by default")
        conn.close()
    except Exception as e:
        logger.error(f"azan migration: {e}")
    n = _user_count(DB_PATH)
    logger.info(f"Database ready — {n} users")



def get_user(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result

def save_user(user_id, first_name, city="قم", country="Iran", language="fa"):
    """ثبت/به‌روزرسانی کاربر با retry محدود در صورت lock دیتابیس."""
    _execute_write(
        "INSERT INTO users "
        "(user_id, first_name, city, country, language, subscribed, "
        "register_date, last_active, notification_enabled, notify_fajr, "
        "notify_dhuhr, notify_asr, notify_maghrib, notify_isha) "
        "VALUES (?, ?, ?, ?, ?, 1, datetime('now'), datetime('now'), 0, 0, 0, 0, 0, 0) "
        "ON CONFLICT(user_id) DO UPDATE SET "
        "first_name=excluded.first_name, last_active=datetime('now')",
        (user_id, first_name, city, country, language),
    )

def update_user_field(user_id, field, value):
    allowed_fields = {
        "city", "country", "language", "subscribed",
        "notification_enabled", "notify_fajr", "notify_dhuhr",
        "notify_asr", "notify_maghrib", "notify_isha"
    }
    if field not in allowed_fields:
        logger.warning(f"Attempt to update invalid field: {field}")
        return
    _execute_write(
        f"UPDATE users SET {field} = ?, last_active = datetime('now') WHERE user_id = ?",
        (value, user_id),
    )

def get_all_users():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT user_id, first_name, city, language FROM users WHERE subscribed = 1")
    result = c.fetchall()
    conn.close()
    return result

def get_active_users_today():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE date(last_active) = date('now')")
    result = c.fetchone()[0]
    conn.close()
    return result

def update_stats():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    active = get_active_users_today()
    c.execute("INSERT INTO stats (date, total_users, active_users) VALUES (date('now'), ?, ?)", (total, active))
    conn.commit()
    conn.close()
    logger.info(f"Stats updated: total={total}, active={active}")

def get_user_city(user_id):
    user = get_user(user_id)
    return user[2] if user else "قم"

def get_user_country(user_id):
    user = get_user(user_id)
    return user[3] if user else "Iran"

def get_user_language(user_id):
    user = get_user(user_id)
    return user[4] if user else "fa"


# ── تنظیمات اذان ──
# ستون‌ها: notification_enabled, notify_fajr, notify_dhuhr, notify_asr, notify_maghrib, notify_isha

AZAN_FIELDS = {
    "fajr": ("notify_fajr", "اذان صبح"),
    "dhuhr": ("notify_dhuhr", "اذان ظهر"),
    "asr": ("notify_asr", "اذان عصر"),
    "maghrib": ("notify_maghrib", "اذان مغرب"),
    "isha": ("notify_isha", "اذان عشاء"),
}


def get_azan_settings(user_id):
    """
    برگرداندن تنظیمات اذان کاربر.
    خروجی: {
      enabled: bool,
      fajr, dhuhr, asr, maghrib, isha: bool
    }
    """
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            """SELECT COALESCE(notification_enabled, 0),
                      COALESCE(notify_fajr, 0),
                      COALESCE(notify_dhuhr, 0),
                      COALESCE(notify_asr, 0),
                      COALESCE(notify_maghrib, 0),
                      COALESCE(notify_isha, 0)
               FROM users WHERE user_id = ?""",
            (user_id,),
        )
        row = c.fetchone()
    except Exception:
        row = None
    finally:
        conn.close()
    if not row:
        return {
            "enabled": False,
            "fajr": False, "dhuhr": False, "asr": False,
            "maghrib": False, "isha": False,
        }
    return {
        "enabled": bool(row[0]),
        "fajr": bool(row[1]),
        "dhuhr": bool(row[2]),
        "asr": bool(row[3]),
        "maghrib": bool(row[4]),
        "isha": bool(row[5]),
    }


def set_azan_master(user_id, enabled: bool):
    """روشن/خاموش کردن کل اعلان اذان"""
    update_user_field(user_id, "notification_enabled", 1 if enabled else 0)


def toggle_azan_prayer(user_id, prayer_key: str) -> bool:
    """
    روشن/خاموش کردن یک اذان خاص.
    prayer_key: fajr|dhuhr|asr|maghrib|isha
    برمی‌گرداند وضعیت جدید (True=روشن)
    """
    if prayer_key not in AZAN_FIELDS:
        return False
    field, _ = AZAN_FIELDS[prayer_key]
    settings = get_azan_settings(user_id)
    new_val = not settings.get(prayer_key, False)
    update_user_field(user_id, field, 1 if new_val else 0)
    return new_val


def get_users_for_azan():
    """
    کاربران فعال برای اعلان اذان.
    خروجی: لیست (user_id, city, enabled, fajr, dhuhr, asr, maghrib, isha)
    """
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            """SELECT user_id, city,
                      COALESCE(notification_enabled, 0),
                      COALESCE(notify_fajr, 0),
                      COALESCE(notify_dhuhr, 0),
                      COALESCE(notify_asr, 0),
                      COALESCE(notify_maghrib, 0),
                      COALESCE(notify_isha, 0)
               FROM users
               WHERE subscribed = 1
                 AND COALESCE(notification_enabled, 0) = 1"""
        )
        rows = c.fetchall()
    except Exception as e:
        logger.error(f"get_users_for_azan: {e}")
        rows = []
    finally:
        conn.close()
    return rows

def get_last_main_msg_id(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT last_main_msg_id FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return row[0] if row else None
    except Exception:
        return None
    finally:
        conn.close()

def set_last_main_msg_id(user_id, message_id):
    try:
        _execute_write("UPDATE users SET last_main_msg_id = ? WHERE user_id = ?", (message_id, user_id))
    except Exception as e:
        logger.error(f"set_last_main_msg_id failed: {e}")


# ── یادداشت و یادآوری و آمار شخصی ──

def init_extra_tables():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "CREATE TABLE IF NOT EXISTS notes ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "user_id INTEGER,"
        "content TEXT,"
        "created_at TEXT DEFAULT (datetime('now')))"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS reminders ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "user_id INTEGER,"
        "text TEXT,"
        "remind_at TEXT,"
        "done INTEGER DEFAULT 0,"
        "created_at TEXT DEFAULT (datetime('now')),"
        "repeat_type TEXT DEFAULT 'once',"
        "repeat_every INTEGER DEFAULT 0,"
        "active INTEGER DEFAULT 1)"
    )
    for col, typ in (
        ("repeat_type", "TEXT DEFAULT 'once'"),
        ("repeat_every", "INTEGER DEFAULT 0"),
        ("active", "INTEGER DEFAULT 1"),
    ):
        try:
            c.execute(f"ALTER TABLE reminders ADD COLUMN {col} {typ}")
        except Exception:
            pass
    c.execute(
        "CREATE TABLE IF NOT EXISTS ai_memory ("
        "user_id INTEGER NOT NULL,"
        "key TEXT NOT NULL,"
        "value TEXT NOT NULL,"
        "updated_at TEXT DEFAULT (datetime('now')),"
        "PRIMARY KEY (user_id, key))"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS ai_history_summary ("
        "user_id INTEGER PRIMARY KEY,"
        "summary TEXT,"
        "updated_at TEXT DEFAULT (datetime('now')))"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS usage_stats ("
        "user_id INTEGER,"
        "feature TEXT,"
        "count INTEGER DEFAULT 1,"
        "last_used TEXT,"
        "PRIMARY KEY (user_id, feature))"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS sent_jokes ("
        "user_id INTEGER,"
        "joke_hash TEXT,"
        "sent_at TEXT DEFAULT (datetime('now')),"
        "PRIMARY KEY (user_id, joke_hash))"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS ai_preferences ("
        "user_id INTEGER PRIMARY KEY,"
        "provider TEXT NOT NULL,"
        "model TEXT DEFAULT '*',"
        "updated_at TEXT DEFAULT (datetime('now')))"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS user_preferences ("
        "user_id INTEGER PRIMARY KEY,"
        "response_style TEXT DEFAULT 'balanced',"
        "currency TEXT DEFAULT 'USD',"
        "updated_at TEXT DEFAULT (datetime('now')))"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS automation_preferences ("
        "user_id INTEGER PRIMARY KEY,"
        "daily_digest INTEGER DEFAULT 0,"
        "last_digest_date TEXT,"
        "updated_at TEXT DEFAULT (datetime('now')))"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS agent_learning ("
        "user_id INTEGER NOT NULL,"
        "agent TEXT NOT NULL,"
        "tool TEXT NOT NULL,"
        "success_count INTEGER DEFAULT 0,"
        "failure_count INTEGER DEFAULT 0,"
        "last_success TEXT,"
        "last_failure TEXT,"
        "last_error TEXT,"
        "updated_at TEXT DEFAULT (datetime('now')),"
        "PRIMARY KEY (user_id, agent, tool))"
    )
    try:
        c.execute("ALTER TABLE users ADD COLUMN birth_date TEXT")
    except Exception:
        pass
    # Indexes for the hottest read paths; CREATE IF NOT EXISTS is safe for upgrades.
    for sql in (
        "CREATE INDEX IF NOT EXISTS idx_users_subscribed ON users(subscribed)",
        "CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active)",
        "CREATE INDEX IF NOT EXISTS idx_reminders_pending ON reminders(done, active, remind_at)",
        "CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id, done, active)",
        "CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id, id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_sent_jokes_user_time ON sent_jokes(user_id, sent_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_usage_feature ON usage_stats(feature, count DESC)",
        "CREATE INDEX IF NOT EXISTS idx_agent_learning_user ON agent_learning(user_id, agent, tool)",
    ):
        c.execute(sql)
    conn.commit()
    conn.close()



def get_sent_joke_hashes(user_id, limit=5000):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            "SELECT joke_hash FROM sent_jokes WHERE user_id = ? ORDER BY sent_at DESC LIMIT ?",
            (user_id, limit),
        )
        return {row[0] for row in c.fetchall()}
    except Exception:
        return set()
    finally:
        conn.close()


def mark_joke_sent(user_id, joke_hash):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT OR IGNORE INTO sent_jokes (user_id, joke_hash) VALUES (?, ?)",
            (user_id, joke_hash),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"mark_joke_sent: {e}")
    finally:
        conn.close()


def reset_sent_jokes(user_id):
    """اگر همه جوک‌ها دیده شد، تاریخچه را پاک کن تا از اول شروع شود"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM sent_jokes WHERE user_id = ?", (user_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"reset_sent_jokes: {e}")
    finally:
        conn.close()



def add_note(user_id, content):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO notes (user_id, content) VALUES (?, ?)", (user_id, content[:500]))
    conn.commit()
    conn.close()


def get_notes(user_id, limit=10):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, content, created_at FROM notes WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows


def delete_note(user_id, note_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))
    conn.commit()
    conn.close()


def add_reminder(user_id, text, remind_at, repeat_type="once", repeat_every=0):
    """
    repeat_type: once | daily | weekly | monthly | every_minutes
    repeat_every: برای every_minutes = تعداد دقیقه؛ برای بقیه معمولاً ۱
    """
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO reminders (user_id, text, remind_at, done, repeat_type, repeat_every, active) "
        "VALUES (?, ?, ?, 0, ?, ?, 1)",
        (user_id, (text or "")[:300], remind_at, repeat_type or "once", int(repeat_every or 0)),
    )
    rid = c.lastrowid
    conn.commit()
    conn.close()
    return rid


def get_pending_reminders(before_time=None):
    conn = get_db_connection()
    c = conn.cursor()
    if before_time:
        c.execute(
            "SELECT id, user_id, text, remind_at, COALESCE(repeat_type,'once'), "
            "COALESCE(repeat_every,0), COALESCE(active,1) "
            "FROM reminders WHERE done = 0 AND COALESCE(active,1) = 1 AND remind_at <= ?",
            (before_time,),
        )
    else:
        c.execute(
            "SELECT id, user_id, text, remind_at, COALESCE(repeat_type,'once'), "
            "COALESCE(repeat_every,0), COALESCE(active,1) "
            "FROM reminders WHERE done = 0 AND COALESCE(active,1) = 1"
        )
    rows = c.fetchall()
    conn.close()
    return rows


def mark_reminder_done(rid):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE reminders SET done = 1, active = 0 WHERE id = ?", (rid,))
    conn.commit()
    conn.close()


def reschedule_reminder(rid, next_at):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE reminders SET remind_at = ?, done = 0, active = 1 WHERE id = ?",
        (next_at, rid),
    )
    conn.commit()
    conn.close()


def list_user_reminders(user_id, limit=20):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, text, remind_at, COALESCE(repeat_type,'once'), COALESCE(repeat_every,0), "
        "COALESCE(done,0), COALESCE(active,1) FROM reminders "
        "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def cancel_reminder(user_id, rid):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE reminders SET done = 1, active = 0 WHERE id = ? AND user_id = ?",
        (rid, user_id),
    )
    conn.commit()
    n = c.rowcount
    conn.close()
    return n > 0


# ── حافظه بلندمدت AI ────────────────────────────────────────────────────────

def set_ai_memory(user_id, key, value):
    key = (key or "note").strip()[:80]
    value = (value or "").strip()[:1000]
    if not value:
        return
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO ai_memory (user_id, key, value, updated_at) VALUES (?, ?, ?, datetime('now')) "
        "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')",
        (user_id, key, value),
    )
    conn.commit()
    conn.close()


def get_ai_memory(user_id, limit=40, query=None):
    """Return memory, optionally ranked by lightweight lexical relevance.

    The original (key, value) return shape is preserved. Ranking is performed
    in Python to avoid DB-specific full-text dependencies and to keep upgrades
    backward compatible.
    """
    conn = get_db_connection()
    c = conn.cursor()
    try:
        # Read a bounded candidate set; this table is intentionally small.
        c.execute(
            "SELECT key, value, updated_at FROM ai_memory WHERE user_id = ? "
            "ORDER BY updated_at DESC LIMIT ?",
            (user_id, max(1, min(int(limit) * 3, 120))),
        )
        rows = c.fetchall()
    except Exception:
        return []
    finally:
        conn.close()

    if not query:
        return [(r[0], r[1]) for r in rows[:limit]]

    import re
    tokens = set(re.findall(r"[\w\u0600-\u06ff]{2,}", str(query).lower()))
    if not tokens:
        return [(r[0], r[1]) for r in rows[:limit]]

    scored = []
    for key, value, updated_at in rows:
        hay = f"{key} {value}".lower()
        overlap = sum(1 for token in tokens if token in hay)
        key_bonus = sum(2 for token in tokens if token in str(key).lower())
        score = overlap + key_bonus
        # Small recency tie-break without depending on timestamp parsing.
        scored.append((score, str(updated_at or ""), key, value))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [(key, value) for score, _updated, key, value in scored[:limit]]


def delete_ai_memory(user_id, key=None):
    conn = get_db_connection()
    c = conn.cursor()
    if key:
        c.execute("DELETE FROM ai_memory WHERE user_id = ? AND key = ?", (user_id, key))
    else:
        c.execute("DELETE FROM ai_memory WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_ai_history_summary(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT summary FROM ai_history_summary WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return row[0] if row and row[0] else ""
    except Exception:
        return ""
    finally:
        conn.close()


def set_ai_history_summary(user_id, summary):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO ai_history_summary (user_id, summary, updated_at) VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(user_id) DO UPDATE SET summary = excluded.summary, updated_at = datetime('now')",
        (user_id, (summary or "")[:4000]),
    )
    conn.commit()
    conn.close()


def clear_ai_history_summary(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM ai_history_summary WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def record_agent_outcome(user_id, agent, tool, success, error=""):
    """Record bounded agent/tool feedback for future routing decisions."""
    agent = (str(agent or "general").strip()[:40] or "general")
    tool = (str(tool or "unknown").strip()[:80] or "unknown")
    error = str(error or "").strip()[:500]
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO agent_learning "
            "(user_id, agent, tool, success_count, failure_count, last_success, last_failure, last_error, updated_at) "
            "VALUES (?, ?, ?, ?, ?, CASE WHEN ? THEN datetime('now') ELSE NULL END, "
            "CASE WHEN ? THEN datetime('now') ELSE NULL END, ?, datetime('now')) "
            "ON CONFLICT(user_id, agent, tool) DO UPDATE SET "
            "success_count = success_count + excluded.success_count, "
            "failure_count = failure_count + excluded.failure_count, "
            "last_success = CASE WHEN excluded.success_count > 0 THEN datetime('now') ELSE agent_learning.last_success END, "
            "last_failure = CASE WHEN excluded.failure_count > 0 THEN datetime('now') ELSE agent_learning.last_failure END, "
            "last_error = CASE WHEN excluded.failure_count > 0 THEN excluded.last_error ELSE agent_learning.last_error END, "
            "updated_at = datetime('now')",
            (user_id, agent, tool, int(bool(success)), int(not success), bool(success), bool(not success), error),
        )
        conn.commit()
    finally:
        conn.close()


def get_agent_tool_reliability(user_id, agent, tool):
    """Return (score, attempts, failures) with a neutral prior for unknown tools."""
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT success_count, failure_count FROM agent_learning WHERE user_id = ? AND agent = ? AND tool = ?",
            (user_id, str(agent or "general")[:40], str(tool or "unknown")[:80]),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return 0.5, 0, 0
    success, failures = int(row[0] or 0), int(row[1] or 0)
    attempts = success + failures
    return ((success / attempts) if attempts else 0.5), attempts, failures


def get_agent_learning(user_id, limit=50):
    """Return recent agent learning rows for diagnostics/UI."""
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT agent, tool, success_count, failure_count, last_error, updated_at "
            "FROM agent_learning WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
            (user_id, max(1, min(int(limit), 100))),
        ).fetchall()
        return rows
    finally:
        conn.close()

def track_usage(user_id, feature):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO usage_stats (user_id, feature, count, last_used)
                 VALUES (?, ?, 1, datetime('now'))
                 ON CONFLICT(user_id, feature) DO UPDATE SET
                 count = count + 1, last_used = datetime('now')''', (user_id, feature))
    conn.commit()
    conn.close()


def get_user_usage(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT feature, count FROM usage_stats WHERE user_id = ? ORDER BY count DESC", (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows


def set_birth_date(user_id, birth_date):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET birth_date = ? WHERE user_id = ?", (birth_date, user_id))
    conn.commit()
    conn.close()


def get_birth_date(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT birth_date FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return row[0] if row else None
    except Exception:
        return None
    finally:
        conn.close()


# ── Smart UX preferences ───────────────────────────────────────────────────

def get_user_preferences(user_id):
    """Return lightweight UX preferences without exposing raw conversation data."""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            "SELECT response_style, currency FROM user_preferences WHERE user_id = ?",
            (user_id,),
        )
        row = c.fetchone()
        if not row:
            return {"response_style": "balanced", "currency": "USD"}
        return {"response_style": row[0] or "balanced", "currency": row[1] or "USD"}
    finally:
        conn.close()


def set_user_preference(user_id, key, value):
    """Safely update one supported UX preference."""
    allowed = {"response_style", "currency"}
    if key not in allowed:
        raise ValueError("unsupported preference")
    value = str(value).strip()[:32]
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO user_preferences (user_id, response_style, currency, updated_at) "
            "VALUES (?, ?, ?, datetime('now')) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            f"{key} = excluded.{key}, updated_at = datetime('now')",
            (user_id, value if key == "response_style" else "balanced",
             value if key == "currency" else "USD"),
        )
        conn.commit()
    finally:
        conn.close()


def clear_user_preferences(user_id):
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM user_preferences WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def get_top_user_features(user_id, limit=3):
    """Return most-used features, preferring recent usage when counts tie."""
    limit = max(1, min(int(limit), 10))
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT feature, count FROM usage_stats WHERE user_id = ? "
            "ORDER BY count DESC, last_used DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return rows
    finally:
        conn.close()


# ── Proactive automation preferences ───────────────────────────────────────

def get_automation_preferences(user_id):
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT daily_digest, last_digest_date FROM automation_preferences WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return {"daily_digest": False, "last_digest_date": None}
        return {"daily_digest": bool(row[0]), "last_digest_date": row[1]}
    finally:
        conn.close()


def set_daily_digest(user_id, enabled):
    enabled = 1 if enabled else 0
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO automation_preferences (user_id, daily_digest, updated_at) "
            "VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(user_id) DO UPDATE SET daily_digest=excluded.daily_digest, updated_at=datetime('now')",
            (user_id, enabled),
        )
        conn.commit()
    finally:
        conn.close()


def get_users_for_daily_digest(date_key, limit=5000):
    conn = get_db_connection()
    try:
        return conn.execute(
            "SELECT user_id FROM automation_preferences "
            "WHERE daily_digest = 1 AND COALESCE(last_digest_date, '') <> ? LIMIT ?",
            (date_key, max(1, int(limit))),
        ).fetchall()
    finally:
        conn.close()


def mark_daily_digest_sent(user_id, date_key):
    conn = get_db_connection()
    try:
        cur = conn.execute(
            "UPDATE automation_preferences SET last_digest_date = ?, updated_at = datetime('now') "
            "WHERE user_id = ? AND daily_digest = 1 AND COALESCE(last_digest_date, '') <> ?",
            (date_key, user_id, date_key),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_upcoming_user_reminders(user_id, now_iso, limit=5):
    conn = get_db_connection()
    try:
        return conn.execute(
            "SELECT text, remind_at, COALESCE(repeat_type,'once') FROM reminders "
            "WHERE user_id = ? AND done = 0 AND COALESCE(active,1) = 1 AND remind_at >= ? "
            "ORDER BY remind_at ASC LIMIT ?",
            (user_id, now_iso, max(1, int(limit))),
        ).fetchall()
    finally:
        conn.close()


# ── AI provider preference (per user) ──────────────────────────────────────

def get_ai_preference(user_id):
    """Returns (provider, model) or None. model='*' means all models of provider."""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            "SELECT provider, model FROM ai_preferences WHERE user_id = ?",
            (user_id,),
        )
        row = c.fetchone()
        if row:
            return (row[0], row[1] or "*")
        return None
    except Exception:
        return None
    finally:
        conn.close()


def set_ai_preference(user_id, provider, model="*"):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO ai_preferences (user_id, provider, model, updated_at) "
            "VALUES (?, ?, ?, datetime('now')) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "provider = excluded.provider, model = excluded.model, "
            "updated_at = datetime('now')",
            (user_id, provider, model or "*"),
        )
        conn.commit()
    finally:
        conn.close()


def clear_ai_preference(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM ai_preferences WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()
