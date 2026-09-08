def get_refresh_button():
    """فقط دکمه بروزرسانی زیر پیام"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data="refresh_main")]
    ])

def get_main_keyboard(user_id=None):
    """کیبورد اصلی؛ در صورت وجود کاربر، بخش‌های پرتکرار را بالاتر می‌آورد."""
    rows = [
        [KeyboardButton("🏙 انتخاب شهر"), KeyboardButton("📅 تقویم")],
        [KeyboardButton("🌍 زبان"), KeyboardButton("➕ بیشتر")],
        [KeyboardButton("🤖 دستیار هوشمند")],
    ]
    # Personalization is intentionally conservative: only reorder existing buttons.
    if user_id is not None:
        try:
            from bot.database import get_top_user_features
            top = {name for name, _count in get_top_user_features(user_id, 3)}
            priority = []
            if "market" in top or "crypto_top" in top or "crypto_full" in top:
                priority.append(rows[1])
            if "forecast" in top or "aqi" in top or "location" in top:
                priority.append(rows[0])
            if priority:
                seen = {id(r) for r in priority}
                rows = priority + [r for r in rows if id(r) not in seen]
        except Exception:
            pass
    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="پیام بنویسید یا از دکمه‌ها استفاده کنید...",
    )

def get_ai_keyboard(user_id=None):
    """دکمه‌های شیشه‌ای زیر پیام AI: انتخاب ارائه‌دهنده و پاک‌کردن حافظه."""
    from bot.services.ai_service import get_selected_model, _PROVIDER_PRETTY
    selected = get_selected_model(user_id) if user_id is not None else None
    selected_text = "🎛 انتخاب مدل AI"
    if selected:
        provider = selected[0]
        pretty = _PROVIDER_PRETTY.get(provider, provider)
        selected_text = f"🎛 فعال: {pretty}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(selected_text, callback_data="ai_models")],
        [InlineKeyboardButton("🧹 حذف حافظه", callback_data="ai_clear_memory")],
    ])

def get_ai_model_keyboard(user_id=None):
    """
    لیست ارائه‌دهنده‌ها (نه تک‌تک مدل‌ها).
    با انتخاب یک ارائه‌دهنده، همه مدل‌هایش به‌صورت خودکار امتحان می‌شوند.
    """
    from bot.services.ai_service import available_providers, get_selected_model
    selected = get_selected_model(user_id) if user_id is not None else None
    selected_provider = selected[0] if selected else None
    rows = []
    for index, (provider, label) in enumerate(available_providers()):
        mark = "✅ " if selected_provider == provider else ""
        rows.append([
            InlineKeyboardButton(
                f"{mark}{label}",
                callback_data=f"ai_provider:{index}",
            )
        ])
    if not rows:
        rows.append([InlineKeyboardButton("❌ هیچ سرویسی تنظیم نشده", callback_data="ai_noop")])
    rows.append([InlineKeyboardButton("↩️ برگشت", callback_data="ai_models_back")])
    return InlineKeyboardMarkup(rows)

def get_more_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📅 تاریخ و سن"), KeyboardButton("🕌 مذهبی")],
            [KeyboardButton("💰 بازار"), KeyboardButton("🌤 هوا و مکان")],
            [KeyboardButton("🛠 ابزارها"), KeyboardButton("🎮 سرگرمی")],
            [KeyboardButton("🎨 فونت"), KeyboardButton("👤 پروفایل")],
            [KeyboardButton("🔙 بازگشت")],
        ],
        resize_keyboard=True,
    )

def get_date_tools_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🔄 مبدل تاریخ"), KeyboardButton("🎂 محاسبه سن")],
            [KeyboardButton("🎉 روزشمار تولد"), KeyboardButton("♈ برج و حیوان")],
            [KeyboardButton("🌙 سن قمری"), KeyboardButton("📆 اختلاف تاریخ")],
            [KeyboardButton("👥 اختلاف سن"), KeyboardButton("📅 تقویم ماه")],
            [KeyboardButton("🔍 مناسبت‌یاب"), KeyboardButton("🌸 شمارش نوروز")],
            [KeyboardButton("🌍 ساعت جهانی"), KeyboardButton("⏳ شمارش‌معکوس")],
            [KeyboardButton("🔙 بازگشت به بیشتر")],
        ],
        resize_keyboard=True,
    )

def get_religious_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🕋 قبله‌نما"), KeyboardButton("📿 اذکار روز")],
            [KeyboardButton("📖 آیه و حدیث"), KeyboardButton("🕌 مناسبت مذهبی")],
            [KeyboardButton("🙏 استخاره"), KeyboardButton("🔔 تنظیم اذان")],
            [KeyboardButton("🔙 بازگشت به بیشتر")],
        ],
        resize_keyboard=True,
    )

def get_market_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("💵 قیمت کامل بازار"), KeyboardButton("💎 ۲۰ ارز برتر کریپتو")],
            [KeyboardButton("🔄 تبدیل ارز / کریپتو"), KeyboardButton("📈 سود و ضرر")],
            [KeyboardButton("📊 نمودار و تحلیل ارز دیجیتال")],
            [KeyboardButton("🔙 بازگشت به بیشتر")],
        ],
        resize_keyboard=True,
    )

def get_weather_geo_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🌤 پیش‌بینی هوا"), KeyboardButton("🌫 کیفیت هوا")],
            [KeyboardButton("📍 لوکیشن من")],
            [KeyboardButton("🔙 بازگشت به بیشتر")],
        ],
        resize_keyboard=True,
    )

def get_tools_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🔢 ماشین‌حساب"), KeyboardButton("🔐 پسورد تصادفی")],
            [KeyboardButton("📝 شمارش متن"), KeyboardButton("🗺 فاصله جهانی")],
            [KeyboardButton("🔙 بازگشت به بیشتر")],
        ],
        resize_keyboard=True,
    )

def get_azan_keyboard(settings: dict = None):
    """کیبورد تنظیم اذان با وضعیت فعلی هر نماز."""
    if not settings:
        settings = {
            "enabled": True,
            "fajr": True, "dhuhr": False, "asr": False,
            "maghrib": True, "isha": False,
        }

    def mark(on: bool) -> str:
        return "✅" if on else "❌"

    master = "🔔 اعلان‌ها: روشن" if settings.get("enabled") else "🔕 اعلان‌ها: خاموش"
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(master)],
            [
                KeyboardButton(f"{mark(settings.get('fajr'))} اذان صبح"),
                KeyboardButton(f"{mark(settings.get('dhuhr'))} اذان ظهر"),
            ],
            [
                KeyboardButton(f"{mark(settings.get('asr'))} اذان عصر"),
                KeyboardButton(f"{mark(settings.get('maghrib'))} اذان مغرب"),
            ],
            [
                KeyboardButton(f"{mark(settings.get('isha'))} اذان عشاء"),
            ],
            [KeyboardButton("🔄 همه روشن"), KeyboardButton("⏹ همه خاموش")],
            [KeyboardButton("🔙 بازگشت به مذهبی")],
        ],
        resize_keyboard=True,
    )

def get_fun_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📖 فال حافظ"), KeyboardButton("😂 جوک روز")],
            [KeyboardButton("🧠 دانستنی روز"), KeyboardButton("💪 چالش امروز")],
            [KeyboardButton("💖 جمله انگیزشی")],
            [KeyboardButton("🔙 بازگشت به بیشتر")],
        ],
        resize_keyboard=True,
    )

def get_joke_keyboard():
    """کیبورد دسته‌بندی جوک"""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🎲 جوک تصادفی"), KeyboardButton("😄 عمومی")],
            [KeyboardButton("🤣 ترکی"), KeyboardButton("😂 رشتی")],
            [KeyboardButton("😏 قزوینی"), KeyboardButton("👨 مردان")],
            [KeyboardButton("👩 زنان"), KeyboardButton("🤑 اصفهانی")],
            [KeyboardButton("🔞 سکسی"), KeyboardButton("🎭 متفرقه")],
            [KeyboardButton("💀 زشت")],
            [KeyboardButton("🔙 بازگشت به سرگرمی")],
        ],
        resize_keyboard=True,
    )

def get_profile_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("👤 پروفایل من"), KeyboardButton("📊 آمار من")],
            [KeyboardButton("🎂 ذخیره تاریخ تولد"), KeyboardButton("⚙️ تنظیمات هوشمند")],
            [KeyboardButton("🔙 بازگشت به بیشتر")],
        ],
        resize_keyboard=True,
    )

def get_smart_settings_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("✍️ پاسخ کوتاه"), KeyboardButton("📚 پاسخ کامل")],
            [KeyboardButton("⚖️ پاسخ متعادل"), KeyboardButton("💵 ارز USD")],
            [KeyboardButton("💶 ارز EUR"), KeyboardButton("🇮🇷 ارز IRR")],
            [KeyboardButton("🧹 پاک‌سازی تنظیمات")],
            [KeyboardButton("🔙 بازگشت به پروفایل")],
        ], resize_keyboard=True
    )

def get_country_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🇮🇷 ایران"), KeyboardButton("🇮🇶 عراق")],
            [KeyboardButton("🔙 بازگشت")],
        ],
        resize_keyboard=True,
    )

def get_iran_cities_keyboard():
    buttons = []
    row = []
    for city in IRAN_CITIES:
        row.append(KeyboardButton(city))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([KeyboardButton("🔙 بازگشت")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_iraq_cities_keyboard():
    buttons = []
    row = []
    for city in IRAQ_CITIES:
        row.append(KeyboardButton(city))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([KeyboardButton("🔙 بازگشت")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_language_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("فارسی 🇮🇷"), KeyboardButton("English 🇬🇧"), KeyboardButton("العربية 🇸🇦")],
            [KeyboardButton("🔙 بازگشت")],
        ],
        resize_keyboard=True,
    )

def get_font_keyboard():
    """کیبورد فونت: فارسی / انگلیسی / همه"""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🇬🇧 فونت انگلیسی"), KeyboardButton("🇮🇷 فونت فارسی")],
            [KeyboardButton("🌈 همه فونت‌ها"), KeyboardButton("📋 لیست فونت‌ها")],
            [KeyboardButton("🔙 بازگشت به بیشتر")],
        ],
        resize_keyboard=True,
    )

def get_font_en_keyboard():
    from bot.features.fonts.converter import EN_STYLES
    from bot.features.fonts.styles import FONT_NAMES
    buttons, row = [], []
    for k in EN_STYLES:
        label = FONT_NAMES.get(k, k)[:18]
        row.append(KeyboardButton(label))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([KeyboardButton("🔙 بازگشت فونت")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_font_fa_keyboard():
    from bot.features.fonts.converter import FA_STYLES
    from bot.features.fonts.styles import FONT_NAMES
    buttons, row = [], []
    for k in FA_STYLES:
        label = FONT_NAMES.get(k, k)[:18]
        row.append(KeyboardButton(label))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([KeyboardButton("🔙 بازگشت فونت")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)