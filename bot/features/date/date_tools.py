"""
تاریخ و زمان — همه ابزارها (۱ تا ۱۰ + شمارش‌معکوس سفارشی)
"""
import re
from datetime import datetime, date, timedelta
import jdatetime
from hijri_converter import Gregorian, Hijri
import pytz
from bot.config import config
from bot.utils.events import shamsi_events, hijri_events

tehran_tz = pytz.timezone(config.TIMEZONE)

PERSIAN_MONTHS = {
    1: "فروردین", 2: "اردیبهشت", 3: "خرداد", 4: "تیر",
    5: "مرداد", 6: "شهریور", 7: "مهر", 8: "آبان",
    9: "آذر", 10: "دی", 11: "بهمن", 12: "اسفند"
}
PERSIAN_MONTHS_REV = {v: k for k, v in PERSIAN_MONTHS.items()}
PERSIAN_WEEKDAYS = {
    0: "شنبه", 1: "یکشنبه", 2: "دوشنبه", 3: "سه‌شنبه",
    4: "چهارشنبه", 5: "پنجشنبه", 6: "جمعه"
}
GREGORIAN_MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December"
}
HIJRI_MONTHS = {
    1: "محرم", 2: "صفر", 3: "ربیع‌الاول", 4: "ربیع‌الثانی",
    5: "جمادی‌الاول", 6: "جمادی‌الثانی", 7: "رجب", 8: "شعبان",
    9: "رمضان", 10: "شوال", 11: "ذی‌قعده", 12: "ذی‌الحجه"
}
HIJRI_MONTHS_REV = {v: k for k, v in HIJRI_MONTHS.items()}
HIJRI_MONTHS_REV.update({
    "ربیع الاول": 3, "ربیع اول": 3, "ربیع الثانی": 4, "ربیع دوم": 4,
    "جمادی الاول": 5, "جمادی اول": 5, "جمادی الثانی": 6, "جمادی دوم": 6,
    "ذیقعده": 11, "ذی قعده": 11, "ذیالحجه": 12, "ذی الحجه": 12, "ذیحجه": 12,
})

ZODIAC = [
    (1, 1, 1, 20, "♑ بزغاله (جدی)"), (1, 21, 2, 19, "♒ دلو"),
    (2, 20, 3, 20, "♓ حوت"), (3, 21, 4, 20, "♈ حمل"),
    (4, 21, 5, 21, "♉ ثور"), (5, 22, 6, 21, "♊ جوزا"),
    (6, 22, 7, 22, "♋ سرطان"), (7, 23, 8, 22, "♌ اسد"),
    (8, 23, 9, 22, "♍ سنبله"), (9, 23, 10, 22, "♎ میزان"),
    (10, 23, 11, 21, "♏ عقرب"), (11, 22, 12, 21, "♐ قوس"),
    (12, 22, 12, 31, "♑ بزغاله (جدی)"),
]
CHINESE_ANIMALS = [
    "🐀 موش", "🐂 گاو", "🐅 ببر", "🐇 خرگوش", "🐉 اژدها", "🐍 مار",
    "🐎 اسب", "🐐 بز", "🐒 میمون", "🐓 خروس", "🐕 سگ", "🐖 خوک",
]

WORLD_CITIES = {
    "تهران": "Asia/Tehran", "دبی": "Asia/Dubai", "استانبول": "Europe/Istanbul",
    "لندن": "Europe/London", "پاریس": "Europe/Paris", "نیویورک": "America/New_York",
    "لس‌آنجلس": "America/Los_Angeles", "توکیو": "Asia/Tokyo", "پکن": "Asia/Shanghai",
    "مسکو": "Europe/Moscow", "سیدنی": "Australia/Sydney", "ریاض": "Asia/Riyadh",
}


def pn(num):
    return str(num).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _norm(text: str) -> str:
    fa, ar, en = "۰۱۲۳۴۵۶۷۸۹", "٠١٢٣٤٥٦٧٨٩", "0123456789"
    text = text.translate(str.maketrans(fa + ar, en + en))
    text = text.replace("ـ", "-").replace("٫", ".")
    return re.sub(r"[\/\-\.]", "/", text.strip())


