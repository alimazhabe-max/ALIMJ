"""Compatibility facade for feature-specific handlers.

Domain handlers live in dedicated modules; legacy imports from this module
remain valid to avoid breaking the message router or external integrations.
"""
from bot.handlers.date_handlers import (
    _h_date_convert, _h_age_calc, _h_birthday, _h_zodiac, _h_lunar,
    _h_date_diff, _h_age_diff, _h_event_search, _h_countdown,
)
from bot.handlers.market_handlers import (
    _h_profit, _h_currency, _h_crypto_full, _h_crypto_pos,
    _h_crypto_chart, _h_crypto_analyze,
)
from bot.handlers.tools_handlers import _h_calc, _h_distance, _h_count_text
from bot.handlers.profile_handlers import _h_birth_save
from bot.handlers.font_handlers import _h_font_text, _h_font_all

__all__ = [name for name in globals() if name.startswith("_h_")]
