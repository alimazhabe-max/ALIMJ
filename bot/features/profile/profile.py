"""پروفایل حرفه‌ای کاربر تلگرام"""
from bot.database import get_user_city, get_birth_date, get_user_usage


def profile_text(user_id: int, first_name: str = "کاربر", username: str = None,
                 last_name: str = None, language_code: str = None) -> str:
    try:
        city = get_user_city(user_id) or "تنظیم نشده"
    except Exception:
        city = "تنظیم نشده"
    try:
        birth = get_birth_date(user_id) or "ثبت نشده"
    except Exception:
        birth = "ثبت نشده"
    try:
        usage_rows = get_user_usage(user_id) or []
    except Exception:
        usage_rows = []

    # usage ممکن است list[tuple] یا dict باشد
    if isinstance(usage_rows, dict):
        items = sorted(usage_rows.items(), key=lambda x: -x[1])
        total = sum(usage_rows.values())
    else:
        items = list(usage_rows)
        total = 0
        for row in items:
            try:
                total += int(row[1])
            except Exception:
                pass

    full_name = (first_name or "").strip()
    if last_name:
        full_name = f"{full_name} {last_name}".strip()

    lines = [
        "👤 پنل پروفایل\n",
        f"📝 نام: {full_name or '—'}",
        f"🔗 یوزرنیم: @{username}" if username else "🔗 یوزرنیم: —",
        f"🆔 آیدی عددی: {user_id}",
        f"🌐 زبان تلگرام: {language_code or '—'}",
        f"🏙 شهر ربات: {city}",
        f"🎂 تاریخ تولد: {birth}",
        f"📊 کل استفاده: {total}",
    ]
    if items:
        lines.append("\nبیشترین بخش‌ها:")
        for row in items[:5]:
            try:
                k, v = row[0], row[1]
                lines.append(f"• {k}: {v}")
            except Exception:
                continue
    return "\n".join(lines)
