"""Domain-specific Telegram handlers. Compatibility-preserving extraction from feature_handlers."""
from __future__ import annotations
from bot.utils.helpers import get_tools_keyboard
from bot.features.tools.app_tools import calculator, world_distance, count_text, parse_two_places

async def _h_calc(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    await u.message.reply_text(calculator(t), reply_markup=get_tools_keyboard())

async def _h_distance(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    from bot.features.tools.app_tools import parse_two_places
    parsed = parse_two_places(t)
    if not parsed:
        await u.message.reply_text(
            "❌ دو مکان بنویسید.\nمثال: تهران مشهد | تهران تا ترکیه | Paris to Tokyo",
            reply_markup=get_tools_keyboard(),
        )
        return
    p1, p2 = parsed
    await u.message.reply_text(await world_distance(p1, p2), reply_markup=get_tools_keyboard())

async def _h_count_text(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    await u.message.reply_text(count_text(t), reply_markup=get_tools_keyboard())
