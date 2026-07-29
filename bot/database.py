import sqlite3
import shutil
from datetime import datetime
from pathlib import Path
from logger import logger
from config import config

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
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")

def backup_db():
    try:
        backup_dir = Path("backups")
        backup_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"bot_{timestamp}.db"
        shutil.copy(DB_PATH, backup_path)
        logger.info(f"Database backed up to {backup_path}")
        # حذف فایل‌های قدیمی (نگهداری ۷ روز آخر)
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
    c.execute('''INSERT OR REPLACE INTO users 
        (user_id, first_name, city, country, language, subscribed, register_date, last_active)
        VALUES (?, ?, ?, ?, ?, 1, datetime('now'), datetime('now'))''',
        (user_id, first_name, city, country, language))
    conn.commit()
    conn.close()

def update_user_field(user_id, field, value):
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

def get_user_language(user_id):
    user = get_user(user_id)
    return user[3] if user else "fa"
