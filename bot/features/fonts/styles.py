"""نقشه‌های یونیکد برای فونت‌های فانتزی (انگلیسی کامل + سازگار با فارسی/عربی)"""

# Base maps for A-Z a-z 0-9
def _make_map(upper_start, lower_start=None, digits=None):
    m = {}
    for i in range(26):
        m[chr(65 + i)] = chr(upper_start + i)
        if lower_start:
            m[chr(97 + i)] = chr(lower_start + i)
    if digits:
        for i in range(10):
            m[str(i)] = chr(digits + i)
    return m


def _combining(mark: str):
    """اعمال علامت ترکیبی روی هر کاراکتر (کار می‌کند روی فارسی و عربی)"""
    return lambda t: "".join(c + mark if c.strip() else c for c in t)


def _multi_combining(*marks: str):
    """چند علامت ترکیبی پشت‌سرهم"""
    return lambda t: "".join(c + "".join(marks) if c.strip() else c for c in t)


def _wrap_emoji(emoji: str):
    return lambda t: f" {emoji} ".join(t.split()) if " " in t else f"{emoji} {t} {emoji}"


def _frame(left: str, right: str = None):
    right = right or left
    return lambda t: f"{left} {t} {right}"


STYLES = {
    # ——— انگلیسی (Mathematical Alphanumeric) ———
    "bold": _make_map(0x1D400, 0x1D41A, 0x1D7CE),
    "italic": _make_map(0x1D434, 0x1D44E),
    "bold_italic": _make_map(0x1D468, 0x1D482),
    "script": _make_map(0x1D49C, 0x1D4B6),
    "bold_script": _make_map(0x1D4D0, 0x1D4EA),
    "fraktur": _make_map(0x1D504, 0x1D51E),
    "bold_fraktur": _make_map(0x1D56C, 0x1D586),
    "double": _make_map(0x1D538, 0x1D552, 0x1D7D8),
    "monospace": _make_map(0x1D670, 0x1D68A, 0x1D7F6),
    "sans": _make_map(0x1D5A0, 0x1D5BA, 0x1D7E2),
    "sans_bold": _make_map(0x1D5D4, 0x1D5EE, 0x1D7EC),
    "sans_italic": _make_map(0x1D608, 0x1D622),
    "sans_bold_italic": _make_map(0x1D63C, 0x1D656),
    "fullwidth": {chr(65+i): chr(0xFF21+i) for i in range(26)} | {chr(97+i): chr(0xFF41+i) for i in range(26)} | {str(i): chr(0xFF10+i) for i in range(10)},
    "circled": {chr(65+i): chr(0x24B6+i) for i in range(26)} | {chr(97+i): chr(0x24D0+i) for i in range(26)} | {str(i): chr(0x2460+i-1) if i > 0 else "⓪" for i in range(10)},
    "squared": {chr(65+i): chr(0x1F130+i) for i in range(26)},
    "negative_circled": {chr(65+i): chr(0x1F150+i) for i in range(26)},
    "parenthesized": {chr(97+i): chr(0x249C+i) for i in range(26)},
    "small_caps": {
        'a':'ᴀ','b':'ʙ','c':'ᴄ','d':'ᴅ','e':'ᴇ','f':'ғ','g':'ɢ','h':'ʜ','i':'ɪ','j':'ᴊ','k':'ᴋ','l':'ʟ','m':'ᴍ',
        'n':'ɴ','o':'ᴏ','p':'ᴘ','q':'ǫ','r':'ʀ','s':'s','t':'ᴛ','u':'ᴜ','v':'ᴠ','w':'ᴡ','x':'x','y':'ʏ','z':'ᴢ',
        'A':'ᴀ','B':'ʙ','C':'ᴄ','D':'ᴅ','E':'ᴇ','F':'ғ','G':'ɢ','H':'ʜ','I':'ɪ','J':'ᴊ','K':'ᴋ','L':'ʟ','M':'ᴍ',
        'N':'ɴ','O':'ᴏ','P':'ᴘ','Q':'ǫ','R':'ʀ','S':'s','T':'ᴛ','U':'ᴜ','V':'ᴠ','W':'ᴡ','X':'x','Y':'ʏ','Z':'ᴢ',
    },
    "superscript": {
        'a':'ᵃ','b':'ᵇ','c':'ᶜ','d':'ᵈ','e':'ᵉ','f':'ᶠ','g':'ᵍ','h':'ʰ','i':'ⁱ','j':'ʲ','k':'ᵏ','l':'ˡ','m':'ᵐ',
        'n':'ⁿ','o':'ᵒ','p':'ᵖ','r':'ʳ','s':'ˢ','t':'ᵗ','u':'ᵘ','v':'ᵛ','w':'ʷ','x':'ˣ','y':'ʸ','z':'ᶻ',
        'A':'ᴬ','B':'ᴮ','D':'ᴰ','E':'ᴱ','G':'ᴳ','H':'ᴴ','I':'ᴵ','J':'ᴶ','K':'ᴷ','L':'ᴸ','M':'ᴹ','N':'ᴺ','O':'ᴼ',
        'P':'ᴾ','R':'ᴿ','T':'ᵀ','U':'ᵁ','V':'ⱽ','W':'ᵂ',
        '0':'⁰','1':'¹','2':'²','3':'³','4':'⁴','5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹',
    },
    "subscript": {
        'a':'ₐ','e':'ₑ','h':'ₕ','i':'ᵢ','j':'ⱼ','k':'ₖ','l':'ₗ','m':'ₘ','n':'ₙ','o':'ₒ','p':'ₚ','r':'ᵣ','s':'ₛ','t':'ₜ','u':'ᵤ','v':'ᵥ','x':'ₓ',
        '0':'₀','1':'₁','2':'₂','3':'₃','4':'₄','5':'₅','6':'₆','7':'₇','8':'₈','9':'₉',
    },
    "upside_down": (lambda t: "".join({
        'a':'ɐ','b':'q','c':'ɔ','d':'p','e':'ǝ','f':'ɟ','g':'ƃ','h':'ɥ','i':'ᴉ','j':'ɾ','k':'ʞ','l':'l','m':'ɯ',
        'n':'u','o':'o','p':'d','q':'b','r':'ɹ','s':'s','t':'ʇ','u':'n','v':'ʌ','w':'ʍ','x':'x','y':'ʎ','z':'z',
        'A':'∀','B':'ꓭ','C':'Ɔ','D':'ᗡ','E':'Ǝ','F':'Ⅎ','G':'פ','H':'H','I':'I','J':'ſ','K':'ʞ','L':'˥','M':'W',
        'N':'N','O':'O','P':'Ԁ','Q':'Q','R':'ɹ','S':'S','T':'┴','U':'∩','V':'Λ','W':'M','X':'X','Y':'⅄','Z':'Z',
        '0':'0','1':'Ɩ','2':'ᄅ','3':'Ɛ','4':'ㄣ','5':'ϛ','6':'9','7':'ㄥ','8':'8','9':'6',
        ' ':' ',
    }.get(c, c) for c in t[::-1])),
    "bubble": {chr(65+i): chr(0x24B6+i) for i in range(26)} | {chr(97+i): chr(0x24D0+i) for i in range(26)},
    "regional": {chr(65+i): chr(0x1F1E6+i) for i in range(26)},
    "wide": {chr(65+i): chr(0xFF21+i) for i in range(26)} | {chr(97+i): chr(0xFF41+i) for i in range(26)},

    # ——— سازگار با فارسی و عربی (Combining Marks) ———
    "strikethrough": _combining("\u0336"),       # خط‌خورده
    "underline": _combining("\u0332"),           # زیرخط
    "overline": _combining("\u0305"),            # بالای خط
    "double_underline": _combining("\u0333"),    # دو زیرخط
    "slash": _combining("\u0338"),               # اسلش
    "dots": _combining("\u0307"),                # نقطه بالا
    "double_dot": _combining("\u0308"),          # دو نقطه (مثل اومlaut)
    "zigzag": _combining("\u035B"),              # زیگزاگ
    "bridge": _combining("\u0346"),              # پل بالا
    "tilde": _combining("\u0303"),               # تیلد
    "caron": _combining("\u030C"),               # کَرون
    "ring": _combining("\u030A"),                # حلقه بالا
    "hook": _combining("\u0309"),                # هوک
    "grave": _combining("\u0300"),               # گراو
    "acute": _combining("\u0301"),               # اکوت
    "diaeresis": _combining("\u0308"),           # دو نقطه
    "macron": _combining("\u0304"),              # مکرون
    "breve": _combining("\u0306"),               # بِرِو
    "dot_below": _combining("\u0323"),           # نقطه زیر
    "line_below": _combining("\u0331"),          # خط زیر
    "circle_below": _combining("\u0325"),        # دایره زیر
    "double_acute": _combining("\u030B"),        # دو اکوت
    "inverted_breve": _combining("\u0311"),      # بِرِو معکوس
    "candrabindu": _combining("\u0310"),         # چندرابیندو
    "perispomeni": _combining("\u0342"),         # پریسپومنی
    "x_above": _combining("\u033D"),             # ضربدر بالا
    "vertical_line": _combining("\u030D"),       # خط عمودی
    "double_vertical": _combining("\u030E"),     # دو خط عمودی
    "seagull": _combining("\u033C"),             # مرغ دریایی زیر
    "asterisk_below": _combining("\u0359"),      # ستاره زیر
    "plus_below": _combining("\u031F"),          # به‌علاوه زیر

    # ترکیب‌های چندتایی (زیباتر برای فارسی)
    "fancy1": _multi_combining("\u0305", "\u0332"),          # بالا + زیرخط
    "fancy2": _multi_combining("\u0307", "\u0332"),          # نقطه + زیرخط
    "fancy3": _multi_combining("\u0308", "\u0332"),          # دو نقطه + زیرخط
    "fancy4": _multi_combining("\u0336", "\u0305"),          # خط‌خورده + بالای خط
    "fancy5": _multi_combining("\u0304", "\u0331"),          # مکرون + خط زیر
    "fancy6": _multi_combining("\u0301", "\u0323"),          # اکوت + نقطه زیر
    "fancy7": _multi_combining("\u030A", "\u0332"),          # حلقه + زیرخط
    "fancy8": _multi_combining("\u035B", "\u0332"),          # زیگزاگ + زیرخط
    "fancy9": _multi_combining("\u0307", "\u0307", "\u0332"), # دو نقطه بالا + زیرخط
    "fancy10": _multi_combining("\u0336", "\u0336"),         # دو خط‌خورده

    # فاصله و معکوس
    "spaced": lambda t: " ".join(t),
    "double_spaced": lambda t: "  ".join(t),
    "reverse": lambda t: t[::-1],
    "letter_space": lambda t: "\u2009".join(t),   # thin space بین حروف
    "wide_space": lambda t: "\u2003".join(t),     # em space

    # فریم و تزئین
    "frame_star": _frame("★", "★"),
    "frame_diamond": _frame("◆", "◆"),
    "frame_flower": _frame("❀", "❀"),
    "frame_heart": _frame("♥", "♥"),
    "frame_moon": _frame("☽", "☾"),
    "frame_bracket": _frame("【", "】"),
    "frame_corner": _frame("『", "』"),
    "frame_ornament": _frame("❧", "❧"),
    "frame_arabic": _frame("﴾", "﴿"),             # براکت عربی
    "frame_quran": _frame("۝", "۝"),               # علامت پایان آیه

    # ایموجی بین کلمات
    "clap": _wrap_emoji("👏"),
    "heart": _wrap_emoji("❤️"),
    "star": _wrap_emoji("⭐"),
    "fire": _wrap_emoji("🔥"),
    "sparkle": _wrap_emoji("✨"),
    "wave": _wrap_emoji("🌊"),
    "rainbow": _wrap_emoji("🌈"),
    "moon": _wrap_emoji("🌙"),
    "sun": _wrap_emoji("☀️"),
    "flower": _wrap_emoji("🌸"),
    "rose": _wrap_emoji("🌹"),
    "diamond": _wrap_emoji("💎"),
    "crown": _wrap_emoji("👑"),
    "gem": _wrap_emoji("💠"),
    "spark": _wrap_emoji("💫"),
}