def parse_shamsi(text: str):
    text = text.strip()
    n = _norm(text)
    m = re.match(r"^(\d{3,4})\s*/\s*(\d{1,2})\s*/\s*(\d{1,2})(?:\s+(\d{1,2}):(\d{1,2}))?$", n)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        h = int(m.group(4)) if m.group(4) else 0
        mi = int(m.group(5)) if m.group(5) else 0
        if 1200 <= y <= 1500:
            return (y, mo, d, h, mi)
    for name, num in PERSIAN_MONTHS_REV.items():
        if name in text:
            nums = re.findall(r"\d+", n)
            if len(nums) >= 2:
                day, year = int(nums[0]), int(nums[-1])
                if 1200 <= year <= 1500:
                    return (year, num, day, 0, 0)
            break
    return None


def parse_any_date(text: str):
    n = _norm(text.strip())
    m = re.match(r"^(\d{3,4})\s*/\s*(\d{1,2})\s*/\s*(\d{1,2})$", n)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1200 <= y <= 1500:
            return ("shamsi", y, mo, d)
        if 1800 <= y <= 2100:
            return ("gregorian", y, mo, d)
        if 1300 <= y <= 1600:
            return ("hijri", y, mo, d)
    for name, num in PERSIAN_MONTHS_REV.items():
        if name in text:
            nums = re.findall(r"\d+", n)
            if len(nums) >= 2:
                return ("shamsi", int(nums[-1]), num, int(nums[0]))
    for name, num in HIJRI_MONTHS_REV.items():
        if name in text:
            nums = re.findall(r"\d+", n)
            if len(nums) >= 2:
                return ("hijri", int(nums[-1]), num, int(nums[0]))
    return None


def _g2h(g: date) -> dict:
    try:
        adj = g - timedelta(days=1)
        h = Gregorian(adj.year, adj.month, adj.day).to_hijri()
        return {"day": h.day, "month": h.month, "month_name": HIJRI_MONTHS.get(h.month, str(h.month)), "year": h.year}
    except Exception:
        return {"day": 0, "month": 0, "month_name": "—", "year": 0}


# ── ۱. روزشمار تولد ──
def birthday_countdown(y, m, d) -> str:
    try:
        today = jdatetime.datetime.now().date()
        try:
            this_bd = jdatetime.date(today.year, m, d)
        except ValueError:
            this_bd = jdatetime.date(today.year, m, d - 1)
        if this_bd >= today:
            next_bd, next_age = this_bd, today.year - y
        else:
            try:
                next_bd = jdatetime.date(today.year + 1, m, d)
            except ValueError:
                next_bd = jdatetime.date(today.year + 1, m, d - 1)
            next_age = today.year - y + 1
        days_left = (next_bd - today).days
        cur_age = today.year - y - (0 if (today.month, today.day) >= (m, d) else 1)
        status = "🎉 **امروز تولد شماست!**" if days_left == 0 else f"⏳ **{pn(days_left)} روز** تا تولد بعدی"
        return (
            f"🎂 **روزشمار تولد**\n\n"
            f"📅 تولد: {pn(d)} {PERSIAN_MONTHS[m]} {pn(y)}\n"
            f"🗓 سن فعلی: {pn(cur_age)} سال\n\n{status}\n"
            f"🎈 {pn(next_bd.day)} {PERSIAN_MONTHS[next_bd.month]} {pn(next_bd.year)} → {pn(next_age)} ساله"
        )
    except Exception:
        return "❌ تاریخ نامعتبر.\nمثال: `1375/03/15`"


