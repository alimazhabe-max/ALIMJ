# دیکشنری کامل متون چندزبانه (حاوی تمام کلیدهای مورد نیاز)
TEXTS = {
    "fa": {
        "welcome": "🌟 سلام {name} عزیز! 🌟",
        "prayer": "⏰ **اوقات شرعی امروز ({city}):**",
        "weather": "🌦️ **آب و هوای {city}:**",
        "motivation": "💖 **پیام انگیزشی روز:**",
        "change_city": "🔔 برای تغییر شهر، از دکمه‌های زیر استفاده کن.",
        "city_changed": "✅ شهر شما به **{city}** تغییر کرد.",
        "city_not_found": "❌ شهر '{city}' پیدا نشد.",
        "help": "🤖 **راهنمای ربات:**\n\n"
                "/start - نمایش اطلاعات امروز\n"
                "/city [نام شهر] - تغییر شهر\n"
                "/language - تغییر زبان\n"
                "/calendar - مشاهده تقویم تعاملی\n"
                "/stats - آمار ربات (فقط ادمین)\n"
                "/broadcast [پیام] - ارسال همگانی (فقط ادمین)",
        "language_changed": "✅ زبان شما به **{lang}** تغییر کرد.",
        "no_events": "هیچ مناسبت خاصی ثبت نشده است.",
        "admin_only": "❌ این دستور فقط برای ادمین‌ها قابل استفاده است.",
        "broadcast_sent": "✅ پیام به {count} کاربر ارسال شد.",
        "stats": "📊 **آمار ربات:**\n\n"
                 "👥 تعداد کل کاربران: {total}\n"
                 "📅 کاربران فعال امروز: {active}",
        "calendar_title": "📅 **تقویم {month} {year}**\n\n",
        "calendar_today": "📌 امروز: {date}",
        "calendar_event": "• {event}",
        "not_member": "❌ برای استفاده از این ربات، ابتدا در کانال زیر عضو شوید:\n{channel_link}\n\nپس از عضویت، دوباره `/start` را بفرستید.",
        "next_prayer": "⏳ زمان تا اذان بعدی ({name}): **{hours} ساعت و {minutes} دقیقه**",
    },
    "en": {
        "welcome": "🌟 Hello dear {name}! 🌟",
        "prayer": "⏰ **Prayer Times ({city}):**",
        "weather": "🌦️ **Weather in {city}:**",
        "motivation": "💖 **Daily Motivation:**",
        "change_city": "🔔 Use the buttons below to change city.",
        "city_changed": "✅ Your city has been changed to **{city}**.",
        "city_not_found": "❌ City '{city}' not found.",
        "help": "🤖 **Bot Commands:**\n\n"
                "/start - Show today's info\n"
                "/city [city name] - Change city\n"
                "/language - Change language\n"
                "/calendar - Interactive calendar\n"
                "/stats - Bot stats (admin only)\n"
                "/broadcast [message] - Broadcast (admin only)",
        "language_changed": "✅ Your language has been changed to **{lang}**.",
        "no_events": "No specific events recorded.",
        "admin_only": "❌ This command is for admins only.",
        "broadcast_sent": "✅ Message sent to {count} users.",
        "stats": "📊 **Bot Stats:**\n\n"
                 "👥 Total users: {total}\n"
                 "📅 Active users today: {active}",
        "calendar_title": "📅 **Calendar {month} {year}**\n\n",
        "calendar_today": "📌 Today: {date}",
        "calendar_event": "• {event}",
        "not_member": "❌ To use this bot, please join the channel below first:\n{channel_link}\n\nAfter joining, send `/start` again.",
        "next_prayer": "⏳ Time until next prayer ({name}): **{hours} hours and {minutes} minutes**",
    },
    "ar": {
        "welcome": "🌟 مرحباً عزيزي {name}! 🌟",
        "prayer": "⏰ **أوقات الصلاة اليوم ({city}):**",
        "weather": "🌦️ **الطقس في {city}:**",
        "motivation": "💖 **رسالة تحفيزية اليوم:**",
        "change_city": "🔔 استخدم الأزرار أدناه لتغيير المدينة.",
        "city_changed": "✅ تم تغيير مدينتك إلى **{city}**.",
        "city_not_found": "❌ المدينة '{city}' غير موجودة.",
        "help": "🤖 **تعليمات البوت:**\n\n"
                "/start - عرض معلومات اليوم\n"
                "/city [اسم المدينة] - تغيير المدينة\n"
                "/language - تغيير اللغة\n"
                "/calendar - تقويم تفاعلي\n"
                "/stats - إحصائيات البوت (للمشرفين)\n"
                "/broadcast [رسالة] - إرسال جماعي (للمشرفين)",
        "language_changed": "✅ تم تغيير لغتك إلى **{lang}**.",
        "no_events": "لا توجد مناسبات خاصة مسجلة.",
        "admin_only": "❌ هذا الأمر مخصص للمشرفين فقط.",
        "broadcast_sent": "✅ تم إرسال الرسالة إلى {count} مستخدم.",
        "stats": "📊 **إحصائيات البوت:**\n\n"
                 "👥 إجمالي المستخدمين: {total}\n"
                 "📅 المستخدمين النشطين اليوم: {active}",
        "calendar_title": "📅 **تقويم {month} {year}**\n\n",
        "calendar_today": "📌 اليوم: {date}",
        "calendar_event": "• {event}",
        "not_member": "❌ لاستخدام هذا البوت، يرجى الانضمام إلى القناة أدناه أولاً:\n{channel_link}\n\nبعد الانضمام، أرسل `/start` مرة أخرى.",
        "next_prayer": "⏳ الوقت المتبقي حتى الصلاة القادمة ({name}): **{hours} ساعة و {minutes} دقيقة**",
    }
}

def get_text(user_id, key, **kwargs):
    from database import get_user_language
    lang = get_user_language(user_id)
    text = TEXTS.get(lang, TEXTS["fa"]).get(key, key)
    return text.format(**kwargs) if kwargs else text
