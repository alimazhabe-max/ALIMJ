"""Database connection, transaction and backup primitives.

Kept separate from the feature repositories so the public bot.database API
remains backwards compatible while the database layer can evolve independently.
"""
import sqlite3
import shutil
import os
import time
from pathlib import Path
import sys
from datetime import datetime
from bot.logger import logger
from bot.config import config

DB_PATH = config.DB_PATH
BACKUP_DIR = Path(config.BACKUP_DIR)
BACKUP_KEEP = getattr(config, "BACKUP_KEEP", 14)

DB_BUSY_RETRIES = max(1, int(os.getenv("DB_BUSY_RETRIES", "4")))
DB_BUSY_BACKOFF = max(0.02, float(os.getenv("DB_BUSY_BACKOFF", "0.08")))

def _current_db_path():
    mod = sys.modules.get("bot.database")
    return getattr(mod, "DB_PATH", DB_PATH) if mod is not None else DB_PATH

def _current_backup_dir():
    mod = sys.modules.get("bot.database")
    return Path(getattr(mod, "BACKUP_DIR", BACKUP_DIR)) if mod is not None else BACKUP_DIR

def _ensure_parent(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)


DB_BUSY_RETRIES = max(1, int(os.getenv("DB_BUSY_RETRIES", "4")))
DB_BUSY_BACKOFF = max(0.02, float(os.getenv("DB_BUSY_BACKOFF", "0.08")))

def _current_db_path():
    mod = sys.modules.get("bot.database")
    return getattr(mod, "DB_PATH", DB_PATH) if mod is not None else DB_PATH

def _current_backup_dir():
    mod = sys.modules.get("bot.database")
    return Path(getattr(mod, "BACKUP_DIR", BACKUP_DIR)) if mod is not None else BACKUP_DIR


def get_db_connection():
    _ensure_parent(_current_db_path())
    conn = sqlite3.connect(_current_db_path(), check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA wal_autocheckpoint=1000")
    return conn


def run_db_transaction(operation, retries=DB_BUSY_RETRIES):
    """Run one short transaction and retry only transient SQLite lock errors."""
    last_exc = None
    for attempt in range(max(0, retries) + 1):
        conn = get_db_connection()
        try:
            result = operation(conn)
            conn.commit()
            return result
        except sqlite3.OperationalError as exc:
            conn.rollback()
            last_exc = exc
            msg = str(exc).lower()
            transient = any(x in msg for x in ("locked", "busy"))
            if not transient or attempt >= retries:
                raise
            time.sleep(DB_BUSY_BACKOFF * (2 ** attempt))
        finally:
            conn.close()
    if last_exc:
        raise last_exc


def _execute_write(sql, params=()):
    run_db_transaction(lambda conn: conn.execute(sql, params))



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
    _ensure_parent(_current_db_path())
    _current_backup_dir().mkdir(parents=True, exist_ok=True)

    current_users = _user_count(_current_db_path())
    if current_users > 0:
        logger.info(f"DB OK — {current_users} users at {_current_db_path()}")
        return

    candidates = []
    if BACKUP_DIR.exists():
        candidates.extend(sorted(_current_backup_dir().glob("bot_*.db"), reverse=True))
    stable = Path(_current_db_path()).parent / "bot_data.backup.db"
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
            shutil.copy2(best, _current_db_path())
            logger.warning(
                f"Restored DB from backup {best.name} ({best_count} users) -> {_current_db_path()}"
            )
        except Exception as e:
            logger.error(f"Restore failed: {e}")
    else:
        logger.info(f"No backup to restore — fresh DB at {_current_db_path()}")


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

        _current_backup_dir().mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = _current_backup_dir() / f"bot_{timestamp}.db"
        stable = Path(_current_db_path()).parent / "bot_data.backup.db"

        # SQLite Backup API is safe with WAL and concurrent writes.
        src = sqlite3.connect(_current_db_path(), check_same_thread=False, timeout=30)
        try:
            for target in (backup_path, stable):
                dst = sqlite3.connect(str(target), check_same_thread=False)
                try:
                    src.backup(dst)
                finally:
                    dst.close()
        finally:
            src.close()

        old = sorted(BACKUP_DIR.glob("bot_*.db"))
        for f in old[:-BACKUP_KEEP]:
            try:
                f.unlink()
            except Exception:
                pass

        logger.info(f"DB backed up ({users} users) -> {backup_path.name}")
    except Exception as e:
        logger.error(f"Backup failed: {e}")