# ── ۲. برج + حیوان ──
def zodiac_animal(y, m, d) -> str:
    try:
        j = jdatetime.date(y, m, d)
        g = j.togregorian()
        zodiac = "نامشخص"
        for m1, d1, m2, d2, name in ZODIAC:
            if (g.month == m1 and g.day >= d1) or (g.month == m2 and g.day <= d2):
                zodiac = name
                break
        animal = CHINESE_ANIMALS[(y - 1399) % 12]  # 1403=اژدها، 1404=مار
        return (
            f"♈ **برج و حیوان سال**\n\n"
            f"📅 {pn(d)} {PERSIAN_MONTHS[m]} {pn(y)}\n"
            f"📆 {g.day} {GREGORIAN_MONTHS[g.month]} {g.year}\n\n"
            f"✨ برج فلکی: {zodiac}\n🐾 حیوان سال: {animal}"
        )
    except Exception:
        return "❌ تاریخ نامعتبر.\nمثال: `1375/03/15`"


# ── ۳. سن قمری + تکلیف ──
def lunar_age(y, m, d) -> str:
    try:
        birth_g = jdatetime.date(y, m, d).togregorian()
        hb = _g2h(birth_g)
        hn = _g2h(datetime.now(tehran_tz).date())
        hy = hn["year"] - hb["year"]
        hm = hn["month"] - hb["month"]
        hd = hn["day"] - hb["day"]
        if hd < 0:
            hm -= 1
            hd += 29
        if hm < 0:
            hy -= 1
            hm += 12

        def taklif(add):
            try:
                h = Hijri(hb["year"] + add, hb["month"], min(hb["day"], 28))
                g = h.to_gregorian()
                j = jdatetime.date.fromgregorian(date=date(g.year, g.month, g.day))
                return f"{pn(j.day)} {PERSIAN_MONTHS[j.month]} {pn(j.year)}"
            except Exception:
                return "—"

        return (
            f"🌙 **سن قمری و سن تکلیف**\n\n"
            f"📅 شمسی: {pn(d)} {PERSIAN_MONTHS[m]} {pn(y)}\n"
            f"🌙 قمری: {pn(hb['day'])} {hb['month_name']} {pn(hb['year'])}\n\n"
            f"🗓 سن قمری: {pn(hy)} سال و {pn(hm)} ماه و {pn(hd)} روز\n\n"
            f"👧 سن تکلیف دختران (۹ق): {taklif(9)}\n"
            f"👦 سن تکلیف پسران (۱۵ق): {taklif(15)}"
        )
    except Exception:
        return "❌ تاریخ نامعتبر.\nمثال: `1375/03/15`"


# ── ۴. اختلاف دو تاریخ (پیشرفته) ──
def _days_in_jmonth(year, month):
    """تعداد روز ماه شمسی (درست برای کبیسه)"""
    days = jdatetime.j_days_in_month[month - 1]
    if month == 12 and jdatetime.date(year, 1, 1).isleap():
        days = 30
    return days


def _ymd_diff(a, b):
    """اختلاف سال/ماه/روز بین دو jdatetime.date (a <= b)"""
    years = b.year - a.year
    months = b.month - a.month
    days = b.day - a.day
    if days < 0:
        months -= 1
        pm = b.month - 1 if b.month > 1 else 12
        py = b.year if b.month > 1 else b.year - 1
        days += _days_in_jmonth(py, pm)
    if months < 0:
        years -= 1
        months += 12
    return years, months, days


def _g2h_safe(g):
    try:
        h = Gregorian(g.year, g.month, g.day).to_hijri()
        return h.year, h.month, h.day, HIJRI_MONTHS.get(h.month, str(h.month))
    except Exception:
        return None, None, None, "—"


