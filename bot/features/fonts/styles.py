"""نقشه‌های یونیکد برای فونت‌های فانتزی (انگلیسی کامل + تقریبی فارسی)"""

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

STYLES = {
    "bold": _make_map(0x1D400, 0x1D41A, 0x1D7CE),          # Mathematical Bold
    "italic": _make_map(0x1D434, 0x1D44E),                 # Mathematical Italic
    "bold_italic": _make_map(0x1D468, 0x1D482),            # Bold Italic
    "script": _make_map(0x1D49C, 0x1D4B6),                 # Script
    "bold_script": _make_map(0x1D4D0, 0x1D4EA),            # Bold Script
    "fraktur": _make_map(0x1D504, 0x1D51E),                # Fraktur
    "bold_fraktur": _make_map(0x1D56C, 0x1D586),           # Bold Fraktur
    "double": _make_map(0x1D538, 0x1D552, 0x1D7D8),        # Double-Struck
    "monospace": _make_map(0x1D670, 0x1D68A, 0x1D7F6),     # Monospace
    "sans": _make_map(0x1D5A0, 0x1D5BA, 0x1D7E2),          # Sans-Serif
    "sans_bold": _make_map(0x1D5D4, 0x1D5EE, 0x1D7EC),     # Sans Bold
    "sans_italic": _make_map(0x1D608, 0x1D622),            # Sans Italic
    "sans_bold_italic": _make_map(0x1D63C, 0x1D656),      # Sans Bold Italic
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
    "regional": {chr(65+i): chr(0x1F1E6+i) for i in range(26)},  # flag letters
    "wide": {chr(65+i): chr(0xFF21+i) for i in range(26)} | {chr(97+i): chr(0xFF41+i) for i in range(26)},
    "strikethrough": lambda t: "".join(c + "\u0336" for c in t),
    "underline": lambda t: "".join(c + "\u0332" for c in t),
    "overline": lambda t: "".join(c + "\u0305" for c in t),
    "double_underline": lambda t: "".join(c + "\u0333" for c in t),
    "slash": lambda t: "".join(c + "\u0338" for c in t),
    "dots": lambda t: "".join(c + "\u0307" for c in t),
    "zigzag": lambda t: "".join(c + "\u035B" for c in t),
    "bridge": lambda t: "".join(c + "\u0346" for c in t),
    "reverse": lambda t: t[::-1],
    "spaced": lambda t: " ".join(t),
    "double_spaced": lambda t: "  ".join(t),
    "clap": lambda t: " 👏 ".join(t.split()),
    "heart": lambda t: " ❤️ ".join(t.split()),
    "star": lambda t: " ⭐ ".join(t.split()),
    "fire": lambda t: " 🔥 ".join(t.split()),
    "sparkle": lambda t: " ✨ ".join(t.split()),
    "wave": lambda t: " 🌊 ".join(t.split()),
    "rainbow": lambda t: " 🌈 ".join(t.split()),
    "moon": lambda t: " 🌙 ".join(t.split()),
    "sun": lambda t: " ☀️ ".join(t.split()),
    "flower": lambda t: " 🌸 ".join(t.split()),
    "persian_bold_approx": lambda t: t,  # placeholder - real Persian unicode limited
}

# نام‌های فارسی/انگلیسی برای نمایش به کاربر
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
    "strikethrough": "S̶t̶r̶i̶k̶e̶",
    "underline": "U̲n̲d̲e̲r̲l̲i̲n̲e̲",
    "overline": "O̅v̅e̅r̅l̅i̅n̅e̅",
    "double_underline": "D̳o̳u̳b̳l̳e̳",
    "slash": "S̸l̸a̸s̸h̸",
    "dots": "Ḋȯṫṡ",
    "zigzag": "Z͛i͛g͛z͛a͛g͛",
    "bridge": "B͆r͆i͆d͆g͆e͆",
    "reverse": "esreveR",
    "spaced": "S p a c e d",
    "double_spaced": "D  o  u  b  l  e",
    "clap": "👏 Clap 👏",
    "heart": "❤️ Heart ❤️",
    "star": "⭐ Star ⭐",
    "fire": "🔥 Fire 🔥",
    "sparkle": "✨ Sparkle ✨",
    "wave": "🌊 Wave 🌊",
    "rainbow": "🌈 Rainbow 🌈",
    "moon": "🌙 Moon 🌙",
    "sun": "☀️ Sun ☀️",
    "flower": "🌸 Flower 🌸",
}

# برای فارسی: چند استایل ترکیبی که روی کاراکترهای فارسی هم کار می‌کنند (combining)
PERSIAN_COMPATIBLE = ["strikethrough", "underline", "overline", "double_underline", "slash", "dots", "zigzag", "bridge", "spaced", "reverse", "clap", "heart", "star", "fire", "sparkle", "wave", "rainbow", "moon", "sun", "flower"]
