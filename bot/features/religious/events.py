"""مناسبت‌های مذهبی و قمری — نمایش مناسبت‌های ثبت‌شده در ۳۰ روز آینده."""
from datetime import datetime, timedelta

import jdatetime
import pytz
from hijri_converter import Gregorian

from bot.config import config
from bot.utils.events import hijri_events

tehran_tz = pytz.timezone(config.TIMEZONE)

# مناسبت‌های مهم و منتخب. علاوه بر این لیست، تمام مناسبت‌های موجود در
# bot.utils.events.hijri_events نیز بررسی می‌شوند تا مناسبت‌های قمری جا نیفتند.
RELIGIOUS_EVENTS = [
    (1, 1, "آغاز سال قمری / محرم"),
    (1, 9, "تاسوعای حسینی"),
    (1, 10, "عاشورای حسینی"),
    (2, 20, "اربعین حسینی"),
    (2, 28, "رحلت پیامبر (ص) و شهادت امام حسن (ع)"),
    (3, 8, "شهادت امام حسن عسکری (ع)"),
    (3, 17, "ولادت پیامبر (ص) و امام صادق (ع)"),
    (7, 13, "ولادت امام علی (ع)"),
    (7, 27, "مبعث پیامبر (ص)"),
    (8, 15, "ولادت امام زمان (عج)"),
    (9, 1, "آغاز ماه رمضان"),
    (9, 19, "ضربت خوردن امام علی (ع)"),
    (9, 21, "شهادت امام علی (ع)"),
    (9, 23, "شب قدر"),
    (10, 1, "عید فطر"),
    (10, 25, "شهادت امام جعفر صادق (ع)"),
    (12, 9, "روز عرفه"),
    (12, 10, "عید قربان"),
    (12, 18, "عید غدیر خم"),
]


def _to_shamsi(gregorian_date) -> str:
    """تبدیل تاریخ میلادی به شمسی برای نمایش."""
    try:
        jd = jdatetime.date.fromgregorian(date=gregorian_date)
        return f"{jd.year}/{jd.month:02d}/{jd.day:02d}"
    except Exception:
        return str(gregorian_date)


def _event_names_for_hijri(month: int, day: int):
    """برگرداندن نام مناسبت‌های ثبت‌شده برای یک تاریخ قمری."""
    names = []

    # منبع اصلی و کامل مناسبت‌های قمری پروژه.
    values = hijri_events.get(f"{month}-{day}", [])
    if isinstance(values, str):
        values = [values]

    for value in values:
        if value and str(value).strip():
            names.append(str(value).strip())

    # مناسبت‌های منتخب قدیمی پروژه را هم نگه می‌داریم تا چیزی حذف نشود.
    for event_month, event_day, name in RELIGIOUS_EVENTS:
        if event_month == month and event_day == day and name not in names:
            names.append(name)

    return names


def religious_countdown() -> str:
    """نمایش مناسبت‌های قمری ثبت‌شده در امروز و ۳۰ روز آینده.

    به‌جای بررسی یک فهرست محدود و محاسبه دستی فاصله ماه‌های قمری،
    تک‌تک ۳۱ روز میلادی از امروز تا پایان بازه بررسی می‌شوند و برای
    هر روز، تاریخ قمری واقعی همان روز از hijri_converter گرفته می‌شود.
    این روش تغییر ماه و سال قمری را نیز بدون محاسبه دستی مدیریت می‌کند.
    """
    now = datetime.now(tehran_tz)
    today = now.date()

    # تبدیل امروز به قمری فقط برای نمایش سربرگ.
    today_hijri = Gregorian(today.year, today.month, today.day).to_hijri()

    lines = ["🕌 **مناسبت‌های مذهبی و قمری (تا یک ماه)**\n"]
    lines.append(
        f"امروز قمری: {today_hijri.day}/{today_hijri.month}/{today_hijri.year}\n"
    )

    found = []

    # ۰ تا ۳۰ یعنی امروز + ۳۰ روز آینده.
    for offset in range(31):
        target_date = today + timedelta(days=offset)

        try:
            target_hijri = Gregorian(
                target_date.year,
                target_date.month,
                target_date.day,
            ).to_hijri()
        except Exception:
            continue

        names = _event_names_for_hijri(target_hijri.month, target_hijri.day)
        if not names:
            continue

        shamsi = _to_shamsi(target_date)
        qamari = (
            f"{target_hijri.day}/{target_hijri.month}/{target_hijri.year}"
        )

        for name in names:
            found.append((offset, name, shamsi, qamari))

    # حذف نام‌های تکراری فقط وقتی که همان مناسبت در چند تاریخ ثبت شده باشد.
    # اگر یک مناسبت در دو روز مختلف آمده باشد، اولین وقوع در بازه نمایش داده می‌شود.
    seen = set()
    unique = []
    for item in found:
        name = item[1]
        if name in seen:
            continue
        seen.add(name)
        unique.append(item)

    if not unique:
        lines.append("مناسبت قمری ثبت‌شده‌ای در ۳۰ روز آینده یافت نشد.")
        return "\n".join(lines)

    for days, name, shamsi, qamari in unique[:20]:
        if days == 0:
            lines.append(f"• **{name}** — امروز ({qamari} قمری)")
        else:
            lines.append(
                f"• **{name}** — {days} روز دیگر\n"
                f"  قمری: {qamari} | شمسی: {shamsi}"
            )

    return "\n".join(lines)