def date_diff(y1, m1, d1, y2, m2, d2) -> str:
    try:
        a = jdatetime.date(y1, m1, d1)
        b = jdatetime.date(y2, m2, d2)
        swapped = False
        if a > b:
            a, b = b, a
            y1, m1, d1, y2, m2, d2 = y2, m2, d2, y1, m1, d1
            swapped = True

        total = (b - a).days
        years, months, days = _ymd_diff(a, b)
        total_months = years * 12 + months
        weeks = total // 7
        rem_days = total % 7
        hours = total * 24
        minutes = hours * 60

        ga = a.togregorian()
        gb = b.togregorian()
        ha = _g2h_safe(ga)
        hb = _g2h_safe(gb)

        wd_a = PERSIAN_WEEKDAYS[a.weekday()]
        wd_b = PERSIAN_WEEKDAYS[b.weekday()]

        # روزهای کاری تقریبی (۵/۷)
        workdays = int(total * 5 / 7)

        # مناسبت‌های بین دو تاریخ (نمونه محدود)
        event_count = 0
        try:
            cur = a
            while cur <= b and event_count < 50:
                key = f"{cur.month}-{cur.day}"
                evs = shamsi_events.get(key, [])
                for e in evs:
                    if "هیچ مناسبت" not in e:
                        event_count += 1
                cur = cur + timedelta(days=1)
        except Exception:
            event_count = 0

        direction = ""
        if swapped:
            direction = "⚠️ ترتیب ورودی برعکس بود؛ از تاریخ کوچک‌تر به بزرگ‌تر محاسبه شد.\n\n"

        lines = [
            "📅 **اختلاف دو تاریخ (پیشرفته)**\n",
            direction,
            f"🔹 از: {wd_a} {pn(d1)} {PERSIAN_MONTHS[m1]} {pn(y1)}",
            f"   📆 میلادی: {ga.day} {GREGORIAN_MONTHS[ga.month]} {ga.year}",
            f"   🌙 قمری: {pn(ha[2])} {ha[3]} {pn(ha[0])}" if ha[0] else "   🌙 قمری: —",
            "",
            f"🔸 تا: {wd_b} {pn(d2)} {PERSIAN_MONTHS[m2]} {pn(y2)}",
            f"   📆 میلادی: {gb.day} {GREGORIAN_MONTHS[gb.month]} {gb.year}",
            f"   🌙 قمری: {pn(hb[2])} {hb[3]} {pn(hb[0])}" if hb[0] else "   🌙 قمری: —",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            f"🗓 دقیق: **{pn(years)}** سال و **{pn(months)}** ماه و **{pn(days)}** روز",
            f"📊 مجموع ماه‌ها: {pn(total_months)} ماه",
            f"📆 مجموع روزها: {pn(f'{total:,}')} روز",
            f"🗓 هفته‌ها: {pn(weeks)} هفته و {pn(rem_days)} روز",
            f"🕐 ساعت تقریبی: {pn(f'{hours:,}')} ساعت",
            f"⏱ دقیقه تقریبی: {pn(f'{minutes:,}')} دقیقه",
            f"💼 روز کاری تقریبی: {pn(f'{workdays:,}')} روز",
        ]
        if event_count:
            lines.append(f"📌 مناسبت‌های ثبت‌شده در این بازه: حدود {pn(event_count)}")
        lines.append("")
        lines.append(f"📈 میانگین: حدود {pn(round(total / 365.25, 2))} سال خورشیدی")
        return "\n".join(lines)
    except Exception:
        return "❌ فرمت: `1375/03/15 1403/05/18`"


def parse_two_dates(text: str):
    matches = re.findall(r"(\d{3,4})\s*/\s*(\d{1,2})\s*/\s*(\d{1,2})", _norm(text))
    if len(matches) >= 2:
        a = tuple(int(x) for x in matches[0])
        b = tuple(int(x) for x in matches[1])
        if 1200 <= a[0] <= 1500 and 1200 <= b[0] <= 1500:
            return a, b
    return None


