"""پروفایل حرفه‌ای کاربر تلگرام"""
from datetime import datetime, timezone
from bot.database import get_user, get_user_city, get_birth_date, get_user_usage, get_notes


def profile_text(user_id: int, first_name: str = "کاربر", username: str = None,
                 last_name: str = None, language_code: str = None) -> str:
    city = get_user_city(user_id) or "تنظیم نشده"
    birth = get_birth_date(user_id) or "ثبت نشده"
    usage = get_user_usage(user_id) or {}
    notes = get_notes(user_id) or []
    full_name = first_name or ""
    if last_name:
        full_name = f"{full_name} {last_name}".strip()

    lines = [
        "👤 **پنل پروفایل**\n",
        f"📝 نام: **{full_name or '—'}**",
        f"🔗 یوزرنیم: **@{username}**" if username else "🔗 یوزرنیم: —",
        f"🆔 آیدی عددی: `{user_id}`",
        f"🌐 زبان تلگرام: {language_code or '—'}",
        f"🏙 شهر ربات: {city}",
        f"🎂 تاریخ تولد: {birth}",
        f"📒 یادداشت‌ها: {len(notes)}",
        f"📊 کل استفاده: {sum(usage.values()) if usage else 0}",
    ]
    if usage:
        lines.append("\n**بیشترین بخش‌ها:**")
        for k, v in sorted(usage.items(), key=lambda x: -x[1])[:5]:
            lines.append(f"• {k}: {v}")
    lines.append("\n💡 عکس پروفایل در پیام جدا (در صورت وجود) ارسال می‌شود.")
    return "\n".join(lines)
