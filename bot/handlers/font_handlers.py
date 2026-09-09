"""Domain-specific Telegram handlers. Compatibility-preserving extraction from feature_handlers."""
from __future__ import annotations
from bot.utils.helpers import get_font_keyboard
from bot.features.fonts import apply_font, apply_all_fonts

async def _h_font_text(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    font = c.user_data.get("selected_font", "bold")
    await u.message.reply_text(apply_font(t, font), reply_markup=get_font_keyboard())

async def _h_font_all(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    await u.message.reply_text(apply_all_fonts(t), reply_markup=get_font_keyboard())