# ── ۵. اختلاف سن دو نفر (پیشرفته) ──
def age_diff(y1, m1, d1, y2, m2, d2) -> str:
    try:
        today = jdatetime.datetime.now().date()
        a = jdatetime.date(y1, m1, d1)  # نفر اول
        b = jdatetime.date(y2, m2, d2)  # نفر دوم

        # سن هر نفر تا امروز
        def age_until(birth, until):
            if birth > until:
                return None
            return _ymd_diff(birth, until)

        age_a = age_until(a, today)
        age_b = age_until(b, today)
        if age_a is None or age_b is None:
            return "❌ تاریخ تولد نمی‌تواند در آینده باشد."

        # اختلاف تولدها
        older, younger = (a, b) if a <= b else (b, a)
        older_label = "نفر اول" if a <= b else "نفر دوم"
        younger_label = "نفر دوم" if a <= b else "نفر اول"
        dy, dm, dd = _ymd_diff(older, younger)
        total_days = (younger - older).days

        # سن قمری تقریبی
        def lunar_years(birth):
            days_alive = (today - birth).days
            return round(days_alive / 354.367, 1)

        # درصد عمر (فرض ۷۵ سال)
        def life_pct(birth):
            days_alive = (today - birth).days
            return min(100, round(days_alive / (75 * 365.25) * 100, 1))

        ga = a.togregorian()
        gb = b.togregorian()

        lines = [
            "👥 **اختلاف سن دو نفر (پیشرفته)**\n",
            f"👤 نفر اول: {pn(d1)} {PERSIAN_MONTHS[m1]} {pn(y1)}",
            f"   سن فعلی: {pn(age_a[0])} سال و {pn(age_a[1])} ماه و {pn(age_a[2])} روز",
            f"   سن قمری ≈ {pn(lunar_years(a))} سال | عمر ≈ {pn(life_pct(a))}٪",
            f"   میلادی: {ga.day} {GREGORIAN_MONTHS[ga.month]} {ga.year}",
            "",
            f"👤 نفر دوم: {pn(d2)} {PERSIAN_MONTHS[m2]} {pn(y2)}",
            f"   سن فعلی: {pn(age_b[0])} سال و {pn(age_b[1])} ماه و {pn(age_b[2])} روز",
            f"   سن قمری ≈ {pn(lunar_years(b))} سال | عمر ≈ {pn(life_pct(b))}٪",
            f"   میلادی: {gb.day} {GREGORIAN_MONTHS[gb.month]} {gb.year}",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            f"🏆 بزرگ‌تر: **{older_label}**",
            f"📏 اختلاف سن: **{pn(dy)}** سال و **{pn(dm)}** ماه و **{pn(dd)}** روز",
            f"📆 اختلاف تولد: {pn(f'{total_days:,}')} روز ≈ {pn(total_days // 7)} هفته",
            f"📊 اختلاف به ماه: {pn(dy * 12 + dm)} ماه",
        ]

        # کی اختلاف به عدد رند می‌رسد؟
        # مثلاً وقتی اختلاف دقیقاً N سال کامل شود (از الان به بعد معنا ندارد چون ثابت است)
        # به‌جای آن: چند سال دیگر نفر کوچک‌تر به سن فعلی نفر بزرگ‌تر می‌رسد
        if a != b:
            older_age_y = age_a[0] if a <= b else age_b[0]
            younger_birth = younger
            # تاریخ رسیدن کوچک‌تر به سن فعلی بزرگ‌تر
            target_y = younger_birth.year + older_age_y
            try:
                target = jdatetime.date(target_y, younger_birth.month, younger_birth.day)
                if target < today:
                    target = jdatetime.date(target_y + 1, younger_birth.month, younger_birth.day)
                left = (target - today).days
                if left >= 0:
                    lines.append(
                        f"\n🎯 {younger_label} حدود {pn(left)} روز دیگر "
                        f"به سن فعلی {older_label} می‌رسد "
                        f"({pn(target.day)} {PERSIAN_MONTHS[target.month]} {pn(target.year)})"
                    )
            except Exception:
                pass

        # نسبت سنی
        days_a = (today - a).days
        days_b = (today - b).days
        if min(days_a, days_b) > 0:
            ratio = max(days_a, days_b) / min(days_a, days_b)
            lines.append(f"📐 نسبت سنی: {pn(round(ratio, 2))} برابر")

        return "\n".join(lines)
    except Exception:
        return "❌ فرمت: `1375/03/15 1380/06/20`"


