"""مبدل فونت — پشتیبانی بیش از ۵۰ استایل یونیکد"""
from .styles import STYLES, FONT_NAMES, PERSIAN_COMPATIBLE
import random


def list_fonts() -> str:
    lines = ["🎨 **لیست فونت‌ها**\n"]
    lines.append("برای استفاده: فونت را انتخاب کنید سپس متن بفرستید.\n")
    for i, (key, name) in enumerate(FONT_NAMES.items(), 1):
        lines.append(f"{i}. `{key}` → {name}")
    lines.append("\n📌 مثال: بعد از انتخاب فونت، بنویسید:\n`سلام دنیا` یا `Hello World`")
    return "\n".join(lines)


def get_font_preview(style_key: str = None) -> str:
    sample_en = "Hello World 123"
    sample_fa = "سلام دنیا"
    if style_key and style_key in STYLES:
        en = _apply(sample_en, style_key)
        fa = _apply(sample_fa, style_key)
        return f"🎨 **پیش‌نمایش `{style_key}`**\n\nانگلیسی:\n{en}\n\nفارسی:\n{fa}"
    # چند نمونه تصادفی
    keys = list(STYLES.keys())
    random.shuffle(keys)
    lines = ["🎨 **چند نمونه فونت**\n"]
    for k in keys[:8]:
        name = FONT_NAMES.get(k, k)
        en = _apply(sample_en, k)
        lines.append(f"**{name}**\n{en}\n")
    return "\n".join(lines)


def _apply(text: str, style_key: str) -> str:
    style = STYLES.get(style_key)
    if style is None:
        return text
    if callable(style):
        return style(text)
    # str.maketrans returns a mapping with int ordinals
    if isinstance(style, dict) and style and all(isinstance(k, int) for k in style.keys()):
        return text.translate(style)
    # char -> char dict
    result = []
    for ch in text:
        result.append(style.get(ch, ch))
    return "".join(result)


def apply_font(text: str, style_key: str) -> str:
    if not text or not text.strip():
        return "❌ متن خالی است."
    if style_key not in STYLES:
        return f"❌ فونت «{style_key}» پیدا نشد.\nاز لیست فونت‌ها یکی انتخاب کنید."
    converted = _apply(text, style_key)
    name = FONT_NAMES.get(style_key, style_key)
    return (
        f"🎨 **فونت: {name}**\n\n"
        f"{converted}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"متن اصلی: {text}"
    )
