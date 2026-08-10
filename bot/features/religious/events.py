"""مناسبت‌های مذهبی قمری — نمایش تا یک ماه آینده"""
from datetime import datetime, timedelta
import jdatetime
from hijri_converter import Gregorian, Hijri
import pytz
from bot.config import config

tehran_tz = pytz.timezone(config.TIMEZONE)

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


def religious_countdown() -> str:
    now = datetime.now(tehran_tz)
    g = Gregorian(now.year, now.month, now.day)
    h = g.to_hijri()
    lines = ["🕌 **مناسبت‌های مذهبی (تا یک ماه)**\n"]
    lines.append(f"امروز قمری: {h.day}/{h.month}/{h.year}\n")

    found = []
    for month, day, name in RELIGIOUS_EVENTS:
        for year_offset in (0, 1):
            try:
                y = h.year + year_offset
                target_h = Hijri(y, month, day)
                if target_h < h:
                    continue
                target_g = target_h.to_gregorian()
                target_dt = datetime(target_g.year, target_g.month, target_g.day, tzinfo=tehran_tz)
                days = (target_dt - now).days
                if 0 <= days <= 31:
                    try:
                        jd = jdatetime.date.fromgregorian(date=target_g)
                        shamsi = f"{jd.year}/{jd.month}/{jd.day}"
                    except Exception:
                        shamsi = str(target_g)
                    found.append((days, name, shamsi, f"{day}/{month}/{y}"))
            except Exception:
                continue

    seen = set()
    unique = []
    for item in sorted(found, key=lambda x: x[0]):
        if item[1] not in seen:
            seen.add(item[1])
            unique.append(item)

    if not unique:
        lines.append("مناسبت ثبت‌شده‌ای در ۳۰ روز آینده یافت نشد.")
    else:
        for days, name, shamsi, qamari in unique[:15]:
            if days == 0:
                lines.append(f"• **{name}** — امروز ({qamari} قمری)")
            else:
                lines.append(f"• **{name}** — {days} روز دیگر\n  قمری: {qamari} | شمسی≈ {shamsi}")

    return "\n".join(lines)