# ── ۶. تبدیل تاریخ با روز هفته ──
def convert_with_weekday(kind, y, m, d) -> str:
    try:
        if kind == "shamsi":
            j = jdatetime.date(y, m, d)
            g = j.togregorian()
            h = _g2h(g)
        elif kind == "gregorian":
            g = date(y, m, d)
            j = jdatetime.date.fromgregorian(date=g)
            h = _g2h(g)
        else:
            hh = Hijri(y, m, d)
            gg = hh.to_gregorian()
            g = date(gg.year, gg.month, gg.day)
            j = jdatetime.date.fromgregorian(date=g)
            h = {"day": d, "month": m, "month_name": HIJRI_MONTHS.get(m, str(m)), "year": y}
        wd = PERSIAN_WEEKDAYS[j.weekday()]
        j_num = f"{pn(j.year)}/{pn(f'{j.month:02d}')}/{pn(f'{j.day:02d}')}"
        g_num = f"{g.year}/{g.month:02d}/{g.day:02d}"
        hm = pn(f"{h['month']:02d}")
        hd = pn(f"{h['day']:02d}")
        h_num = f"{pn(h['year'])}/{hm}/{hd}"
        return (
            f"✅ **تبدیل تاریخ**\n\n"
            f"📅 شمسی: {wd} {pn(j.day)} {PERSIAN_MONTHS[j.month]} {pn(j.year)}  ({j_num})\n"
            f"📆 میلادی: {g.strftime('%A')} {g.day} {GREGORIAN_MONTHS[g.month]} {g.year}  ({g_num})\n"
            f"🌙 قمری: {pn(h['day'])} {h['month_name']} {pn(h['year'])}  ({h_num})"
        )
    except Exception:
        return "❌ تاریخ نامعتبر.\nمثال: `1403/05/18` یا `2024/08/09`"


# ── ۷. تقویم ماه کامل ──
def month_calendar(year=None, month=None) -> str:
    try:
        today = jdatetime.datetime.now().date()
        year = year or today.year
        month = month or today.month
        first = jdatetime.date(year, month, 1)
        # jdatetime.j_days_in_month یک لیست است نه تابع
        days_in = jdatetime.j_days_in_month[month - 1]
        if month == 12 and jdatetime.date(year, 1, 1).isleap():
            days_in = 30
        start_wd = first.weekday()  # 0=شنبه
        lines = [f"📅 **{PERSIAN_MONTHS[month]} {pn(year)}**\n", "ش ی د س چ پ ج"]
        row = ["  "] * start_wd
        for day in range(1, days_in + 1):
            mark = f"{day:2d}"
            if day == today.day and month == today.month and year == today.year:
                mark = f"[{day}]"
            row.append(f"{mark:>3}")
            if len(row) == 7:
                lines.append(" ".join(row))
                row = []
        if row:
            lines.append(" ".join(row))
        # مناسبت‌های ماه
        evs = []
        for day in range(1, days_in + 1):
            key = f"{month}-{day}"
            for e in shamsi_events.get(key, []):
                if "هیچ مناسبت" not in e:
                    evs.append(f"• {pn(day)}: {e}")
        if evs:
            lines.append("\n📌 مناسبت‌ها:")
            lines.extend(evs[:15])
        return "\n".join(lines)
    except Exception as e:
        return f"❌ خطا: {e}"


# ── ۸. مناسبت‌یاب ──
def search_events(query: str) -> str:
    q = query.strip()
    if len(q) < 2:
        return "❌ حداقل ۲ حرف بنویسید."
    today = jdatetime.datetime.now().date()
    results = []

    # شمسی با روز مانده
    for key, evs in shamsi_events.items():
        try:
            m, d = map(int, key.split("-"))
        except Exception:
            continue
        for e in evs:
            if q not in e or "هیچ مناسبت" in e:
                continue
            # امسال یا سال بعد
            try:
                target = jdatetime.date(today.year, m, d)
            except Exception:
                continue
            if target < today:
                try:
                    target = jdatetime.date(today.year + 1, m, d)
                except Exception:
                    continue
            days = (target - today).days
            when = "امروز" if days == 0 else f"{pn(days)} روز مانده"
            results.append((days, f"• {e}\n  📅 {pn(d)} {PERSIAN_MONTHS[m]} — {when}"))

    # قمری با روز مانده
    try:
        g = today.togregorian()
        h = Gregorian(g.year, g.month, g.day).to_hijri()
    except Exception:
        h = None
    if h:
        for key, evs in hijri_events.items():
            try:
                m, d = map(int, key.split("-"))
            except Exception:
                continue
            for e in evs:
                if q not in e:
                    continue
                for yoff in (0, 1):
                    try:
                        th = Hijri(h.year + yoff, m, d)
                        if th < h:
                            continue
                        tg = th.to_gregorian()
                        tj = jdatetime.date.fromgregorian(date=tg)
                        days = (tj - today).days
                        if days < 0:
                            continue
                        when = "امروز" if days == 0 else f"{pn(days)} روز مانده"
                        results.append((days, f"• {e}\n  🌙 {pn(d)} {HIJRI_MONTHS.get(m, m)} قمری — {when}"))
                        break
                    except Exception:
                        continue

    if not results:
        return f"❌ مناسبتی با «{q}» پیدا نشد."
    results.sort(key=lambda x: x[0])
    lines = [f"🔍 مناسبت‌یاب: «{q}»\n"]
    for _, line in results[:20]:
        lines.append(line)
    return "\n".join(lines)


