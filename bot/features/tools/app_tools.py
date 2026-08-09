"""
ابزارهای کاربردی — واحد، ماشین‌حساب، پسورد، شمارش، BMI، یادآوری، یادداشت
"""
import re
import random
import string
import math
from datetime import datetime, timedelta
import jdatetime
import pytz
from bot.config import config

tehran_tz = pytz.timezone(config.TIMEZONE)


def pn(n):
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


# ── ۲۶. تبدیل واحد ──
UNIT_CONV = {
    # طول → متر
    "km": 1000, "کیلومتر": 1000, "m": 1, "متر": 1,
    "cm": 0.01, "سانتی‌متر": 0.01, "mm": 0.001, "میلی‌متر": 0.001,
    "mile": 1609.34, "مایل": 1609.34, "ft": 0.3048, "فوت": 0.3048,
    "inch": 0.0254, "اینچ": 0.0254,
    # وزن → گرم
    "kg": 1000, "کیلوگرم": 1000, "کیلو": 1000, "g": 1, "گرم": 1,
    "mg": 0.001, "میلی‌گرم": 0.001, "lb": 453.592, "پوند": 453.592,
    "oz": 28.3495, "اونس": 28.3495,
    # حجم → لیتر
    "l": 1, "لیتر": 1, "ml": 0.001, "میلی‌لیتر": 0.001,
    "gal": 3.78541, "گالن": 3.78541,
}

TEMP_UNITS = {"c", "f", "k", "سلسیوس", "فارنهایت", "کلوین", "°c", "°f"}


def convert_unit(amount: float, from_u: str, to_u: str) -> str:
    fu, tu = from_u.lower().strip(), to_u.lower().strip()
    # دما
    if fu in TEMP_UNITS or tu in TEMP_UNITS:
        return _temp_convert(amount, fu, tu)
    if fu not in UNIT_CONV or tu not in UNIT_CONV:
        return (
            "❌ واحد نامعتبر.\n"
            "طول: km m cm mile ft inch\n"
            "وزن: kg g lb oz\n"
            "حجم: l ml gal\n"
            "دما: C F K\n"
            "مثال: `10 km mile`"
        )
    # گروه یکسان؟
    base = amount * UNIT_CONV[fu]
    result = base / UNIT_CONV[tu]
    return f"📐 **{pn(amount)} {from_u}** = **{pn(f'{result:.6g}')} {to_u}**"


def _temp_convert(val, fu, tu):
    # به سلسیوس
    if fu in ("f", "فارنهایت", "°f"):
        c = (val - 32) * 5 / 9
    elif fu in ("k", "کلوین"):
        c = val - 273.15
    else:
        c = val
    if tu in ("f", "فارنهایت", "°f"):
        r = c * 9 / 5 + 32
        return f"🌡 {pn(val)}° → **{pn(f'{r:.2f}')}°F**"
    if tu in ("k", "کلوین"):
        r = c + 273.15
        return f"🌡 {pn(val)}° → **{pn(f'{r:.2f}')} K**"
    return f"🌡 {pn(val)}° → **{pn(f'{c:.2f}')}°C**"


def parse_unit(text: str):
    n = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    m = re.match(r"([\d.]+)\s*(\S+)\s+(\S+)", n.strip())
    if m:
        return float(m.group(1)), m.group(2), m.group(3)
    return None


# ── ۲۷. ماشین‌حساب ──
SAFE_MATH = re.compile(r"^[\d\s\+\-\*\/\.\(\)\%\^]+$")


def calculator(expr: str) -> str:
    expr = expr.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹×÷", "0123456789*/")).strip()
    expr = expr.replace("^", "**").replace("%", "/100*")
    if not SAFE_MATH.match(expr.replace("**", "")):
        return "❌ فقط اعداد و + - * / ( ) مجاز است."
    try:
        result = eval(expr, {"__builtins__": {}}, {})
        return f"🔢 **{expr}** = **{pn(f'{result:,.10g}')}**"
    except Exception:
        return "❌ عبارت نامعتبر."


# ── ۲۸. پسورد ──
def generate_password(length: int = 12) -> str:
    length = max(6, min(length, 64))
    chars = string.ascii_letters + string.digits + "!@#$%&*"
    pwd = "".join(random.choice(chars) for _ in range(length))
    return f"🔐 **پسورد تصادفی** ({pn(length)} کاراکتر)\n\n`{pwd}`\n\n⚠️ این پیام را پاک کنید."


# ── ۲۹. شمارش متن ──
def count_text(text: str) -> str:
    chars = len(text)
    chars_no_space = len(text.replace(" ", "").replace("\n", ""))
    words = len(text.split())
    lines = text.count("\n") + 1
    return (
        f"📝 **شمارش متن**\n\n"
        f"• کاراکتر (با فاصله): {pn(chars)}\n"
        f"• کاراکتر (بدون فاصله): {pn(chars_no_space)}\n"
        f"• کلمه: {pn(words)}\n"
        f"• خط: {pn(lines)}"
    )


# ── ۳۰. BMI ──
def bmi_calc(weight_kg: float, height_cm: float) -> str:
    if weight_kg <= 0 or height_cm <= 0:
        return "❌ وزن و قد باید مثبت باشند."
    h = height_cm / 100
    bmi = weight_kg / (h * h)
    if bmi < 18.5:
        status = "کمبود وزن"
    elif bmi < 25:
        status = "نرمال ✅"
    elif bmi < 30:
        status = "اضافه وزن"
    else:
        status = "چاقی"
    # کالری تقریبی پایه (مرد، ۳۰ ساله، کم‌تحرک - فرمول ساده)
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * 30 + 5  # مرد
    return (
        f"⚖️ **BMI و کالری**\n\n"
        f"وزن: {pn(weight_kg)} kg | قد: {pn(height_cm)} cm\n"
        f"BMI: **{pn(f'{bmi:.1f}')}** → {status}\n\n"
        f"🔥 کالری پایه تقریبی (BMR): ~{pn(f'{bmr:.0f}')} kcal/روز\n"
        f"(بستگی به سن، جنسیت و فعالیت دارد)"
    )


def parse_bmi(text: str):
    nums = re.findall(r"[\d.]+", text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")))
    if len(nums) >= 2:
        return float(nums[0]), float(nums[1])
    return None
