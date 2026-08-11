import sqlite3
import shutil
import os
from datetime import datetime
from pathlib import Path
from bot.logger import logger
from bot.config import config

DB_PATH = config.DB_PATH
BACKUP_DIR = Path(config.BACKUP_DIR)
BACKUP_KEEP = getattr(config, "BACKUP_KEEP", 14)


def _ensure_parent(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def get_db_connection():
    _ensure_parent(DB_PATH)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _user_count(db_file) -> int:
    """تعداد کاربران یک فایل دیتابیس — اگر خراب باشد 0"""
    try:
        p = Path(db_file)
        if not p.exists() or p.stat().st_size < 100:
            return 0
        conn = sqlite3.connect(str(p), timeout=5)
        try:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users")
            return int(c.fetchone()[0] or 0)
        finally:
            conn.close()
    except Exception:
        return 0


def restore_from_backup_if_needed():
    """
    اگر دیتابیس اصلی خالی/ناموجود باشد ولی بکاپ داشته باشیم،
    آخرین بکاپ معتبر را برمی‌گرداند تا داده کاربران از بین نرود.
    """
    _ensure_parent(DB_PATH)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    current_users = _user_count(DB_PATH)
    if current_users > 0:
        logger.info(f"DB OK — {current_users} users at {DB_PATH}")
        return

    candidates = []
    if BACKUP_DIR.exists():
        candidates.extend(sorted(BACKUP_DIR.glob("bot_*.db"), reverse=True))
    stable = Path(DB_PATH).parent / "bot_data.backup.db"
    if stable.exists():
        candidates.insert(0, stable)

    best = None
    best_count = 0
    for p in candidates:
        n = _user_count(p)
        if n > best_count:
            best, best_count = p, n

    if best and best_count > 0:
        try:
            shutil.copy2(best, DB_PATH)
            logger.warning(
                f"Restored DB from backup {best.name} ({best_count} users) -> {DB_PATH}"
            )
        except Exception as e:
            logger.error(f"Restore failed: {e}")
    else:
        logger.info(f"No backup to restore — fresh DB at {DB_PATH}")


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
        c.execute("SELECT value FROM meta WHERE key = 'azan_off_by_default_v1'")
        row = c.fetchone()
        if not row:
            c.execute(
                "UPDATE users SET notification_enabled = 0, "
                "notify_fajr = 0, notify_dhuhr = 0, notify_asr = 0, "
                "notify_maghrib = 0, notify_isha = 0"
            )
            c.execute(
                "INSERT INTO meta (key, value) VALUES ('azan_off_by_default_v1', '1')"
            )
            conn.commit()
            logger.info("Migration: all azan notifications set to OFF by default")
        conn.close()
    except Exception as e:
        logger.error(f"azan migration: {e}")
    n = _user_count(DB_PATH)
    logger.info(f"Database ready — {n} users")


def backup_db():
    """
    بکاپ روی همان دیسک پایدار:
    - backups/bot_YYYYMMDD_HHMMSS.db
    - bot_data.backup.db (آخرین نسخه ثابت برای ریستور سریع)
    """
    try:
        if not Path(DB_PATH).exists():
            return
        users = _user_count(DB_PATH)
        if users == 0:
            logger.info("Skip backup — DB has 0 users")
            return

        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUP_DIR / f"bot_{timestamp}.db"
        shutil.copy2(DB_PATH, backup_path)

        stable = Path(DB_PATH).parent / "bot_data.backup.db"
        shutil.copy2(DB_PATH, stable)

        old = sorted(BACKUP_DIR.glob("bot_*.db"))
        for f in old[:-BACKUP_KEEP]:
            try:
                f.unlink()
            except Exception:
                pass

        logger.info(f"DB backed up ({users} users) -> {backup_path.name}")
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
            """SELECT notification_enabled,
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
            "enabled": True,
            "fajr": True, "dhuhr": False, "asr": False,
            "maghrib": True, "isha": False,
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
        "created_at TEXT DEFAULT (datetime('now')))"
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
    try:
        c.execute("ALTER TABLE users ADD COLUMN birth_date TEXT")
    except Exception:
        pass
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