# ── ۹. شمارش‌معکوس نوروز ──
def nowruz_countdown() -> str:
    today = jdatetime.datetime.now().date()
    year = today.year if (today.month, today.day) < (1, 1) else today.year + 1
    # اگر هنوز به ۱ فروردین نرسیده‌ایم
    if today.month == 1 and today.day == 1:
        return "🎉 **امروز نوروز است! سال نو مبارک**"
    target = jdatetime.date(today.year + (0 if today.month < 1 or (today.month == 1 and today.day == 1) else 1), 1, 1)
    if today >= jdatetime.date(today.year, 1, 1) and not (today.month == 1 and today.day == 1):
        target = jdatetime.date(today.year + 1, 1, 1)
    days = (target - today).days
    return (
        f"🌸 **شمارش‌معکوس نوروز**\n\n"
        f"⏳ {pn(days)} روز تا ۱ فروردین {pn(target.year)}\n"
        f"📅 تحویل سال: ۱ فروردین {pn(target.year)}"
    )


# ── ۱۰. ساعت جهانی ──
def world_clock() -> str:
    now_utc = datetime.now(pytz.UTC)
    lines = ["🌍 **ساعت جهانی**\n"]
    for name, tz_name in WORLD_CITIES.items():
        tz = pytz.timezone(tz_name)
        local = now_utc.astimezone(tz)
        lines.append(f"• {name}: {local.strftime('%H:%M')} ({local.strftime('%d/%m')})")
    return "\n".join(lines)


# ── شمارش‌معکوس سفارشی ──
def custom_countdown(y, m, d, label="رویداد") -> str:
    try:
        today = jdatetime.datetime.now().date()
        target = jdatetime.date(y, m, d)
        delta = (target - today).days
        if delta > 0:
            return f"⏳ **شمارش‌معکوس: {label}**\n\n{pn(delta)} روز مانده\n📅 {pn(d)} {PERSIAN_MONTHS[m]} {pn(y)}"
        if delta == 0:
            return f"🎉 **امروز همان روز است: {label}**"
        return f"📅 **{label}** {pn(abs(delta))} روز پیش بوده است."
    except Exception:
        return "❌ تاریخ نامعتبر.\nمثال: `1405/01/01 نوروز`"


def parse_countdown(text: str):
    p = parse_shamsi(text)
    if not p:
        # تاریخ + برچسب
        n = _norm(text)
        m = re.search(r"(\d{3,4})\s*/\s*(\d{1,2})\s*/\s*(\d{1,2})", n)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            label = re.sub(r"\d{3,4}\s*[/\-\.]\s*\d{1,2}\s*[/\-\.]\s*\d{1,2}", "", text).strip() or "رویداد"
            return (y, mo, d, label)
        return None
    y, m, d, _, _ = p
    label = re.sub(r"\d{3,4}\s*[/\-\.]\s*\d{1,2}\s*[/\-\.]\s*\d{1,2}", "", text).strip() or "رویداد"
    return (y, m, d, label)
