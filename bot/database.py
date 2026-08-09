import sqlite3
import shutil
from datetime import datetime
from pathlib import Path
from bot.logger import logger
from bot.config import config

DB_PATH = config.DB_PATH

def get_db_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    logger.info("Initializing database...")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        city TEXT DEFAULT 'قم',
        country TEXT DEFAULT 'Iran',
        language TEXT DEFAULT 'fa',
        subscribed INTEGER DEFAULT 1,
        register_date TEXT,
        last_active TEXT,
        notification_enabled INTEGER DEFAULT 1,
        notify_fajr INTEGER DEFAULT 1,
        notify_dhuhr INTEGER DEFAULT 0,
        notify_asr INTEGER DEFAULT 0,
        notify_maghrib INTEGER DEFAULT 1,
        notify_isha INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        total_users INTEGER,
        active_users INTEGER
    )''')
    try:
        c.execute("ALTER TABLE users ADD COLUMN last_main_msg_id INTEGER")
    except Exception:
        pass
    conn.commit()
    conn.close()
    init_extra_tables()
    logger.info("Database initialized successfully")

def backup_db():
    try:
        backup_dir = Path("backups")
        backup_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"bot_{timestamp}.db"
        shutil.copy(DB_PATH, backup_path)
        logger.info(f"Database backed up to {backup_path}")
        for file in sorted(backup_dir.glob("bot_*.db"))[:-7]:
            file.unlink()
    except Exception as e:
        logger.error(f"Backup failed: {e}")

def get_user(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result

def save_user(user_id, first_name, city="قم", country="Iran", language="fa"):
    conn = get_db_connection()
    c = conn.cursor()
    existing = get_user(user_id)
    if existing:
        c.execute('''UPDATE users SET 
            first_name = ?, 
            last_active = datetime('now')
            WHERE user_id = ?''', (first_name, user_id))
    else:
        c.execute('''INSERT INTO users 
            (user_id, first_name, city, country, language, subscribed, register_date, last_active)
            VALUES (?, ?, ?, ?, ?, 1, datetime('now'), datetime('now'))''',
            (user_id, first_name, city, country, language))
    conn.commit()
    conn.close()

def update_user_field(user_id, field, value):
    allowed_fields = {
        "city", "country", "language", "subscribed",
        "notification_enabled", "notify_fajr", "notify_dhuhr",
        "notify_asr", "notify_maghrib", "notify_isha"
    }
    if field not in allowed_fields:
        logger.warning(f"Attempt to update invalid field: {field}")
        return
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(f"UPDATE users SET {field} = ?, last_active = datetime('now') WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()

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
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("UPDATE users SET last_main_msg_id = ? WHERE user_id = ?", (message_id, user_id))
        conn.commit()
    except Exception as e:
        logger.error(f"set_last_main_msg_id failed: {e}")
    finally:
        conn.close()


# ── یادداشت و یادآوری و آمار شخصی ──

def init_extra_tables():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        content TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        text TEXT,
        remind_at TEXT,
        done INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now'))
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS usage_stats (
        user_id INTEGER,
        feature TEXT,
        count INTEGER DEFAULT 1,
        last_used TEXT,
        PRIMARY KEY (user_id, feature)
    )''')
    try:
        c.execute("ALTER TABLE users ADD COLUMN birth_date TEXT")
    except Exception:
        pass
    conn.commit()
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


def add_reminder(user_id, text, remind_at):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO reminders (user_id, text, remind_at) VALUES (?, ?, ?)", (user_id, text[:200], remind_at))
    conn.commit()
    conn.close()


def get_pending_reminders(before_time=None):
    conn = get_db_connection()
    c = conn.cursor()
    if before_time:
        c.execute("SELECT id, user_id, text, remind_at FROM reminders WHERE done = 0 AND remind_at <= ?", (before_time,))
    else:
        c.execute("SELECT id, user_id, text, remind_at FROM reminders WHERE done = 0")
    rows = c.fetchall()
    conn.close()
    return rows


def mark_reminder_done(rid):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE reminders SET done = 1 WHERE id = ?", (rid,))
    conn.commit()
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
