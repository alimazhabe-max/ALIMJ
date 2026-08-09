# ALIMJ Bot v3 — ربات کامل اوقات شرعی + ابزارها

## ساختار پوشه‌ها

```
ALIMJ_Bot_Complete/
├── requirements.txt
├── render.yaml
├── README.md
└── bot/
    ├── main.py                 # نقطه شروع
    ├── config.py
    ├── database.py
    ├── logger.py
    ├── scheduler.py
    ├── api/                    # ارتباط با سرویس‌های خارجی
    │   ├── calendar.py
    │   ├── prayer.py
    │   ├── tgju.py
    │   ├── weather.py
    │   └── weather_extra.py    # پیش‌بینی ۷روزه + AQI + فاصله
    ├── handlers/
    │   ├── commands.py
    │   ├── callbacks.py
    │   ├── messages.py         # هندلر اصلی پیام‌ها
    │   └── middleware.py
    ├── utils/                  # ابزارهای کمکی قدیمی (سازگاری)
    │   ├── helpers.py          # کیبوردها و پیام اصلی
    │   ├── finance_tools.py
    │   ├── fun_tools.py
    │   ├── app_tools.py
    │   └── ...
    └── features/               # ★ بخش‌های جدا و تمیز
        ├── religious/          # مذهبی
        │   ├── qibla.py
        │   ├── adhkar.py
        │   ├── verse_hadith.py
        │   ├── istikhara.py    # با مقدمه توحید و صلوات
        │   └── events.py
        ├── fonts/              # فونت‌های فانتزی
        │   ├── styles.py
        │   └── converter.py
        ├── market/             # بازار و کریپتو
        ├── weather/
        ├── tools/
        ├── fun/
        ├── profile/
        └── date/
```

## قابلیت‌های اصلی

### مذهبی
- قبله‌نما
- اذکار روز
- آیه و حدیث (از API + محلی)
- استخاره (با دستورالعمل ۳ بار توحید + ۳ بار صلوات + دعا)
- مناسبت‌های مذهبی

### بازار
- قیمت کامل (دلار، طلا، سکه)
- ۲۰ ارز برتر کریپتو (دلار + تومان)
- تبدیل بیش از ۵۰۰ ارز دیجیتال (مثال: `20 ton`)

### هوا و مکان
- پیش‌بینی ۷ روزه
- کیفیت هوا واقعی (AQI)
- فاصله شهرها

### فونت
- بیش از ۵۰ استایل یونیکد
- پشتیبانی انگلیسی کامل + استایل‌های سازگار با فارسی

### ابزارها و سرگرمی
- ماشین‌حساب، BMI، پسورد، تبدیل واحد
- فال حافظ، جوک، حقیقت یا جرات، چالش روزانه

## اجرا

```bash
pip install -r requirements.txt
# ساخت فایل .env
echo "BOT_TOKEN=توکن_ربات" > .env
echo "ADMIN_IDS=آیدی_عددی" >> .env
python -m bot.main
```

## متغیرهای محیطی
- `BOT_TOKEN` (الزامی)
- `ADMIN_IDS`
- `CHANNEL_ID` / `CHANNEL_LINK`
- `TIMEZONE=Asia/Tehran`
