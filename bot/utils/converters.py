"""
مبدل تاریخ (شمسی ↔ میلادی ↔ قمری) و محاسبه سن دقیق
"""
import re
from datetime import datetime, date, timedelta
import jdatetime
from hijri_converter import Gregorian, Hijri
import pytz
from bot.config import config

tehran_tz = pytz.timezone(config.TIMEZONE)

HIJRI_MONTHS = {
    1: "محرم", 2: "صفر", 3: "ربیع‌الاول", 4: "ربیع‌الثانی",
    5: "جمادی‌الاول", 6: "جمادی‌الثانی", 7: "رجب", 8: "شعبان",
    9: "رمضان", 10: "شوال", 11: "ذی‌قعده", 12: "ذی‌الحجه"
}
HIJRI_MONTHS_REV = {v: k for k, v in HIJRI_MONTHS.items()}
# نام‌های رایج جایگزین
HIJRI_MONTHS_REV.update({
    "ربیع الاول": 3, "ربیع اول": 3,
    "ربیع الثانی": 4, "ربیع دوم": 4,
    "جمادی الاول": 5, "جمادی اول": 5,
    "جمادی الثانی": 6, "جمادی دوم": 6,
    "ذیقعده": 11, "ذی قعده": 11,
    "ذیالحجه": 12, "ذی الحجه": 12, "ذیحجه": 12,
})

PERSIAN_MONTHS = {
    1: "فروردین", 2: "اردیبهشت", 3: "خرداد", 4: "تیر",
    5: "مرداد", 6: "شهریور", 7: "مهر", 8: "آبان",
    9: "آذر", 10: "دی", 11: "بهمن", 12: "اسفند"
}
PERSIAN_MONTHS_REV = {v: k for k, v in PERSIAN_MONTHS.items()}

GREGORIAN_MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December"
}


def to_persian_num(num):
    mapping = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    return str(num).translate(mapping)


def _normalize(text: str) -> str:
    """تبدیل اعداد فارسی/عربی به انگلیسی و یکدست‌سازی جداکننده‌ها"""
    fa = "۰۱۲۳۴۵۶۷۸۹"
    ar = "٠١٢٣٤٥٦٧٨٩"
    en = "0123456789"
    table = str.maketrans(fa + ar, en + en)
    text = text.translate(table)
    text = text.replace("ـ", "-").replace("٫", ".").replace("،", ",")
    text = re.sub(r"[\/\-\.]", "/", text)
    return text.strip()


def parse_date(text: str):
    """
    تشخیص و پارس تاریخ از متن کاربر.
    خروجی: (نوع, year, month, day)  یا None
    نوع: 'shamsi' | 'gregorian' | 'hijri'
    """
    text = text.strip()
    if not text:
        return None

    normalized = _normalize(text)

    # الگوی عددی: 1403/5/18 یا 2024/08/09
    m = re.match(r"^(\d{3,4})\s*/\s*(\d{1,2})\s*/\s*(\d{1,2})$", normalized)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1200 <= y <= 1500:
            return ("shamsi", y, mo, d)
        if 1800 <= y <= 2100:
            return ("gregorian", y, mo, d)
        if 1300 <= y <= 1600:  # قمری نزدیک به شمسی
            # اگر ماه > ۱۲ نیست و سال در محدوده قمری است
            return ("hijri", y, mo, d)
        return None

    # الگوی با نام ماه شمسی: 18 مرداد 1403
    for name, num in PERSIAN_MONTHS_REV.items():
        if name in text:
            nums = re.findall(r"\d+", _normalize(text))
            if len(nums) >= 2:
                # معمولاً روز و سال
                day = int(nums[0])
                year = int(nums[-1])
                if 1200 <= year <= 1500 and 1 <= day <= 31:
                    return ("shamsi", year, num, day)
            break

    # الگوی با نام ماه قمری: 15 صفر 1446
    for name, num in HIJRI_MONTHS_REV.items():
        if name in text:
            nums = re.findall(r"\d+", _normalize(text))
            if len(nums) >= 2:
                day = int(nums[0])
                year = int(nums[-1])
                if 1300 <= year <= 1600 and 1 <= day <= 30:
                    return ("hijri", year, num, day)
            break

    return None


def convert_date(kind: str, year: int, month: int, day: int) -> str:
    """تبدیل تاریخ به هر سه سیستم و برگرداندن متن فرمت‌شده"""
    try:
        if kind == "shamsi":
            j = jdatetime.date(year, month, day)
            g = j.togregorian()
            h_info = _gregorian_to_hijri(g)
        elif kind == "gregorian":
            g = date(year, month, day)
            j = jdatetime.date.fromgregorian(date=g)
            h_info = _gregorian_to_hijri(g)
        elif kind == "hijri":
            h = Hijri(year, month, day)
            g = h.to_gregorian()
            g = date(g.year, g.month, g.day)
            j = jdatetime.date.fromgregorian(date=g)
            h_info = {
                "day": day,
                "month": month,
                "month_name": HIJRI_MONTHS.get(month, str(month)),
                "year": year,
            }
        else:
            return "❌ نوع تاریخ نامعتبر است."

        shamsi_str = (
            f"{to_persian_num(j.day)} {PERSIAN_MONTHS[j.month]} "
            f"{to_persian_num(j.year)}  ({to_persian_num(j.year)}/{to_persian_num(f'{j.month:02d}')}/{to_persian_num(f'{j.day:02d}')})"
        )
        miladi_str = f"{g.day} {GREGORIAN_MONTHS[g.month]} {g.year}  ({g.year}/{g.month:02d}/{g.day:02d})"
        hijri_str = (
            f"{to_persian_num(h_info['day'])} {h_info['month_name']} "
            f"{to_persian_num(h_info['year'])}"
        )

        return (
            f"✅ **نتیجه تبدیل تاریخ**\n\n"
            f"📅 **شمسی:** {shamsi_str}\n"
            f"📆 **میلادی:** {miladi_str}\n"
            f"🌙 **قمری:** {hijri_str}"
        )
    except Exception as e:
        return f"❌ تاریخ نامعتبر است.\nمثال: `1403/05/18` یا `2024/08/09` یا `15 صفر 1446`"


