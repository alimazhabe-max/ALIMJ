"""مبدل فونت — فارسی / انگلیسی / همه فونت‌ها"""
from .styles import STYLES, FONT_NAMES
import random
import re

# فونت‌های مناسب انگلیسی (unicode fancy)
EN_STYLES = [
    "bold", "italic", "bold_italic", "script", "bold_script", "fraktur", "bold_fraktur",
    "double", "monospace", "sans", "sans_bold", "sans_italic", "sans_bold_italic",
    "fullwidth", "circled", "small_caps", "superscript", "subscript", "upside_down",
    "strikethrough", "underline", "spaced", "reverse",
]

# فونت‌های سازگار با فارسی (combining marks + spaced)
FA_STYLES = [
    "strikethrough", "underline", "overline", "double_underline", "slash", "dots",
    "zigzag", "bridge", "spaced", "double_spaced", "reverse",
    "clap", "heart", "star", "fire", "sparkle", "wave", "rainbow", "moon", "sun", "flower",
]


def list_fonts() -> str:
    lines = ["🎨 **لیست فونت‌ها**\n"]
    lines.append("🇬🇧 انگلیسی:")
    for k in EN_STYLES:
        if k in FONT_NAMES:
            lines.append(f"• `{k}` — {FONT_NAMES[k]}")
    lines.append("\n🇮🇷 فارسی / تزئینی:")
    for k in FA_STYLES:
        if k in FONT_NAMES:
            lines.append(f"• `{k}` — {FONT_NAMES[k]}")
    lines.append("\n📌 بعد از انتخاب فونت، متن را بفرستید.")
    return "\n".join(lines)


def get_font_preview(style_key: str = None) -> str:
    sample_en = "Hello World 123"
    sample_fa = "سلام دنیا"
    if style_key and style_key in STYLES:
        en = _apply(sample_en, style_key)
        fa = _apply(sample_fa, style_key)
        return f"🎨 **پیش‌نمایش `{style_key}`**\n\nانگلیسی:\n{en}\n\nفارسی:\n{fa}"
    keys = list(STYLES.keys())
    random.shuffle(keys)
    lines = ["🎨 **چند نمونه**\n"]
    for k in keys[:6]:
        lines.append(f"**{FONT_NAMES.get(k, k)}**\n{_apply(sample_en, k)}\n")
    return "\n".join(lines)


def _apply(text: str, style_key: str) -> str:
    style = STYLES.get(style_key)
    if style is None:
        return text
    if callable(style):
        return style(text)
    if isinstance(style, dict) and style and all(isinstance(k, int) for k in style.keys()):
        return text.translate(style)
    return "".join(style.get(ch, ch) for ch in text)


def apply_font(text: str, style_key: str) -> str:
    if not text or not text.strip():
        return "❌ متن خالی است."
    if style_key not in STYLES:
        return f"❌ فونت «{style_key}» پیدا نشد."
    converted = _apply(text, style_key)
    name = FONT_NAMES.get(style_key, style_key)
    return (
        f"🎨 **فونت: {name}**\n\n"
        f"{converted}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"متن اصلی: {text}"
    )


def _is_mostly_persian(text: str) -> bool:
    fa = len(re.findall(r"[\u0600-\u06FF]", text))
    en = len(re.findall(r"[A-Za-z]", text))
    return fa >= en


def apply_all_fonts(text: str) -> str:
    """اعمال همه فونت‌های مرتبط (هوشمند فارسی/انگلیسی)"""
    if not text or not text.strip():
        return "❌ متن خالی است."
    text = text.strip()
    if len(text) > 80:
        text = text[:80]
    keys = FA_STYLES if _is_mostly_persian(text) else EN_STYLES
    lines = [f"🎨 **همه فونت‌ها** روی:\n`{text}`\n"]
    for k in keys:
        if k not in STYLES:
            continue
        try:
            conv = _apply(text, k)
            name = FONT_NAMES.get(k, k)
            lines.append(f"**{name}**\n{conv}\n")
        except Exception:
            continue
    return "\n".join(lines)
