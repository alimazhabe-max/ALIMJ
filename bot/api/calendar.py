"""
bot/api/calendar.py  — نسخه اصلاح‌شده (بدون هک یک‌روزه)
تاریخ قمری دقیقاً مطابق استاندارد hijri_converter / Umm al-Qura
"""

import jdatetime
from hijri_converter import Gregorian
from datetime import timedelta
from bot.utils.events import shamsi_events, hijri_events


def get_today_tehran():
    import pytz
    from datetime import datetime
    tehran_tz = pytz.timezone('Asia/Tehran')
    now = datetime.now(tehran_tz)
    return jdatetime.datetime.fromgregorian(datetime=now).date()


def get_hijri_date(g_date):
    """
    تبدیل تاریخ میلادی به قمری بدون کم کردن یک روز.
    این باعث می‌شود برای ۱۴ آگوست ۲۰۲۶ → ۱ ربیع‌الاول ۱۴۴۸ شود
    (هم‌خوان با اکثر تقویم‌های دیگر).
    """
    try:
        # بدون هک یک‌روزه
        hijri = Gregorian(g_date.year, g_date.month, g_date.day).to_hijri()
        hijri_months = {
            1: "محرم", 2: "صفر", 3: "ربیع‌الاول", 4: "ربیع‌الثانی",
            5: "جمادی‌الاول", 6: "جمادی‌الثانی", 7: "رجب", 8: "شعبان",
            9: "رمضان", 10: "شوال", 11: "ذی‌قعده", 12: "ذی‌الحجه"
        }
        return {
            "day": hijri.day,
            "month": hijri.month,
            "month_name": hijri_months[hijri.month],
            "year": hijri.year,
            "full": f"{hijri.day} {hijri_months[hijri.month]} {hijri.year}"
        }
    except Exception:
        return {"day": 0, "month": 0, "month_name": "نامشخص", "year": 0, "full": "نامشخص"}


def get_shamsi_events(year, month, day):
    key = f"{month}-{day}"
    return shamsi_events.get(key, ["هیچ مناسبت خاصی ثبت نشده است."])


def get_hijri_events(hijri_month, hijri_day):
    key = f"{hijri_month}-{hijri_day}"
    return hijri_events.get(key, ["هیچ مناسبت قمری خاصی ثبت نشده است."])
