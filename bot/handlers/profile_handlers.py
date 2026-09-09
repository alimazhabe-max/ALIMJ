"""Domain-specific Telegram handlers. Compatibility-preserving extraction from feature_handlers."""
from __future__ import annotations
from bot.database import set_birth_date
from bot.utils.helpers import get_profile_keyboard
from bot.features.date.date_tools import parse_shamsi

async def _h_birth_save(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_shamsi(t)
    if p:
        set_birth_date(uid, f"{p[0]}/{p[1]}/{p[2]}")
        await u.message.reply_text(f"✅ ذخیره شد: {p[0]}/{p[1]}/{p[2]}", reply_markup=get_profile_keyboard())
    else:
        await u.message.reply_text("❌", reply_markup=get_profile_keyboard())