def _gregorian_to_hijri(g: date) -> dict:
    try:
        # هک یک‌روزه برای تطبیق رایج در ایران
        adjusted = g - timedelta(days=1)
        h = Gregorian(adjusted.year, adjusted.month, adjusted.day).to_hijri()
        return {
            "day": h.day,
            "month": h.month,
            "month_name": HIJRI_MONTHS.get(h.month, str(h.month)),
            "year": h.year,
        }
    except Exception:
        return {"day": 0, "month": 0, "month_name": "نامشخص", "year": 0}


def calculate_age(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> str:
    """
    محاسبه سن دقیق بر اساس تاریخ تولد شمسی.
    خروجی: سال، ماه، روز، ساعت، دقیقه
    """
    try:
        birth_j = jdatetime.datetime(year, month, day, hour, minute)
        birth_g = birth_j.togregorian()
        birth_aware = tehran_tz.localize(birth_g)

        now = datetime.now(tehran_tz)

        if birth_aware > now:
            return "❌ تاریخ تولد نمی‌تواند در آینده باشد."

        # محاسبه تفاوت دقیق
        delta = now - birth_aware
        total_seconds = int(delta.total_seconds())

        # سال و ماه با جابه‌جایی تقویم شمسی
        now_j = jdatetime.datetime.fromgregorian(datetime=now)
        years = now_j.year - birth_j.year
        months = now_j.month - birth_j.month
        days = now_j.day - birth_j.day

        if days < 0:
            months -= 1
            # تعداد روزهای ماه قبلی
            prev_month = now_j.month - 1 if now_j.month > 1 else 12
            prev_year = now_j.year if now_j.month > 1 else now_j.year - 1
            days_in_prev = jdatetime.date(prev_year, prev_month, 1).daysinmonth
            days += days_in_prev

        if months < 0:
            years -= 1
            months += 12

        # ساعت و دقیقه از باقی‌مانده ثانیه‌ها (تقریبی از زمان دقیق تولد)
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60

        # اگر فقط تاریخ داده شده (ساعت=۰)، ساعت و دقیقه را از نیمه‌شب حساب نکنیم
        # بلکه نشان دهیم «از نیمه‌شب امروز»
        time_part = ""
        if hour != 0 or minute != 0:
            time_part = (
                f"\n🕐 **ساعت:** {to_persian_num(hours)}\n"
                f"⏱ **دقیقه:** {to_persian_num(minutes)}"
            )
        else:
            # سن به روز کامل
            total_days = delta.days
            time_part = f"\n📆 **مجموع روزها:** {to_persian_num(f'{total_days:,}')}"

        birth_str = (
            f"{to_persian_num(day)} {PERSIAN_MONTHS[month]} {to_persian_num(year)}"
        )
        if hour or minute:
            birth_str += f" ساعت {to_persian_num(f'{hour:02d}')}:{to_persian_num(f'{minute:02d}')}"

        return (
            f"🎂 **سن دقیق شما**\n\n"
            f"📅 تاریخ تولد: {birth_str}\n\n"
            f"🗓 **سال:** {to_persian_num(years)}\n"
            f"🗓 **ماه:** {to_persian_num(months)}\n"
            f"🗓 **روز:** {to_persian_num(days)}"
            f"{time_part}"
        )
    except Exception:
        return (
            "❌ تاریخ نامعتبر است.\n"
            "مثال: `1375/03/15`\n"
            "یا با ساعت: `1375/03/15 14:30`"
        )


def parse_birth_datetime(text: str):
    """
    پارس تاریخ تولد شمسی.
    پشتیبانی از:
      1375/3/15
      1375/03/15 14:30
      15 فروردین 1375
    خروجی: (year, month, day, hour, minute) یا None
    """
    text = text.strip()
    normalized = _normalize(text)

    # با ساعت: 1375/3/15 14:30
    m = re.match(
        r"^(\d{3,4})\s*/\s*(\d{1,2})\s*/\s*(\d{1,2})(?:\s+(\d{1,2}):(\d{1,2}))?$",
        normalized,
    )
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        h = int(m.group(4)) if m.group(4) else 0
        mi = int(m.group(5)) if m.group(5) else 0
        if 1200 <= y <= 1500:
            return (y, mo, d, h, mi)
        return None

    # با نام ماه
    for name, num in PERSIAN_MONTHS_REV.items():
        if name in text:
            nums = re.findall(r"\d+", normalized)
            if len(nums) >= 2:
                day = int(nums[0])
                year = int(nums[-1])
                if 1200 <= year <= 1500:
                    return (year, num, day, 0, 0)
            break

    return None