# نام‌های نمایشی
FONT_NAMES = {
    "bold": "𝐁𝐨𝐥𝐝 (ضخیم)",
    "italic": "𝐼𝑡𝑎𝑙𝑖𝑐 (ایتالیک)",
    "bold_italic": "𝑩𝒐𝒍𝒅 𝑰𝒕𝒂𝒍𝒊𝒄",
    "script": "𝒮𝒸𝓇𝒾𝓅𝓉 (دست‌نویس)",
    "bold_script": "𝓑𝓸𝓵𝓭 𝓢𝓬𝓻𝓲𝓹𝓽",
    "fraktur": "𝔉𝔯𝔞𝔨𝔱𝔲𝔯 (گوتیک)",
    "bold_fraktur": "𝕭𝖔𝖑𝖉 𝕱𝖗𝖆𝖐𝖙𝖚𝖗",
    "double": "𝔻𝕠𝕦𝕓𝕝𝕖 (دوبل)",
    "monospace": "𝙼𝚘𝚗𝚘𝚜𝚙𝚊𝚌𝚎",
    "sans": "𝖲𝖺𝗇𝗌",
    "sans_bold": "𝗦𝗮𝗻𝘀 𝗕𝗼𝗹𝗱",
    "sans_italic": "𝘚𝘢𝘯𝘴 𝘐𝘵𝘢𝘭𝘪𝘤",
    "sans_bold_italic": "𝙎𝙖𝙣𝙨 𝘽𝙤𝙡𝙙 𝙄𝙩𝙖𝙡𝙞𝙘",
    "fullwidth": "Ｆｕｌｌｗｉｄｔｈ",
    "circled": "Ⓒⓘⓡⓒⓛⓔⓓ",
    "squared": "🄰 🅂 🅀",
    "negative_circled": "🅐🅝🅓",
    "parenthesized": "⒜⒝⒞",
    "small_caps": "sᴍᴀʟʟ ᴄᴀᴘs",
    "superscript": "ˢᵘᵖᵉʳˢᶜʳⁱᵖᵗ",
    "subscript": "ₛᵤᵦₛ𝒸ᵣᵢₚₜ",
    "upside_down": "uʍop ǝpᴉsdn",
    "bubble": "ⓑⓤⓑⓑⓛⓔ",
    "regional": "🇷 🇪 🇬 🇮 🇴 🇳 🇦 🇱",
    "wide": "Ｗｉｄｅ",
    # فارسی/عربی
    "strikethrough": "خط‌خورده",
    "underline": "زیرخط",
    "overline": "بالاخـط",
    "double_underline": "دو زیرخط",
    "slash": "اسلش",
    "dots": "نقطه‌دار",
    "double_dot": "دونقطه",
    "zigzag": "زیگزاگ",
    "bridge": "پل",
    "tilde": "تیلد",
    "caron": "کَرون",
    "ring": "حلقه",
    "hook": "قلاب",
    "grave": "گراو",
    "acute": "اکوت",
    "diaeresis": "دیاِرِسیس",
    "macron": "مکرون",
    "breve": "بِرِو",
    "dot_below": "نقطه زیر",
    "line_below": "خط زیر",
    "circle_below": "دایره زیر",
    "double_acute": "دو اکوت",
    "inverted_breve": "بِرِو معکوس",
    "candrabindu": "چندرابیندو",
    "perispomeni": "پریسپومنی",
    "x_above": "ضربدر",
    "vertical_line": "خط عمودی",
    "double_vertical": "دو خط عمودی",
    "seagull": "مرغ‌دریایی",
    "asterisk_below": "ستاره زیر",
    "plus_below": "به‌علاوه زیر",
    "fancy1": "فانتزی ۱ (بالا+زیر)",
    "fancy2": "فانتزی ۲ (نقطه+زیر)",
    "fancy3": "فانتزی ۳ (دونقطه+زیر)",
    "fancy4": "فانتزی ۴ (خط‌خورده+بالا)",
    "fancy5": "فانتزی ۵ (مکرون+زیر)",
    "fancy6": "فانتزی ۶ (اکوت+نقطه)",
    "fancy7": "فانتزی ۷ (حلقه+زیر)",
    "fancy8": "فانتزی ۸ (زیگزاگ+زیر)",
    "fancy9": "فانتزی ۹ (دونقطه+زیرخط)",
    "fancy10": "فانتزی ۱۰ (دوبل خط)",
    "spaced": "فاصله‌دار",
    "double_spaced": "فاصله دوبل",
    "reverse": "معکوس",
    "letter_space": "فاصله نازک",
    "wide_space": "فاصله عریض",
    "frame_star": "قاب ستاره ★",
    "frame_diamond": "قاب لوزی ◆",
    "frame_flower": "قاب گل ❀",
    "frame_heart": "قاب قلب ♥",
    "frame_moon": "قاب ماه ☽☾",
    "frame_bracket": "قاب براکت 【】",
    "frame_corner": "قاب گوشه 『』",
    "frame_ornament": "قاب تزئینی ❧",
    "frame_arabic": "قاب عربی ﴾﴿",
    "frame_quran": "قاب قرآنی ۝",
    "clap": "👏 تشویق",
    "heart": "❤️ قلب",
    "star": "⭐ ستاره",
    "fire": "🔥 آتش",
    "sparkle": "✨ درخشش",
    "wave": "🌊 موج",
    "rainbow": "🌈 رنگین‌کمان",
    "moon": "🌙 ماه",
    "sun": "☀️ خورشید",
    "flower": "🌸 شکوفه",
    "rose": "🌹 گل‌سرخ",
    "diamond": "💎 الماس",
    "crown": "👑 تاج",
    "gem": "💠 نگین",
    "spark": "💫 جرقه",
}

# بهترین استایل‌های سازگار با فارسی و عربی
PERSIAN_COMPATIBLE = [
    "strikethrough", "underline", "overline", "double_underline", "slash",
    "dots", "double_dot", "zigzag", "bridge", "tilde", "caron", "ring",
    "hook", "grave", "acute", "macron", "breve", "dot_below", "line_below",
    "circle_below", "double_acute", "inverted_breve", "x_above",
    "vertical_line", "double_vertical", "seagull", "asterisk_below", "plus_below",
    "fancy1", "fancy2", "fancy3", "fancy4", "fancy5",
    "fancy6", "fancy7", "fancy8", "fancy9", "fancy10",
    "spaced", "double_spaced", "reverse", "letter_space", "wide_space",
    "frame_star", "frame_diamond", "frame_flower", "frame_heart", "frame_moon",
    "frame_bracket", "frame_corner", "frame_ornament", "frame_arabic", "frame_quran",
    "clap", "heart", "star", "fire", "sparkle", "wave", "rainbow",
    "moon", "sun", "flower", "rose", "diamond", "crown", "gem", "spark",
]
