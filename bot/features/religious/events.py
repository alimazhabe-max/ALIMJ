"""شمارش‌معکوس مناسبت‌های مذهبی"""
from datetime import datetime, timedelta
import jdatetime
from hijri_converter import Gregorian, Hijri
import pytz
from bot.config import config

tehran_tz = pytz.timezone(config.TIMEZONE)

RELIGIOUS_EVENTS = [
    (1, 1, "آغاز سال قمری / محرم"),
    (1, 10, "تاسوعا / عاشورا"),
    (3, 17, "ولادت پیامبر (ص)"),
    (7, 13, "ولادت امام علی (ع)"),
    (7, 27, "مبعث"),
    (8, 15, "ولادت امام زمان (عج)"),
    (9, 1, "آغاز رمضان"),
    (9, 21, "شهادت امام علی (ع)"),
    (9, 27, "شب قدر"),
    (10, 1, "عید فطر"),
    (12, 9, "روز عرفه"),
    (12, 10, "عید قربان"),
]


def religious_countdown() -> str:
    now = datetime.now(tehran_tz)
    g = Gregorian(now.year, now.month, now.day)
    h = g.to_hijri()
    lines = ["🕌 **مناسبت‌های مذهبی نزدیک**\n"]

    for month, day, name in RELIGIOUS_EVENTS:
        # تقریبی: فرض سال جاری یا بعدی
        try:
            target_h = Hijri(h.year, month, day)
            if target_h < h:
                target_h = Hijri(h.year + 1, month, day)
            target_g = target_h.to_gregorian()
            target_dt = datetime(target_g.year, target_g.month, target_g.day, tzinfo=tehran_tz)
            delta = target_dt - now
            days = delta.days
            if 0 <= days <= 90:
                lines.append(f"• {name}: **{days} روز** دیگر")
        except Exception:
            continue

    if len(lines) == 1:
        lines.append("مناسبت نزدیکی در ۹۰ روز آینده ثبت نشده.")
    return "\n".join(lines)
