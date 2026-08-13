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
            f"{to_persian_num(j.year)}  "
            f"({to_persian_num(j.year)}/{to_persian_num(f'{j.month:02d}')}/{to_persian_num(f'{j.day:02d}')})"
        )
        miladi_str = f"{g.day} {GREGORIAN_MONTHS[g.month]} {g.year}  ({g.year}/{g.month:02d}/{g.day:02d})"
        hy = to_persian_num(h_info["year"])
        hm = to_persian_num(f"{h_info['month']:02d}")
        hd = to_persian_num(f"{h_info['day']:02d}")
        hijri_str = (
            f"{to_persian_num(h_info['day'])} {h_info['month_name']} "
            f"{hy}  ({hy}/{hm}/{hd})"
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
        # بدون هک یک‌روزه — مطابق استاندارد و اکثر تقویم‌ها
        h = Gregorian(g.year, g.month, g.day).to_hijri()
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


# ───────────────── برج فلکی ─────────────────

ZODIAC = [
    # (ماه شروع, روز شروع, ماه پایان, روز پایان, نام)
    (1, 1, 1, 20, "♑ بزغاله (جدی)"),
    (1, 21, 2, 19, "♒ دلو"),
    (2, 20, 3, 20, "♓ حوت"),
    (3, 21, 4, 20, "♈ حمل (فروردین)"),
    (4, 21, 5, 21, "♉ ثور"),
    (5, 22, 6, 21, "♊ جوزا"),
    (6, 22, 7, 22, "♋ سرطان"),
    (7, 23, 8, 22, "♌ اسد"),
    (8, 23, 9, 22, "♍ سنبله"),
    (9, 23, 10, 22, "♎ میزان"),
    (10, 23, 11, 21, "♏ عقرب"),
    (11, 22, 12, 21, "♐ قوس"),
    (12, 22, 12, 31, "♑ بزغاله (جدی)"),
]

# حیوان سال چینی/ایرانی (۱۲ ساله) — بر اساس سال شمسی
# سال ۱۳۴۸ = خروس ... مرجع رایج
CHINESE_ANIMALS = [
    "🐀 موش", "🐂 گاو", "🐅 ببر", "🐇 خرگوش",
    "🐉 اژدها", "🐍 مار", "🐎 اسب", "🐐 بز",
    "🐒 میمون", "🐓 خروس", "🐕 سگ", "🐖 خوک",
]


def get_zodiac(month: int, day: int) -> str:
    """برج فلکی بر اساس ماه و روز میلادی"""
    for m1, d1, m2, d2, name in ZODIAC:
        if (month == m1 and day >= d1) or (month == m2 and day <= d2):
            if m1 == m2 or (month == m1 and day >= d1) or (month == m2 and day <= d2):
                return name
    return "نامشخص"


def get_zodiac_from_shamsi(year: int, month: int, day: int) -> str:
    try:
        j = jdatetime.date(year, month, day)
        g = j.togregorian()
        return get_zodiac(g.month, g.day)
    except Exception:
        return "نامشخص"


def get_animal_year(shamsi_year: int) -> str:
    """حیوان سال بر اساس سال شمسی (چرخه ۱۲ ساله)"""
    # سال ۱۳۰۹ = اسب (شاخص رایج)
    idx = (shamsi_year - 1309) % 12
    return CHINESE_ANIMALS[idx]


def zodiac_and_animal(year: int, month: int, day: int) -> str:
    """برج فلکی + حیوان سال تولد"""
    try:
        zodiac = get_zodiac_from_shamsi(year, month, day)
        animal = get_animal_year(year)
        j = jdatetime.date(year, month, day)
        g = j.togregorian()
        return (
            f"♈ **برج و حیوان سال تولد**\n\n"
            f"📅 تولد: {to_persian_num(day)} {PERSIAN_MONTHS[month]} {to_persian_num(year)}\n"
            f"📆 میلادی: {g.day} {GREGORIAN_MONTHS[g.month]} {g.year}\n\n"
            f"✨ **برج فلکی:** {zodiac}\n"
            f"🐾 **حیوان سال:** {animal}"
        )
    except Exception:
        return "❌ تاریخ نامعتبر است.\nمثال: `1375/03/15`"


# ───────────────── روزشمار تولد ─────────────────

def birthday_countdown(year: int, month: int, day: int) -> str:
    """چند روز تا تولد بعدی + سن بعدی"""
    try:
        now_j = jdatetime.datetime.now(tehran_tz)
        today = now_j.date()

        # تولد امسال
        try:
            this_year_bd = jdatetime.date(today.year, month, day)
        except ValueError:
            # ۲۹ اسفند در سال غیرکبیسه
            this_year_bd = jdatetime.date(today.year, month, day - 1)

        if this_year_bd >= today:
            next_bd = this_year_bd
            next_age = today.year - year
        else:
            try:
                next_bd = jdatetime.date(today.year + 1, month, day)
            except ValueError:
                next_bd = jdatetime.date(today.year + 1, month, day - 1)
            next_age = today.year - year + 1

        delta = next_bd - today
        days_left = delta.days

        current_age = today.year - year
        if (today.month, today.day) < (month, day):
            current_age -= 1

        if days_left == 0:
            status = "🎉 **امروز تولد شماست! تولدت مبارک**"
        else:
            status = f"⏳ **{to_persian_num(days_left)} روز** تا تولد بعدی"

        return (
            f"🎂 **روزشمار تولد**\n\n"
            f"📅 تاریخ تولد: {to_persian_num(day)} {PERSIAN_MONTHS[month]} {to_persian_num(year)}\n"
            f"🗓 سن فعلی: {to_persian_num(current_age)} سال\n\n"
            f"{status}\n"
            f"🎈 در تاریخ {to_persian_num(next_bd.day)} {PERSIAN_MONTHS[next_bd.month]} "
            f"{to_persian_num(next_bd.year)} → {to_persian_num(next_age)} ساله می‌شوید"
        )
    except Exception:
        return "❌ تاریخ نامعتبر است.\nمثال: `1375/03/15`"


# ───────────────── سن قمری و سن تکلیف ─────────────────

def lunar_age(year: int, month: int, day: int) -> str:
    """سن قمری + تاریخ رسیدن به ۹ و ۱۵ سال قمری (سن تکلیف)"""
    try:
        birth_j = jdatetime.date(year, month, day)
        birth_g = birth_j.togregorian()
        h_birth = _gregorian_to_hijri(birth_g)

        now = datetime.now(tehran_tz)
        now_g = now.date()
        h_now = _gregorian_to_hijri(now_g)

        # سن قمری تقریبی (سال قمری ≈ ۳۵۴ روز)
        birth_h_approx = Hijri(h_birth["year"], h_birth["month"], min(h_birth["day"], 28))
        now_h_approx = Hijri(h_now["year"], h_now["month"], min(h_now["day"], 28))

        # محاسبه سال/ماه/روز قمری
        hy = h_now["year"] - h_birth["year"]
        hm = h_now["month"] - h_birth["month"]
        hd = h_now["day"] - h_birth["day"]
        if hd < 0:
            hm -= 1
            hd += 29  # تقریب ماه قمری
        if hm < 0:
            hy -= 1
            hm += 12

        # تاریخ رسیدن به ۹ و ۱۵ سال قمری
        taklif_9 = None
        taklif_15 = None
        try:
            h9 = Hijri(h_birth["year"] + 9, h_birth["month"], min(h_birth["day"], 28))
            g9 = h9.to_gregorian()
            j9 = jdatetime.date.fromgregorian(date=date(g9.year, g9.month, g9.day))
            taklif_9 = f"{to_persian_num(j9.day)} {PERSIAN_MONTHS[j9.month]} {to_persian_num(j9.year)}"
        except Exception:
            taklif_9 = "—"

        try:
            h15 = Hijri(h_birth["year"] + 15, h_birth["month"], min(h_birth["day"], 28))
            g15 = h15.to_gregorian()
            j15 = jdatetime.date.fromgregorian(date=date(g15.year, g15.month, g15.day))
            taklif_15 = f"{to_persian_num(j15.day)} {PERSIAN_MONTHS[j15.month]} {to_persian_num(j15.year)}"
        except Exception:
            taklif_15 = "—"

        return (
            f"🌙 **سن قمری و سن تکلیف**\n\n"
            f"📅 تولد شمسی: {to_persian_num(day)} {PERSIAN_MONTHS[month]} {to_persian_num(year)}\n"
            f"🌙 تولد قمری: {to_persian_num(h_birth['day'])} {h_birth['month_name']} {to_persian_num(h_birth['year'])}\n\n"
            f"🗓 **سن قمری:** {to_persian_num(hy)} سال و {to_persian_num(hm)} ماه و {to_persian_num(hd)} روز\n\n"
            f"👧 **سن تکلیف دختران (۹ قمری):** {taklif_9}\n"
            f"👦 **سن تکلیف پسران (۱۵ قمری):** {taklif_15}"
        )
    except Exception:
        return "❌ تاریخ نامعتبر است.\nمثال: `1375/03/15`"


# ───────────────── اختلاف دو تاریخ ─────────────────

def date_diff(y1, m1, d1, y2, m2, d2, kind="shamsi") -> str:
    """فاصله بین دو تاریخ شمسی"""
    try:
        if kind == "shamsi":
            a = jdatetime.date(y1, m1, d1)
            b = jdatetime.date(y2, m2, d2)
        else:
            a = jdatetime.date.fromgregorian(date=date(y1, m1, d1))
            b = jdatetime.date.fromgregorian(date=date(y2, m2, d2))

        if a > b:
            a, b = b, a
            y1, m1, d1, y2, m2, d2 = y2, m2, d2, y1, m1, d1

        delta = b - a
        total_days = delta.days

        years = b.year - a.year
        months = b.month - a.month
        days = b.day - a.day
        if days < 0:
            months -= 1
            prev_m = b.month - 1 if b.month > 1 else 12
            prev_y = b.year if b.month > 1 else b.year - 1
            days += jdatetime.date(prev_y, prev_m, 1).daysinmonth
        if months < 0:
            years -= 1
            months += 12

        weeks = total_days // 7

        return (
            f"📅 **اختلاف دو تاریخ**\n\n"
            f"از: {to_persian_num(d1)} {PERSIAN_MONTHS.get(m1, m1)} {to_persian_num(y1)}\n"
            f"تا: {to_persian_num(d2)} {PERSIAN_MONTHS.get(m2, m2)} {to_persian_num(y2)}\n\n"
            f"🗓 **{to_persian_num(years)}** سال و **{to_persian_num(months)}** ماه و **{to_persian_num(days)}** روز\n"
            f"📆 مجموع: **{to_persian_num(f'{total_days:,}')}** روز\n"
            f"🗓 حدود **{to_persian_num(weeks)}** هفته"
        )
    except Exception:
        return (
            "❌ تاریخ نامعتبر است.\n"
            "فرمت: `1375/03/15 1403/05/18`\n"
            "(دو تاریخ شمسی با فاصله)"
        )


def parse_two_dates(text: str):
    """پارس دو تاریخ شمسی از یک متن"""
    normalized = _normalize(text)
    matches = re.findall(r"(\d{3,4})\s*/\s*(\d{1,2})\s*/\s*(\d{1,2})", normalized)
    if len(matches) >= 2:
        a = tuple(int(x) for x in matches[0])
        b = tuple(int(x) for x in matches[1])
        if 1200 <= a[0] <= 1500 and 1200 <= b[0] <= 1500:
            return a, b
    return None
