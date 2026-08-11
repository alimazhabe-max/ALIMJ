# -*- coding: utf-8 -*-
"""
بکاپ و ریستور خودکار و رایگان
  1) GitHub (GITHUB_TOKEN + GITHUB_REPO) → کاملاً خودکار
  2) تلگرام ادمین (دستی /backup و /restore)
"""
import asyncio
import base64
import os
import shutil
from datetime import datetime
from pathlib import Path

import requests

from bot.config import config
from bot.database import DB_PATH, backup_db, _user_count, get_db_connection
from bot.logger import logger

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.getenv("GITHUB_REPO", "").strip()  # مثال: username/bot-data-backup
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main").strip()
GITHUB_FILE = os.getenv("GITHUB_DB_FILE", "bot_data.db").strip()
API = "https://api.github.com"


def _gh_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def github_enabled() -> bool:
    return bool(GITHUB_TOKEN and GITHUB_REPO)


def _github_get_sha():
    url = f"{API}/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}?ref={GITHUB_BRANCH}"
    r = requests.get(url, headers=_gh_headers(), timeout=30)
    if r.status_code == 200:
        return r.json().get("sha")
    return None


def github_upload_db():
    if not github_enabled():
        return False, "GitHub تنظیم نشده"
    path = Path(DB_PATH)
    if not path.exists():
        return False, "فایل DB نیست"
    users = _user_count(DB_PATH)
    if users == 0:
        return False, "DB خالی است — آپلود نشد"
    try:
        content_b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        sha = _github_get_sha()
        payload = {
            "message": f"auto backup — {users} users — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
            "content": content_b64,
            "branch": GITHUB_BRANCH,
        }
        if sha:
            payload["sha"] = sha
        url = f"{API}/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
        r = requests.put(url, headers=_gh_headers(), json=payload, timeout=60)
        if r.status_code in (200, 201):
            logger.info(f"GitHub backup OK ({users} users)")
            return True, f"GitHub بکاپ شد ({users} کاربر)"
        return False, f"GitHub error {r.status_code}: {r.text[:200]}"
    except Exception as e:
        logger.error(f"github_upload: {e}")
        return False, str(e)


def github_download_db():
    if not github_enabled():
        return False, "GitHub تنظیم نشده"
    try:
        url = f"{API}/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}?ref={GITHUB_BRANCH}"
        r = requests.get(url, headers=_gh_headers(), timeout=60)
        if r.status_code != 200:
            return False, f"دانلود نشد ({r.status_code})"
        data = r.json()
        content_b64 = data.get("content", "")
        if not content_b64:
            dl = data.get("download_url")
            if dl:
                raw = requests.get(dl, timeout=60).content
            else:
                return False, "محتوای خالی"
        else:
            raw = base64.b64decode("".join(content_b64.split()))
        if len(raw) < 100:
            return False, "فایل دانلودشده خیلی کوچک است"
        Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(DB_PATH).with_suffix(".db.ghdownload")
        tmp.write_bytes(raw)
        n = _user_count(tmp)
        if n == 0:
            tmp.unlink(missing_ok=True)
            return False, "بکاپ گیت‌هاب کاربر ندارد"
        if Path(DB_PATH).exists() and _user_count(DB_PATH) > 0:
            try:
                backup_db()
            except Exception:
                pass
        tmp.replace(DB_PATH)
        logger.warning(f"Restored from GitHub — {n} users")
        return True, f"از GitHub بازگردانی شد — {n} کاربر"
    except Exception as e:
        logger.error(f"github_download: {e}")
        return False, str(e)


def auto_restore_if_empty() -> bool:
    if _user_count(DB_PATH) > 0:
        return False
    if not github_enabled():
        logger.info("DB empty and GitHub not configured — skip auto-restore")
        return False
    ok, msg = github_download_db()
    logger.info(f"auto_restore: {msg}")
    return ok


def auto_backup():
    try:
        backup_db()
    except Exception as e:
        logger.error(f"local backup: {e}")
    if github_enabled():
        return github_upload_db()
    return False, "GitHub غیرفعال — فقط بکاپ محلی"


async def send_db_to_admins(bot, caption: str = None):
    path = Path(DB_PATH)
    if not path.exists():
        return False, "فایل دیتابیس وجود ندارد"
    try:
        backup_db()
    except Exception:
        pass
    users = _user_count(DB_PATH)
    size_kb = path.stat().st_size / 1024
    cap = caption or (
        f"💾 بکاپ دیتابیس\n"
        f"👥 کاربران: {users}\n"
        f"📦 {size_kb:.1f} KB\n"
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"ریستور دستی: همین فایل را با کپشن /restore بفرست"
    )
    ok = 0
    for admin_id in config.ADMIN_IDS:
        try:
            with open(path, "rb") as f:
                await bot.send_document(
                    chat_id=admin_id,
                    document=f,
                    filename=f"bot_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
                    caption=cap,
                )
            ok += 1
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"Send backup to admin {admin_id}: {e}")
    return ok > 0, f"ارسال به {ok}/{len(config.ADMIN_IDS)} ادمین ({users} کاربر)"


async def restore_db_from_file(file_path: str):
    src = Path(file_path)
    if not src.exists() or src.stat().st_size < 100:
        return False, "فایل نامعتبر است"
    if Path(DB_PATH).exists() and _user_count(DB_PATH) > 0:
        try:
            backup_db()
        except Exception:
            pass
    dest = Path(DB_PATH)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".db.restoring")
    shutil.copy2(src, tmp)
    tmp.replace(dest)
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        final = c.fetchone()[0]
        conn.close()
    except Exception as e:
        return False, f"فایل معتبر نیست: {e}"
    if github_enabled():
        try:
            github_upload_db()
        except Exception:
            pass
    return True, f"✅ بازگردانی موفق — {final} کاربر"


async def notify_admins_if_empty(bot):
    n = _user_count(DB_PATH)
    if n > 0:
        return
    if not config.ADMIN_IDS:
        return
    if github_enabled():
        text = (
            "⚠️ دیتابیس خالی بود.\n"
            "تلاش برای بازگردانی خودکار از GitHub انجام شد.\n"
            "اگر هنوز خالی است فایل بکاپ را با /restore بفرست."
        )
    else:
        text = (
            "⚠️ دیتابیس خالی است.\n\n"
            "برای حالت کاملاً خودکار GITHUB_TOKEN و GITHUB_REPO را ست کن.\n"
            "یا فایل بکاپ را با کپشن /restore بفرست."
        )
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=text)
            await asyncio.sleep(0.2)
        except Exception as e:
            logger.error(f"notify empty: {e}")
