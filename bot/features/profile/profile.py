"""پروفایل و آمار کاربر"""
from bot.database import get_user, get_user_city, get_birth_date, get_user_usage, get_notes

def profile_text(user_id: int, first_name: str = "کاربر") -> str:
    city = get_user_city(user_id) or "تنظیم نشده"
    birth = get_birth_date(user_id) or "ثبت نشده"
    usage = get_user_usage(user_id) or {}
    notes = get_notes(user_id) or []
    lines = [
        f"👤 **پروفایل {first_name}**\n",
        f"🏙 شهر: {city}",
        f"🎂 تاریخ تولد: {birth}",
        f"📊 تعداد استفاده: {sum(usage.values()) if usage else 0}",
        f"📒 تعداد یادداشت‌ها: {len(notes)}",
    ]
    if usage:
        lines.append("\n**بیشترین استفاده‌ها:**")
        for k, v in sorted(usage.items(), key=lambda x: -x[1])[:5]:
            lines.append(f"• {k}: {v}")
    return "\n".join(lines)
