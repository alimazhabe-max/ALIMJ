"""هندلر پیام‌ها — همه قابلیت‌ها"""
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.database import (
    update_user_field, get_user_city, set_last_main_msg_id,
    add_reminder, track_usage,
    get_user_usage, set_birth_date, get_birth_date, get_user,
    get_azan_settings, set_azan_master, toggle_azan_prayer,
)
from bot.utils.helpers import (
    build_message, get_main_keyboard, get_refresh_button,
    get_country_keyboard, get_iran_cities_keyboard, get_iraq_cities_keyboard,
    get_language_keyboard, get_more_keyboard, get_date_tools_keyboard,
    get_religious_keyboard, get_market_keyboard, get_weather_geo_keyboard,
    get_tools_keyboard, get_fun_keyboard, get_profile_keyboard, get_joke_keyboard,
    get_calendar_text, get_calendar_buttons, ALL_CITIES, CITY_COUNTRY,
    get_azan_keyboard, get_ai_keyboard, get_ai_model_keyboard,
)
from bot.api.calendar import get_today_tehran
from bot.handlers.middleware import check_and_rate_limit
from bot.utils.motivation import get_motivation
from bot.features.date.date_tools import (
    parse_shamsi, parse_any_date, parse_two_dates, parse_countdown,
    birthday_countdown, zodiac_animal, lunar_age, date_diff, age_diff,
    convert_with_weekday, month_calendar, search_events, nowruz_countdown,
    world_clock, custom_countdown,
)
from bot.features.date.converters import calculate_age, parse_birth_datetime
from bot.features.religious import qibla_direction, daily_adhkar, daily_verse_hadith, religious_countdown, istikhara, istikhara_intro
from bot.features.market.finance import full_market_prices, convert_currency, profit_loss, parse_profit, get_top_crypto, convert_crypto, get_crypto_chart, analyze_crypto, parse_currency_input
from bot.features.tools.app_tools import calculator, generate_password, count_text, world_distance
from bot.features.fun.fun_tools import hafez_fal, joke_of_day, fact_of_day, daily_challenge, random_joke, get_joke_categories
from bot.features.weather.weather_extra import weather_forecast, air_quality
from bot.features.fonts import apply_font, list_fonts, get_font_preview, apply_all_fonts
from bot.features.profile import profile_text
from bot.utils.helpers import get_font_keyboard, get_font_en_keyboard, get_font_fa_keyboard
from bot.features.fonts.styles import FONT_NAMES
from bot.features.fonts.converter import EN_STYLES, FA_STYLES
import re
from datetime import datetime, timedelta
import pytz
from bot.config import config
from bot.services.ai_extras import (
    store_answer, get_last_answer, get_ai_result_keyboard, parse_chart_request, make_chart_image,
    web_search, parse_natural_reminder, enhance_ocr_prompt,
)
from bot.services.ai_service import (
    ask_ai, ask_ai_media, clear_history, enabled_providers,
    _extract_text_from_bytes, generate_or_edit_image,
    looks_like_image_request, looks_like_image_edit,
    text_to_speech, wants_voice_reply, strip_voice_prefix, speech_to_text,
    analyze_voice_emotion, wants_emotion_analysis, should_auto_voice_reply,
    wants_voice_chat_mode, wants_end_voice_chat, is_voice_only_request,
    generate_music, analyze_video, translate_voice,
)



async def _safe_reply(update, text, **kwargs):
    """ارسال امن بدون کرش بابت Markdown"""
    kwargs.pop("parse_mode", None)
    try:
        await update.message.reply_text(text, **kwargs)
    except Exception:
        try:
            await update.message.reply_text(str(text)[:4000], reply_markup=kwargs.get("reply_markup"))
        except Exception:
            pass

async def _keep_typing(bot, chat_id, stop_event):
    """تا وقتی پاسخ آماده نشده، مدام حالت «در حال نوشتن...» را نشان بده."""
    import asyncio
    from telegram.constants import ChatAction
    while not stop_event.is_set():
        try:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=4)
        except Exception:
            pass




def _apply_voice_chat_flags(context, text: str) -> str | None:
    """
    فعال/غیرفعال کردن حالت مکالمه ویسی.
    پیام تأیید برای کاربر برمی‌گرداند یا None.
    """
    if wants_end_voice_chat(text):
        context.user_data["ai_voice_chat"] = False
        return "📝 حالت ویس خاموش شد. از این به بعد جواب‌ها بیشتر متنی است."
    if wants_voice_chat_mode(text):
        context.user_data["ai_voice_chat"] = True
        return (
            "🎙️ حالت مکالمه ویسی روشن شد.\n"
            "هر چی بگی (متن یا ویس) سعی می‌کنم با صدا جواب بدم.\n"
            "برای خاموش کردن بگو: «قطع ویس» یا «فقط متن»."
        )
    return None




async def _handle_special_ai_intents(update, context, user_id, text: str) -> bool:
    """نمودار، جستجو، یادآوری، موسیقی — True اگر کامل هندل شد."""
    import re
    from io import BytesIO
    from bot.database import add_reminder

    # یادآوری
    rem = parse_natural_reminder(text)
    if rem:
        body, when, repeat_type, repeat_every = rem
        add_reminder(
            user_id,
            body,
            when.isoformat(),
            repeat_type=repeat_type,
            repeat_every=repeat_every,
        )
        repeat_label = {
            "daily": "روزانه",
            "weekly": "هفتگی",
            "monthly": "ماهانه",
            "every_minutes": f"هر {repeat_every} دقیقه",
            "every_hours": f"هر {repeat_every} ساعت",
        }.get(repeat_type, "یک‌بار")
        await update.message.reply_text(
            f"⏰ یادآوری ثبت شد.\nموضوع: {body}\nزمان: {when.strftime('%Y-%m-%d %H:%M')}\nتکرار: {repeat_label}",
            reply_markup=get_ai_keyboard(user_id),
        )
        return True

    # جستجوی وب
    m = re.match(r"^(جستجو|سرچ|search)\s*[:：]?\s*(.+)$", text, re.I | re.S)
    if m or re.search(r"\b(در\s*اینترنت|تو\s*وب)\s*جستجو", text, re.I):
        q = m.group(2).strip() if m else re.sub(r".*جستجو\s*[:：]?", "", text, flags=re.I).strip()
        notice = await update.message.reply_text("🔎 در حال جستجو...")
        try:
            result = await web_search(q)
            await update.message.reply_text(result, reply_markup=get_ai_keyboard(user_id))
        finally:
            try:
                await notice.delete()
            except Exception:
                pass
        return True

    # نمودار
    chart = parse_chart_request(text)
    if chart:
        title, labels, values, ctype = chart
        notice = await update.message.reply_text("📊 در حال رسم نمودار...")
        try:
            png = make_chart_image(title, labels, values, ctype)
            bio = BytesIO(png)
            bio.name = "chart.png"
            await update.message.reply_photo(
                photo=bio, caption=title, reply_markup=get_ai_keyboard(user_id)
            )
        except Exception as e:
            await update.message.reply_text(f"⚠️ نمودار: {e}")
        finally:
            try:
                await notice.delete()
            except Exception:
                pass
        return True

    # موسیقی
    if re.search(r"(موسیقی|آهنگ|music)\s*بساز|(بساز|تولید)\s*(موسیقی|آهنگ|افکت)", text, re.I):
        notice = await update.message.reply_text("🎵 در حال ساخت موسیقی...")
        try:
            audio = await generate_music(text)
            bio = BytesIO(audio)
            bio.name = "music.mp3"
            await update.message.reply_audio(
                audio=bio, caption="🎵", reply_markup=get_ai_keyboard(user_id)
            )
        except Exception as e:
            await update.message.reply_text(
                f"⚠️ ساخت موسیقی در دسترس نبود:\n{e}",
                reply_markup=get_ai_keyboard(user_id),
            )
        finally:
            try:
                await notice.delete()
            except Exception:
                pass
        return True

    return False


async def _send_ai_answer(update, user_id, answer: str, *, stream: bool = True):
    """ارسال جواب AI — بدون دکمه زیر پیام."""
    msg = update.message
    store_answer(user_id, answer)
    return await msg.reply_text(f"🤖 {answer}")


async def _ask_ai_stream_and_send(update, context, user_id: int, text: str):
    """استریم AI و ویرایش تدریجی پیام؛ در شکست، پیام نیمه‌کاره حذف می‌شود."""
    import asyncio
    from bot.services.ai_service import ask_ai_stream

    msg = update.message
    # هنگام تولید پاسخ فقط وضعیت «در حال نوشتن» نمایش داده شود؛
    # آیکن ربات تا آماده شدن پاسخ نهایی نمایش داده نمی‌شود.
    sent = await msg.reply_text("✍️ در حال نوشتن...")
    buf = []
    provider_label = ""

    try:
        async for piece, label in ask_ai_stream(user_id, text):
            if label:
                provider_label = label
                continue
            if piece:
                # پاسخ تا پایان تولید نمایش داده نمی‌شود؛ در این مدت فقط
                # پیام «✍️ در حال نوشتن...» روی صفحه باقی می‌ماند.
                buf.append(piece)

        answer = "".join(buf).strip()
        if not answer:
            raise RuntimeError("جواب خالی")

        store_answer(user_id, answer)
        final = "🤖 " + answer
        if len(final) > 4000:
            final = final[:3990] + "…"
        try:
            await sent.edit_text(final)
        except Exception:
            await msg.reply_text(final)
        return answer, provider_label or "ai"

    except Exception:
        try:
            await sent.delete()
        except Exception:
            pass
        raise


async def _send_ai_voice(update_or_msg, text: str, user_id: int, reply_markup=None):
    """ارسال ویس با پیام وضعیت «در حال ویس دادن»."""
    msg = getattr(update_or_msg, "message", None) or update_or_msg
    notice = await msg.reply_text("🔊 در حال ویس دادن...")
    try:
        audio = await text_to_speech(text)
        from io import BytesIO
        bio = BytesIO(audio)
        bio.name = "reply.mp3"
        kwargs = {"audio": bio, "caption": "🔊"}
        if reply_markup is not None:
            kwargs["reply_markup"] = reply_markup
        await msg.reply_audio(**kwargs)
    finally:
        try:
            await notice.delete()
        except Exception:
            pass

async def _ask_ai_with_typing(update, context, user_id, text):
    """AI request with stable chunked output and safe fallback semantics."""
    import asyncio
    stop_event = asyncio.Event()
    chat_id = update.effective_chat.id
    # فقط _ask_ai_stream_and_send یک پیام «✍️ در حال نوشتن...» می‌فرستد.
    # اینجا فقط ChatAction.TYPING برای وضعیت تایپ تلگرام فعال می‌شود تا
    # پیام وضعیت دوبار روی صفحه ایجاد نشود.
    task = asyncio.create_task(_keep_typing(context.bot, chat_id, stop_event))
    try:
        try:
            result = await _ask_ai_stream_and_send(update, context, user_id, text)
            context.user_data["_ai_already_sent"] = True
            return result
        except Exception as stream_error:
            from bot.logger import logger
            logger.warning("AI chunked stream failed, using canonical fallback: %s", stream_error)
            context.user_data["_ai_already_sent"] = False
            return await ask_ai(user_id, text)
    finally:
        stop_event.set()
        try:
            await task
        except Exception:
            pass


async def _send_main(update, context, text, user_id):
    context.user_data.pop("waiting_for", None)
    await update.message.reply_text("🏠 منوی اصلی", reply_markup=get_main_keyboard())
    msg = await update.message.reply_text(text, reply_markup=get_refresh_button())
    context.user_data["last_main_msg_id"] = msg.message_id
    set_last_main_msg_id(user_id, msg.message_id)
    return msg


def _is_back(text):
    t = text.strip()
    return t in ("🔙 بازگشت", "بازگشت") or "بازگشت" in t


def _is_back_more(text):
    return "بازگشت به بیشتر" in text


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    if not await check_and_rate_limit(update, context):
        return

    try:
        await _text_handler_inner(update, context)
    except Exception as e:
        from bot.logger import logger
        logger.error(f"text_handler error: {e}", exc_info=True)
        try:
            await update.message.reply_text("⚠️ این بخش موقتاً در دسترس نیست. کمی بعد دوباره امتحان کنید.")
        except Exception:
            pass


async def _text_handler_inner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "کاربر"
    city = get_user_city(user_id)
    waiting = context.user_data.get("waiting_for")

    # AI chat mode
    if context.user_data.get("ai_mode"):
        if _is_back(text) or _is_back_more(text):
            context.user_data.pop("ai_mode", None)
            context.user_data.pop("waiting_for", None)
            await update.message.reply_text("➕ منوی بیشتر:", reply_markup=get_more_keyboard())
            return
        if text.startswith(("➕", "🏠", "📅", "🕌", "💰", "🌤", "🛠", "🎮", "🎨", "👤", "🏙", "🌍", "🔙", "🤖")):
            if text != "🤖 دستیار هوشمند":
                context.user_data.pop("ai_mode", None)
                # fall through to normal menu handling
            else:
                # repeat the AI entry prompt
                providers = enabled_providers()
                provider_text = "، ".join(providers) if providers else "هیچ سرویس فعالی ندارد"
                await update.message.reply_text(
                    "🤖 دستیار هوشمند روز زیبا\n\n"
                    "پیامت را بفرست تا به هوش مصنوعی ارسال شود.\n"
                    f"سرویس‌های فعال: {provider_text}\n\n"
                    "مدل دلخواهت را از «🎛 انتخاب مدل» انتخاب کن.",
                    reply_markup=get_ai_keyboard(user_id),
                )
                return
        else:
            try:
                # فقط خواندن متن با ویس (بدون AI)
                import re as _re
                m_read = _re.match(r"^(بخون|بخوان)\s*[:：]?\s*(.+)$", text, _re.I | _re.S)
                if m_read:
                    to_read = m_read.group(2).strip()
                    try:
                        await _send_ai_voice(
                            update, to_read, user_id)
                    except Exception as ve:
                        await update.message.reply_text(f"⚠️ ویس ساخته نشد: {ve}")
                    return
                if looks_like_image_request(text):
                    notice = await update.message.reply_text("🎨 در حال ساخت تصویر...")
                    try:
                        img_bytes, mime = await generate_or_edit_image(text)
                        from io import BytesIO
                        bio = BytesIO(img_bytes)
                        bio.name = "ai_image.png" if "png" in mime else "ai_image.jpg"
                        await update.message.reply_photo(
                            photo=bio,
                            caption="🎨 تصویر ساخته شد",
                            reply_markup=get_ai_keyboard(user_id),
                        )
                    finally:
                        try:
                            await notice.delete()
                        except Exception:
                            pass
                    return
                mode_msg = _apply_voice_chat_flags(context, text)
                if mode_msg:
                    await update.message.reply_text(
                        mode_msg, reply_markup=get_ai_keyboard(user_id)
                    )
                # «ویس بفرست» بدون سؤال → آخرین جواب را با ویس بفرست
                if is_voice_only_request(text):
                    last = get_last_answer(user_id) or (context.user_data or {}).get("last_ai_answer")
                    if last:
                        try:
                            await _send_ai_voice(update, last, user_id)
                        except Exception as ve:
                            await update.message.reply_text(f"⚠️ ویس ساخته نشد: {ve}")
                    else:
                        await update.message.reply_text(
                            "هنوز جوابی برای خواندن ندارم. اول یک سؤال بپرس، بعد بگو «ویس بفرست»."
                        )
                    return
                voice_mode = wants_voice_reply(text) or bool(
                    context.user_data.get("ai_voice_chat")
                )
                ask_text = strip_voice_prefix(text) if wants_voice_reply(text) else text
                # اگر فقط روشن کردن حالت ویس بود و سؤال دیگری نبود، لازم نیست AI سنگین
                if mode_msg and wants_voice_chat_mode(text) and len(ask_text) < 40:
                    try:
                        await _send_ai_voice(
                            update,
                            "باشه، با ویس حرف می‌زنیم. هر وقت خواستی بگو.",
                            user_id,
                        )
                    except Exception:
                        pass
                    return
                # قابلیت‌های ویژه قبل از AI عمومی
                handled = await _handle_special_ai_intents(
                    update, context, user_id, ask_text
                )
                if handled:
                    return
                answer, provider = await _ask_ai_with_typing(
                    update, context, user_id, ask_text
                )
                if context.user_data is not None:
                    context.user_data["last_ai_answer"] = answer
                if not (context.user_data or {}).get("_ai_already_sent"):
                    await _send_ai_answer(update, user_id, answer)
                if context.user_data is not None:
                    context.user_data.pop("_ai_already_sent", None)
                explicit = wants_voice_reply(text)
                if should_auto_voice_reply(
                    ask_text,
                    answer,
                    input_was_voice=False,
                    explicit_voice=explicit,
                    voice_chat_mode=bool(context.user_data.get("ai_voice_chat")),
                ):
                    try:
                        await _send_ai_voice(
                            update, answer, user_id
                        )
                    except Exception as ve:
                        await update.message.reply_text(
                            f"⚠️ متن آماده شد ولی ویس ساخته نشد: {ve}"
                        )
            except Exception as exc:
                await update.message.reply_text(
                    "❌ فعلاً هیچ‌کدام از سرویس‌های AI پاسخ ندادند.\n\n" + str(exc)[:3000]
                )
            return

    if waiting:
        if _is_back(text) or _is_back_more(text):
            context.user_data.pop("waiting_for", None)
            await update.message.reply_text("➕ منوی بیشتر:", reply_markup=get_more_keyboard())
            return
        # اگر کاربر دکمه منو زد، waiting را رها کن و ادامه بده
        menu_starts = (
            "➕", "🏠", "📅", "🕌", "💰", "🌤", "🛠", "🎮", "🎨", "👤",
            "🏙", "🌍", "🔙", "💵", "💎", "🔄", "📈", "📐", "🔢", "🔐",
            "📝", "🗺", "⏰", "📒", "📖", "😂", "🧠", "💪", "💖", "🕋",
            "📿", "🙏", "🔔", "🌫", "📍", "🇬🇧", "🇮🇷", "🌈", "📋", "🤖", "🧹",
        )
        if text.startswith(menu_starts) or text in (
            "بیشتر", "بازار", "مذهبی", "ابزارها", "سرگرمی", "فونت", "پروفایل",
            "تاریخ و سن", "هوا و مکان", "انتخاب شهر", "تقویم", "زبان",
        ):
            context.user_data.pop("waiting_for", None)
            waiting = None
        else:
            handlers = {
                "date_convert": _h_date_convert, "age_calc": _h_age_calc,
                "birthday": _h_birthday, "zodiac": _h_zodiac, "lunar": _h_lunar,
                "date_diff": _h_date_diff, "age_diff": _h_age_diff,
                "event_search": _h_event_search, "countdown": _h_countdown,
                "calc": _h_calc,
                "profit": _h_profit, "currency": _h_currency, "distance": _h_distance, "crypto_chart": _h_crypto_full, "crypto_analyze": _h_crypto_full, "crypto_full": _h_crypto_full,
                "birth_save": _h_birth_save,
                "count_text": _h_count_text,
                "font_text": _h_font_text, "font_all": _h_font_all,
            }
            fn = handlers.get(waiting)
            if fn:
                try:
                    await fn(update, context, text, user_id)
                except Exception as e:
                    from bot.logger import logger
                    logger.error(f"waiting handler {waiting}: {e}", exc_info=True)
                    context.user_data.pop("waiting_for", None)
                    await update.message.reply_text(
                        "⚠️ خطا در پردازش. دوباره از منو انتخاب کنید.",
                        reply_markup=get_more_keyboard(),
                    )
                return
            context.user_data.pop("waiting_for", None)

    if text in ("🏙 انتخاب شهر", "انتخاب شهر"):
        await update.message.reply_text("🏙 کشور:", reply_markup=get_country_keyboard()); return
    if text in ("📅 تقویم", "تقویم"):
        t = get_today_tehran()
        await update.message.reply_text(get_calendar_text(t.year, t.month, t.day, user_id), reply_markup=get_calendar_buttons(t.year, t.month, t.day, user_id)); return
    if text in ("🌍 زبان", "زبان"):
        await update.message.reply_text("🌍 زبان:", reply_markup=get_language_keyboard()); return
    if text in ("➕ بیشتر", "بیشتر"):
        await update.message.reply_text("➕ بخش را انتخاب کنید:", reply_markup=get_more_keyboard()); return

    if text == "🤖 دستیار هوشمند":
        providers = enabled_providers()
        context.user_data["ai_mode"] = True
        provider_text = "، ".join(providers) if providers else "هیچ سرویس فعالی ندارد"
        await update.message.reply_text(
            "🤖 دستیار هوشمند روز زیبا\n\n"
            "پیامت را بفرست تا به هوش مصنوعی ارسال شود.\n"
            f"سرویس‌های فعال: {provider_text}\n\n"
            "مدل دلخواهت را از «🎛 انتخاب مدل» انتخاب کن.",
            reply_markup=get_ai_keyboard(user_id),
        )
        return

    if text == "📅 تاریخ و سن":
        await update.message.reply_text("📅 تاریخ و سن:", reply_markup=get_date_tools_keyboard()); return
    if text == "🕌 مذهبی":
        await update.message.reply_text("🕌 مذهبی:", reply_markup=get_religious_keyboard()); return
    if text == "💰 بازار":
        await update.message.reply_text("💰 بازار:", reply_markup=get_market_keyboard()); return
    if text == "🌤 هوا و مکان":
        await update.message.reply_text("🌤 هوا و مکان:", reply_markup=get_weather_geo_keyboard()); return
    if text == "🛠 ابزارها":
        await update.message.reply_text("🛠 ابزارها:", reply_markup=get_tools_keyboard()); return
    if text == "🎮 سرگرمی":
        await update.message.reply_text("🎮 سرگرمی:", reply_markup=get_fun_keyboard()); return
    
    if text in ("🎨 فونت", "فونت"):
        await update.message.reply_text("🎨 بخش فونت:", reply_markup=get_font_keyboard()); return
    if text in ("📋 لیست فونت‌ها", "📋 لیست همه فونت‌ها"):
        await update.message.reply_text(list_fonts(), reply_markup=get_font_keyboard()); return
    if text == "🇬🇧 فونت انگلیسی":
        await update.message.reply_text("🇬🇧 یک فونت انگلیسی انتخاب کنید:", reply_markup=get_font_en_keyboard()); return
    if text == "🇮🇷 فونت فارسی":
        await update.message.reply_text("🇮🇷 یک فونت فارسی/تزئینی انتخاب کنید:", reply_markup=get_font_fa_keyboard()); return
    if text == "🌈 همه فونت‌ها":
        context.user_data["waiting_for"] = "font_all"
        await update.message.reply_text("🌈 یک کلمه یا جمله بفرستید تا روی همه فونت‌ها اعمال شود:", reply_markup=get_font_keyboard()); return
    if text == "🔙 بازگشت فونت":
        await update.message.reply_text("🎨 بخش فونت:", reply_markup=get_font_keyboard()); return
    # انتخاب فونت از نام نمایشی
    name_to_key = {v: k for k, v in FONT_NAMES.items()}
    name_to_key.update({v[:18]: k for k, v in FONT_NAMES.items()})
    if text in name_to_key or text in FONT_NAMES:
        key = name_to_key.get(text, text)
        context.user_data["selected_font"] = key
        context.user_data["waiting_for"] = "font_text"
        await update.message.reply_text(f"🎨 فونت انتخاب شد.\nمتن را بفرستید:", reply_markup=get_font_keyboard()); return

    if text == "👤 پروفایل":
        await update.message.reply_text("👤 پروفایل:", reply_markup=get_profile_keyboard()); return
    if _is_back_more(text):
        await update.message.reply_text("➕ منوی بیشتر:", reply_markup=get_more_keyboard()); return

    # تاریخ و سن
    if text in ("🔄 مبدل تاریخ", "مبدل تاریخ"):
        context.user_data["waiting_for"] = "date_convert"; track_usage(user_id, "date_convert")
        await update.message.reply_text("🔄 تاریخ:\n`1403/05/18` یا `2024/08/09`", reply_markup=get_date_tools_keyboard()); return
    if text in ("🎂 محاسبه سن", "🎂 محاسبه سن دقیق", "محاسبه سن"):
        context.user_data["waiting_for"] = "age_calc"; track_usage(user_id, "age_calc")
        await update.message.reply_text("🎂 تولد شمسی:\n`1375/03/15`", reply_markup=get_date_tools_keyboard()); return
    if text in ("🎉 روزشمار تولد", "روزشمار تولد"):
        context.user_data["waiting_for"] = "birthday"; track_usage(user_id, "birthday")
        bd = get_birth_date(user_id)
        if bd and len(bd.split("/")) == 3:
            p = bd.split("/"); context.user_data.pop("waiting_for", None)
            await update.message.reply_text(birthday_countdown(int(p[0]), int(p[1]), int(p[2])), reply_markup=get_date_tools_keyboard()); return
        await update.message.reply_text("🎉 تولد شمسی:\n`1375/03/15`", reply_markup=get_date_tools_keyboard()); return
    if text in ("♈ برج و حیوان", "برج و حیوان"):
        context.user_data["waiting_for"] = "zodiac"; track_usage(user_id, "zodiac")
        await update.message.reply_text("♈ تولد شمسی:\n`1375/03/15`", reply_markup=get_date_tools_keyboard()); return
    if text in ("🌙 سن قمری", "سن قمری"):
        context.user_data["waiting_for"] = "lunar"; track_usage(user_id, "lunar")
        await update.message.reply_text("🌙 تولد شمسی:\n`1375/03/15`", reply_markup=get_date_tools_keyboard()); return
    if text in ("📆 اختلاف تاریخ", "📆 اختلاف دو تاریخ", "اختلاف تاریخ"):
        context.user_data["waiting_for"] = "date_diff"; track_usage(user_id, "date_diff")
        await update.message.reply_text(
            "📆 دو تاریخ شمسی بفرست:\n"
            "`1375/03/15 1403/05/18`\n\n"
            "خروجی: سال/ماه/روز • هفته • ساعت • روز کاری • میلادی و قمری",
            reply_markup=get_date_tools_keyboard(),
        ); return
    if text in ("👥 اختلاف سن", "اختلاف سن"):
        context.user_data["waiting_for"] = "age_diff"; track_usage(user_id, "age_diff")
        await update.message.reply_text(
            "👥 دو تاریخ تولد شمسی بفرست:\n"
            "`1375/03/15 1380/06/20`\n\n"
            "خروجی: سن هر نفر • اختلاف دقیق • سن قمری • نسبت سنی",
            reply_markup=get_date_tools_keyboard(),
        ); return
    if text in ("📅 تقویم ماه", "تقویم ماه"):
        track_usage(user_id, "month_cal")
        await update.message.reply_text(month_calendar(), reply_markup=get_date_tools_keyboard()); return
    if text in ("🔍 مناسبت‌یاب", "مناسبت‌یاب"):
        context.user_data["waiting_for"] = "event_search"; track_usage(user_id, "event_search")
        await update.message.reply_text("🔍 کلمه کلیدی:\n`نوروز`", reply_markup=get_date_tools_keyboard()); return
    if text in ("🌸 شمارش نوروز", "شمارش نوروز"):
        track_usage(user_id, "nowruz")
        await update.message.reply_text(nowruz_countdown(), reply_markup=get_date_tools_keyboard()); return
    if text in ("🌍 ساعت جهانی", "ساعت جهانی"):
        track_usage(user_id, "world_clock")
        await update.message.reply_text(world_clock(), reply_markup=get_date_tools_keyboard()); return
    if text in ("⏳ شمارش‌معکوس", "شمارش‌معکوس"):
        context.user_data["waiting_for"] = "countdown"; track_usage(user_id, "countdown")
        await update.message.reply_text("⏳ تاریخ:\n`1405/01/01 نوروز`", reply_markup=get_date_tools_keyboard()); return

    # مذهبی
    if text in ("🕋 قبله‌نما", "قبله‌نما"):
        track_usage(user_id, "qibla")
        await update.message.reply_text(qibla_direction(city), reply_markup=get_religious_keyboard()); return
    if text in ("📿 اذکار روز", "اذکار روز"):
        track_usage(user_id, "adhkar")
        await update.message.reply_text(daily_adhkar(user_id), reply_markup=get_religious_keyboard()); return
    if text in ("📖 آیه و حدیث", "آیه و حدیث"):
        track_usage(user_id, "verse")
        await update.message.reply_text(await daily_verse_hadith(user_id), reply_markup=get_religious_keyboard()); return
    if text in ("🕌 مناسبت مذهبی", "مناسبت مذهبی"):
        track_usage(user_id, "rel_cd")
        await update.message.reply_text(religious_countdown(), reply_markup=get_religious_keyboard()); return
    
    if text in ("🙏 استخاره", "استخاره"):
        track_usage(user_id, "istikhara")
        context.user_data["waiting_for"] = "istikhara_confirm"
        await update.message.reply_text(istikhara_intro(), reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("🙏 استخاره بگیر")], [KeyboardButton("🔙 بازگشت به مذهبی")]],
            resize_keyboard=True
        )); return
    if text == "🙏 استخاره بگیر":
        context.user_data.pop("waiting_for", None)
        track_usage(user_id, "istikhara_do")
        await update.message.reply_text(await istikhara(user_id), reply_markup=get_religious_keyboard()); return
    if text == "🔙 بازگشت به مذهبی":
        context.user_data.pop("waiting_for", None)
        await update.message.reply_text("🕌 مذهبی:", reply_markup=get_religious_keyboard()); return

    if text in ("🔔 تنظیم اذان", "تنظیم اذان"):
        track_usage(user_id, "azan")
        await _show_azan_settings(update, user_id, city)
        return

    # دکمه‌های شخصی‌سازی اذان
    if text in ("🔔 اعلان‌ها: روشن", "🔕 اعلان‌ها: خاموش"):
        settings = get_azan_settings(user_id)
        set_azan_master(user_id, not settings["enabled"])
        await _show_azan_settings(update, user_id, city, note="وضعیت کلی اعلان‌ها تغییر کرد.")
        return

    if text in ("🔄 همه روشن",):
        set_azan_master(user_id, True)
        for key in ("fajr", "dhuhr", "asr", "maghrib", "isha"):
            field = f"notify_{key}"
            update_user_field(user_id, field, 1)
        await _show_azan_settings(update, user_id, city, note="همه اذان‌ها روشن شدند.")
        return

    if text in ("⏹ همه خاموش",):
        for key in ("fajr", "dhuhr", "asr", "maghrib", "isha"):
            update_user_field(user_id, f"notify_{key}", 0)
        await _show_azan_settings(update, user_id, city, note="همه اذان‌ها خاموش شدند.")
        return

    # دکمه‌های تکی اذان (با ✅ یا ❌)
    _azan_btn_map = {
        "اذان صبح": "fajr",
        "اذان ظهر": "dhuhr",
        "اذان عصر": "asr",
        "اذان مغرب": "maghrib",
        "اذان عشاء": "isha",
    }
    for label, key in _azan_btn_map.items():
        if text.endswith(label) and (text.startswith("✅") or text.startswith("❌")):
            new_state = toggle_azan_prayer(user_id, key)
            status = "روشن" if new_state else "خاموش"
            await _show_azan_settings(update, user_id, city, note=f"{label} {status} شد.")
            return

    if text in ("🔙 بازگشت به مذهبی",):
        await update.message.reply_text("🕌 مذهبی:", reply_markup=get_religious_keyboard())
        return

    # بازار
    if text in ("💵 قیمت کامل بازار", "قیمت کامل بازار"):
        track_usage(user_id, "market")
        m = await update.message.reply_text("⏳ دریافت قیمت‌ها...")
        r = await full_market_prices()
        await m.edit_text(r)
        await update.message.reply_text("💰", reply_markup=get_market_keyboard()); return
    if text in ("💎 ۲۰ ارز برتر کریپتو", "۲۰ ارز برتر کریپتو", "💎 ۳۰۰ ارز برتر کریپتو", "۳۰۰ ارز برتر کریپتو", "کریپتو"):
        track_usage(user_id, "crypto_top")
        m = await update.message.reply_text("⏳ دریافت لیست کریپتو...")
        r = await get_top_crypto(20)
        await m.edit_text(r)
        await update.message.reply_text("💎", reply_markup=get_market_keyboard()); return
    if text in ("🔄 تبدیل ارز", "تبدیل ارز", "🔄 تبدیل ارز / کریپتو", "تبدیل ارز / کریپتو"):
        context.user_data["waiting_for"] = "currency"; track_usage(user_id, "currency")
        await update.message.reply_text(
            "🔄 مبدل هوشمند ارز / کریپتو\n\n"
            "تقریباً همه ارزهای دیجیتال + تومان/دلار پشتیبانی می‌شود.\n\n"
            "مثال‌ها:\n"
            "• 1.5 btc\n"
            "• 20 ton\n"
            "• 100 تتر\n"
            "• 50 دلار\n"
            "• 1 btc eth\n"
            "• 50000 تومان دلار\n"
            "• 100 usdt toman\n"
            "• ۲ بیتکوین",
            reply_markup=get_market_keyboard()
        ); return
    if text in ("📈 سود و ضرر", "سود و ضرر"):
        context.user_data["waiting_for"] = "profit"; track_usage(user_id, "profit")
        await update.message.reply_text("📈 `1000 1200` یا `1000 1200 5`", reply_markup=get_market_keyboard()); return

    if text in (
        "📊 نمودار و تحلیل ارز دیجیتال",
        "نمودار و تحلیل ارز دیجیتال",
        "📊 نمودار قیمت کریپتو",
        "نمودار قیمت کریپتو",
        "نمودار کریپتو",
        "🔍 تحلیل ارز دیجیتال",
        "تحلیل ارز دیجیتال",
        "تحلیل کریپتو",
    ):
        context.user_data["waiting_for"] = "crypto_full"
        track_usage(user_id, "crypto_full")
        await update.message.reply_text(
            "📊 نمودار + تحلیل حرفه‌ای ارز دیجیتال\n\n"
            "نماد را بفرستید (اختیاری: تعداد روز):\n"
            "• btc\n"
            "• eth 30\n"
            "• sol 7\n"
            "• ton\n\n"
            "خروجی: نمودار چندپنلی + خلاصه تکنیکال + نظر AI (لانگ/شورت)",
            reply_markup=get_market_keyboard(),
        )
        return

    # هوا
    if text in ("🌤 پیش‌بینی هوا", "پیش‌بینی هوا"):
        track_usage(user_id, "forecast")
        await update.message.reply_text(await weather_forecast(city), reply_markup=get_weather_geo_keyboard()); return
    if text in ("🌫 کیفیت هوا", "کیفیت هوا"):
        track_usage(user_id, "aqi")
        await update.message.reply_text(await air_quality(city), reply_markup=get_weather_geo_keyboard()); return
    if text in ("🗺 فاصله شهرها", "فاصله شهرها", "🗺 فاصله جهانی", "فاصله جهانی"):
        context.user_data["waiting_for"] = "distance"; track_usage(user_id, "distance")
        await update.message.reply_text(
            "🗺 فاصله جهانی\n"
            "🌍 همه شهرها و کشورهای دنیا پشتیبانی می‌شود.\n\n"
            "دو مکان را بفرستید:\n"
            "• تهران مشهد\n"
            "• تهران تا ترکیه\n"
            "• ایران ژاپن\n"
            "• Paris to Tokyo\n"
            "• New York - Brazil",
            reply_markup=get_tools_keyboard(),
        ); return
    if text in ("📍 لوکیشن من", "لوکیشن من"):
        track_usage(user_id, "location")
        await update.message.reply_text(f"📍 لوکیشن را از 📎 بفرستید.\nشهر فعلی: {city}", reply_markup=get_weather_geo_keyboard()); return

    # ابزار
    if text in ("🔢 ماشین‌حساب", "ماشین‌حساب"):
        context.user_data["waiting_for"] = "calc"; track_usage(user_id, "calc")
        await update.message.reply_text("🔢 `2+3*4`", reply_markup=get_tools_keyboard()); return
    if text in ("🔐 پسورد تصادفی", "پسورد تصادفی"):
        track_usage(user_id, "password")
        pwd = generate_password(16)
        await update.message.reply_text(
            "🔐 پسورد تصادفی:\n\n<code>" + pwd + "</code>\n\n👆 روی پسورد بزنید تا کپی شود",
            reply_markup=get_tools_keyboard(),
            parse_mode="HTML",
        ); return
    if text in ("📝 شمارش متن", "شمارش متن"):
        context.user_data["waiting_for"] = "count_text"; track_usage(user_id, "count")
        await update.message.reply_text("📝 متن را بفرستید:", reply_markup=get_tools_keyboard()); return

    # سرگرمی
    if text in ("📖 فال حافظ", "فال حافظ"):
        track_usage(user_id, "hafez"); await update.message.reply_text(await hafez_fal(user_id), reply_markup=get_fun_keyboard()); return
    
    if text in ("😂 جوک روز", "جوک روز"):
        track_usage(user_id, "joke")
        await update.message.reply_text(
            "😂 دسته جوک را انتخاب کن:\n(بیش از ۸۷۰۰ جوک از farsijokes)",
            reply_markup=get_joke_keyboard(),
        ); return

    # دسته‌های جوک
    _joke_map = {
        "🎲 جوک تصادفی": None,
        "😄 عمومی": "general",
        "🤣 ترکی": "turkish",
        "😂 رشتی": "rashti",
        "😏 قزوینی": "ghazvini",
        "👨 مردان": "men",
        "👩 زنان": "women",
        "🤑 اصفهانی": "isfahani",
        "🔞 سکسی": "adult",
        "🎭 متفرقه": "misc",
        "💀 زشت": "dirty",
    }
    if text in _joke_map:
        track_usage(user_id, "joke")
        cat = _joke_map[text]
        await update.message.reply_text(await joke_of_day(cat, user_id=update.effective_user.id), reply_markup=get_joke_keyboard())
        return
    if text in ("🔙 بازگشت به سرگرمی",):
        await update.message.reply_text("🎮 سرگرمی:", reply_markup=get_fun_keyboard()); return
    if text in ("🧠 دانستنی روز", "دانستنی روز"):
        track_usage(user_id, "fact"); await update.message.reply_text(await fact_of_day(), reply_markup=get_fun_keyboard()); return
    if text in ("💪 چالش امروز", "چالش امروز"):
        track_usage(user_id, "challenge"); await update.message.reply_text(await daily_challenge(), reply_markup=get_fun_keyboard()); return
    if text in ("💖 جمله انگیزشی", "جمله انگیزشی"):
        track_usage(user_id, "motivation"); await update.message.reply_text(f"💖 {get_motivation()}", reply_markup=get_fun_keyboard()); return

    # پروفایل
    if text in ("👤 پروفایل من", "پروفایل من"):
        track_usage(user_id, "profile")
        u = update.effective_user
        txt = profile_text(
            user_id, u.first_name or first_name,
            username=u.username, last_name=u.last_name,
            language_code=getattr(u, "language_code", None),
        )
        try:
            photos = await context.bot.get_user_profile_photos(user_id, limit=1)
            if photos.total_count > 0:
                file_id = photos.photos[0][-1].file_id
                await update.message.reply_photo(file_id, caption=txt.replace("**", "").replace("`","")+ "", reply_markup=get_profile_keyboard())
            else:
                await update.message.reply_text(txt.replace("**", "").replace("`",""), reply_markup=get_profile_keyboard())
        except Exception:
            await update.message.reply_text(txt.replace("**", "").replace("`",""), reply_markup=get_profile_keyboard())
        return
    if text in ("📊 آمار من", "آمار من"):
        track_usage(user_id, "stats")
        usage = get_user_usage(user_id) or []
        if usage:
            lines = []
            for row in usage[:15]:
                try:
                    lines.append(f"• {row[0]}: {row[1]}")
                except Exception:
                    pass
            msg = "📊 آمار:\n" + ("\n".join(lines) if lines else "خالی")
        else:
            msg = "📊 آمار:\nخالی"
        await update.message.reply_text(msg, reply_markup=get_profile_keyboard()); return
    if text in ("🎂 ذخیره تاریخ تولد", "ذخیره تاریخ تولد"):
        context.user_data["waiting_for"] = "birth_save"
        await update.message.reply_text("🎂 `1375/03/15`", reply_markup=get_profile_keyboard()); return

    if text in ("🇮🇷 ایران", "ایران"):
        await update.message.reply_text("🇮🇷 شهر:", reply_markup=get_iran_cities_keyboard()); return
    if text in ("🇮🇶 عراق", "عراق"):
        await update.message.reply_text("🇮🇶 شهر:", reply_markup=get_iraq_cities_keyboard()); return
    if _is_back(text):
        await _send_main(update, context, await build_message(user_id, first_name, city), user_id); return
    if text.startswith("فارسی") or text == "فارسی 🇮🇷":
        update_user_field(user_id, "language", "fa"); await _send_main(update, context, await build_message(user_id, first_name, city), user_id); return
    if text.startswith("English") or text == "English 🇬🇧":
        update_user_field(user_id, "language", "en"); await _send_main(update, context, await build_message(user_id, first_name, city), user_id); return
    if "العربية" in text or "العربيه" in text:
        update_user_field(user_id, "language", "ar"); await _send_main(update, context, await build_message(user_id, first_name, city), user_id); return
    if text in ALL_CITIES:
        update_user_field(user_id, "city", text); update_user_field(user_id, "country", CITY_COUNTRY.get(text, "Iran"))
        await _send_main(update, context, f"✅ شهر → **{text}**\n\n" + await build_message(user_id, first_name, text), user_id); return


async def _h_date_convert(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_any_date(t)
    await u.message.reply_text(convert_with_weekday(*p) if p else "❌ نامعتبر", reply_markup=get_date_tools_keyboard())

async def _h_age_calc(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_birth_datetime(t)
    await u.message.reply_text(calculate_age(*p) if p else "❌ نامعتبر", reply_markup=get_date_tools_keyboard())

async def _h_birthday(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_shamsi(t)
    if p:
        y, m, d = p[0], p[1], p[2]; set_birth_date(uid, f"{y}/{m}/{d}")
        await u.message.reply_text(birthday_countdown(y, m, d), reply_markup=get_date_tools_keyboard())
    else:
        await u.message.reply_text("❌ نامعتبر", reply_markup=get_date_tools_keyboard())

async def _h_zodiac(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_shamsi(t)
    await u.message.reply_text(zodiac_animal(p[0], p[1], p[2]) if p else "❌", reply_markup=get_date_tools_keyboard())

async def _h_lunar(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_shamsi(t)
    await u.message.reply_text(lunar_age(p[0], p[1], p[2]) if p else "❌", reply_markup=get_date_tools_keyboard())

async def _h_date_diff(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_two_dates(t)
    await u.message.reply_text(date_diff(*p[0], *p[1]) if p else "❌", reply_markup=get_date_tools_keyboard())

async def _h_age_diff(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_two_dates(t)
    await u.message.reply_text(age_diff(*p[0], *p[1]) if p else "❌", reply_markup=get_date_tools_keyboard())

async def _h_event_search(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    await u.message.reply_text(search_events(t), reply_markup=get_date_tools_keyboard())

async def _h_countdown(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_countdown(t)
    await u.message.reply_text(custom_countdown(*p) if p else "❌", reply_markup=get_date_tools_keyboard())

async def _h_calc(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    await u.message.reply_text(calculator(t), reply_markup=get_tools_keyboard())


async def _h_profit(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_profit(t)
    await u.message.reply_text(profit_loss(*p) if p else "❌", reply_markup=get_market_keyboard())

async def _h_currency(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    from bot.features.market.finance import parse_currency_input, SYMBOL_TO_ID, convert_currency as smart_convert
    parsed = parse_currency_input(t)
    if not parsed:
        await u.message.reply_text(
            "❌ مثال:\n"
            "• `20 ton` یا `۱.۵ بیتکوین`\n"
            "• `100 دلار` یا `۵۰ تتر`\n"
            "• `50000 تومان دلار`\n"
            "• `1 btc eth`\n"
            "• `100 usdt toman`",
            reply_markup=get_market_keyboard(),
        )
        return
    amount, a, b = parsed
    try:
        result = await smart_convert(amount, a or "usd", b or "")
        await u.message.reply_text(result, reply_markup=get_market_keyboard())
    except Exception as e:
        await u.message.reply_text(f"⚠️ خطا در تبدیل: {e}", reply_markup=get_market_keyboard())


async def _h_crypto_full(u, c, t, uid):
    """یک پیام واحد: نمودار + تحلیل تکنیکال/فاندامنتال در کپشن"""
    c.user_data.pop("waiting_for", None)
    raw = (t or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    parts = [p for p in raw.replace(",", " ").split() if p]
    symbol = ""
    days = 30
    for p in parts:
        pl = p.lower()
        if pl.replace(".", "", 1).isdigit():
            try:
                days = int(float(p))
            except Exception:
                pass
        elif pl not in ("روز", "day", "days", "نمودار", "chart", "تحلیل", "analyze", "ارز"):
            if not symbol:
                symbol = p
    if not symbol and parts:
        symbol = parts[0]
    if not symbol:
        await u.message.reply_text(
            "❌ نماد را بفرستید. مثال: `btc` یا `eth 30`",
            reply_markup=get_market_keyboard(),
        )
        return

    wait = await u.message.reply_text(f"⏳ در حال آماده‌سازی {symbol.upper()}...")

    # موازی: نمودار + تحلیل
    png = None
    report = ""
    try:
        chart_task = get_crypto_chart(symbol, days)
        # جمع‌بندی AI کوتاه (اختیاری)
        ai_summary = ""
        try:
            base = await analyze_crypto(symbol, ai_summary="")
            try:
                from bot.services.ai_service import ask_ai
                prompt = (
                    "فقط ۲ تا ۴ جمله فارسی، بدون عنوان. "
                    "روند، سیگنال لانگ/شورت/صبر، و یک نکته عملی. توصیه قطعی نده.\\n\\n"
                    + base[:2000]
                )
                answer, _ = await ask_ai(uid, prompt)
                ai_summary = (answer or "").strip().replace("\\n", " ")
                if len(ai_summary) > 260:
                    ai_summary = ai_summary[:260].rsplit(" ", 1)[0] + "…"
            except Exception:
                ai_summary = ""
            report = await analyze_crypto(symbol, ai_summary=ai_summary) if ai_summary else base
        except Exception as e:
            report = f"⚠️ خطا در تحلیل: {e}"

        try:
            png, _cap = await chart_task
        except Exception as e:
            png, _cap = None, str(e)
    except Exception as e:
        report = f"⚠️ خطا: {e}"

    # یک پیام: عکس + کل تحلیل در کپشن
    try:
        await wait.delete()
    except Exception:
        pass

    if png:
        try:
            from io import BytesIO
            bio = BytesIO(png)
            bio.name = f"{symbol}_analysis.png"
            # کپشن حداکثر 1024
            caption = (report or "تحلیل آماده شد.")[:1024]
            await u.message.reply_photo(
                photo=bio,
                caption=caption,
                reply_markup=get_market_keyboard(),
            )
            return
        except Exception as e:
            await u.message.reply_text(
                (report or "") + f"\\n\\n⚠️ نمودار ارسال نشد: {e}",
                reply_markup=get_market_keyboard(),
            )
            return

    await u.message.reply_text(
        report or "❌ داده در دسترس نیست.",
        reply_markup=get_market_keyboard(),
    )


async def _h_crypto_chart(u, c, t, uid):
    return await _h_crypto_full(u, c, t, uid)


async def _h_crypto_analyze(u, c, t, uid):
    return await _h_crypto_full(u, c, t, uid)


async def _h_distance(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    from bot.features.tools.app_tools import parse_two_places
    parsed = parse_two_places(t)
    if not parsed:
        await u.message.reply_text(
            "❌ دو مکان بنویسید.\nمثال: تهران مشهد | تهران تا ترکیه | Paris to Tokyo",
            reply_markup=get_tools_keyboard(),
        )
        return
    p1, p2 = parsed
    await u.message.reply_text(await world_distance(p1, p2), reply_markup=get_tools_keyboard())




async def _h_birth_save(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_shamsi(t)
    if p:
        set_birth_date(uid, f"{p[0]}/{p[1]}/{p[2]}")
        await u.message.reply_text(f"✅ ذخیره شد: {p[0]}/{p[1]}/{p[2]}", reply_markup=get_profile_keyboard())
    else:
        await u.message.reply_text("❌", reply_markup=get_profile_keyboard())

async def _h_count_text(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    await u.message.reply_text(count_text(t), reply_markup=get_tools_keyboard())


async def _h_font_text(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    font = c.user_data.get("selected_font", "bold")
    await u.message.reply_text(apply_font(t, font), reply_markup=get_font_keyboard())


async def _h_font_all(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    await u.message.reply_text(apply_all_fonts(t), reply_markup=get_font_keyboard())


async def _show_azan_settings(update, user_id, city, note: str = None):
    """نمایش پنل تنظیم اذان با وضعیت فعلی و اوقات شرعی"""
    from bot.api.prayer import get_prayer_times, get_next_prayer_time
    from datetime import datetime
    import pytz
    from bot.config import config

    settings = get_azan_settings(user_id)
    times = get_prayer_times(city) or {}
    now = datetime.now(pytz.timezone(config.TIMEZONE))
    nxt_name, nxt_delta = get_next_prayer_time(times, now) if times else (None, None)

    def mark(on: bool) -> str:
        return "✅" if on else "❌"

    lines = [f"🔔 تنظیم اذان — {city}\n"]
    if note:
        lines.append(f"ℹ️ {note}\n")

    master = "روشن ✅" if settings["enabled"] else "خاموش ❌"
    lines.append(f"اعلان کلی: {master}\n")
    lines.append("انتخاب اذان‌ها:")
    lines.append(f"{mark(settings['fajr'])} اذان صبح" + (f"  ({times.get('اذان صبح', '—')})" if times else ""))
    lines.append(f"{mark(settings['dhuhr'])} اذان ظهر" + (f"  ({times.get('اذان ظهر', '—')})" if times else ""))
    lines.append(f"{mark(settings['asr'])} اذان عصر" + (f"  ({times.get('اذان عصر', '—')})" if times else ""))
    lines.append(f"{mark(settings['maghrib'])} اذان مغرب" + (f"  ({times.get('اذان مغرب', '—')})" if times else ""))
    lines.append(f"{mark(settings['isha'])} اذان عشاء" + (f"  ({times.get('اذان عشاء', '—')})" if times else ""))

    if nxt_name and nxt_delta and settings["enabled"]:
        secs = int(nxt_delta.total_seconds())
        h, r = divmod(secs, 3600)
        mi, _ = divmod(r, 60)
        lines.append(f"\n⏳ اذان بعدی: {nxt_name} — {h} ساعت و {mi} دقیقه")
    elif not settings["enabled"]:
        lines.append("\n🔕 اعلان‌ها خاموش است.")

    lines.append("\nروی هر دکمه بزن تا روشن/خاموش شود.")
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=get_azan_keyboard(settings),
    )


async def media_ai_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحلیل عکس و فایل در حالت دستیار هوشمند."""
    if not update.message:
        return
    if not await check_and_rate_limit(update, context):
        return

    # فقط در حالت AI
    if not context.user_data.get("ai_mode"):
        return

    user_id = update.effective_user.id
    msg = update.message
    caption = (msg.caption or "").strip()
    prompt = caption or ""

    images: list[tuple[bytes, str]] = []
    file_text = None
    filename = ""

    try:
        # ویدیو کوتاه
        if msg.video or msg.video_note:
            notice = await msg.reply_text("🎬 در حال تحلیل ویدیو...")
            try:
                v = msg.video or msg.video_note
                tg_file = await v.get_file()
                data = bytes(await tg_file.download_as_bytearray())
                mime = getattr(msg.video, "mime_type", None) or "video/mp4"
                result = await analyze_video(data, prompt, mime=mime)
                await _send_ai_answer(update, user_id, result)
            except Exception as e:
                await msg.reply_text(f"⚠️ ویدیو: {e}", reply_markup=get_ai_keyboard(user_id))
            finally:
                try:
                    await notice.delete()
                except Exception:
                    pass
            return
        # عکس
        if msg.photo:
            photo = msg.photo[-1]  # بالاترین کیفیت
            tg_file = await photo.get_file()
            data = bytes(await tg_file.download_as_bytearray())
            images.append((data, "image/jpeg"))
        # فایل / سند
        elif msg.document:
            doc = msg.document
            filename = doc.file_name or "file"
            mime = doc.mime_type or ""
            # محدودیت حجم ۱۰ مگ
            if doc.file_size and doc.file_size > 10 * 1024 * 1024:
                await msg.reply_text("❌ حجم فایل بیشتر از ۱۰ مگابایت است.")
                return
            tg_file = await doc.get_file()
            data = bytes(await tg_file.download_as_bytearray())

            if mime.startswith("image/") or filename.lower().endswith(
                (".jpg", ".jpeg", ".png", ".webp", ".gif")
            ):
                images.append((data, mime or "image/jpeg"))
            else:
                file_text = _extract_text_from_bytes(data, filename, mime)
                if not file_text.strip():
                    await msg.reply_text(
                        "❌ نتوانستم متن این فایل را بخوانم.\n"
                        "فرمت‌های پشتیبانی‌شده: txt, md, csv, json, pdf, docx و عکس."
                    )
                    return
        else:
            return

        # ویرایش تصویر: عکس + دستور ویرایش
        if images and prompt and looks_like_image_edit(prompt):
            notice = await msg.reply_text("🎨 در حال ویرایش تصویر...")
            try:
                img_bytes, mime = await generate_or_edit_image(
                    prompt,
                    source_image=images[0][0],
                    source_mime=images[0][1],
                )
                from io import BytesIO
                bio = BytesIO(img_bytes)
                bio.name = "edited.png" if "png" in mime else "edited.jpg"
                await msg.reply_photo(
                    photo=bio,
                    caption="🎨 تصویر ویرایش شد",
                    reply_markup=get_ai_keyboard(user_id),
                )
            finally:
                try:
                    await notice.delete()
                except Exception:
                    pass
            return

        notice = await msg.reply_text("✍️ در حال تحلیل...")
        try:
            prompt = enhance_ocr_prompt(prompt, bool(images))
            answer, provider = await ask_ai_media(
                user_id,
                prompt,
                images=images or None,
                file_text=file_text,
                filename=filename,
            )
            await msg.reply_text(
                f"🤖 {answer}",
                reply_markup=get_ai_keyboard(user_id),
            )
        finally:
            try:
                await notice.delete()
            except Exception:
                pass
    except Exception as exc:
        await msg.reply_text(
            "❌ تحلیل ممکن نشد.\n\n" + str(exc)[:2500],
            reply_markup=get_ai_keyboard(user_id),
        )


async def voice_ai_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ویس/صوت ورودی کاربر → متن → جواب AI (و در صورت تمایل ویس خروجی)."""
    if not update.message:
        return
    if not await check_and_rate_limit(update, context):
        return
    if not context.user_data.get("ai_mode"):
        return

    user_id = update.effective_user.id
    msg = update.message
    caption = (msg.caption or "").strip()

    try:
        if msg.voice:
            tg_file = await msg.voice.get_file()
            data = bytes(await tg_file.download_as_bytearray())
            filename, mime = "voice.ogg", "audio/ogg"
        elif msg.audio:
            tg_file = await msg.audio.get_file()
            data = bytes(await tg_file.download_as_bytearray())
            filename = msg.audio.file_name or "audio.mp3"
            mime = msg.audio.mime_type or "audio/mpeg"
        elif msg.video_note:
            # دایره ویدیویی — فقط صدا را نداریم؛ رد می‌کنیم یا download full
            await msg.reply_text("لطفاً ویس معمولی بفرست (نه ویدیو نوت).")
            return
        else:
            return

        if len(data) > 15 * 1024 * 1024:
            await msg.reply_text("❌ حجم ویس خیلی زیاد است.")
            return

        notice = await msg.reply_text("🎧 در حال پیاده‌سازی ویس...")
        try:
            transcript = await speech_to_text(data, filename=filename, mime=mime)
        finally:
            try:
                await notice.delete()
            except Exception:
                pass

        if not transcript:
            await msg.reply_text("❌ چیزی از ویس متوجه نشدم. دوباره واضح‌تر بفرست.")
            return

        # اگر کپشن داشت به متن اضافه کن
        user_text = transcript
        if caption:
            user_text = caption + "\n\n(متن ویس): " + transcript

        await msg.reply_text("📝 شنیدم:\n" + transcript)

        # تشخیص احساس فقط اگر کاربر خواسته باشد
        want_emo = wants_emotion_analysis(caption) or wants_emotion_analysis(transcript)
        if want_emo:
            try:
                emo_notice = await msg.reply_text("💗 در حال تشخیص احساس از صدا...")
                emotion = await analyze_voice_emotion(
                    data, transcript=transcript, filename=filename, mime=mime
                )
                try:
                    await emo_notice.delete()
                except Exception:
                    pass
                await msg.reply_text("🎭 تحلیل احساس صدا:\n" + emotion)
                user_text = (
                    user_text
                    + "\n\n[تحلیل احساس صدای کاربر]\n"
                    + emotion
                )
            except Exception as ee:
                try:
                    await emo_notice.delete()
                except Exception:
                    pass
                from bot.logger import logger
                logger.warning("emotion detect failed: %s", ee)

        # حالت مکالمه ویسی از روی متن ویس یا کپشن
        combined_for_mode = ((caption or "") + " " + (transcript or "")).strip()
        mode_msg = _apply_voice_chat_flags(context, combined_for_mode)
        if mode_msg:
            await msg.reply_text(mode_msg, reply_markup=get_ai_keyboard(user_id))

        # ورودی ویس به خودی خود مکالمه را به سمت ویس می‌برد
        if not context.user_data.get("ai_voice_chat"):
            # اگر گفت ویس حرف بزنیم یا کلاً ویس فرستاد برای گپ، حالت را نرم روشن کن
            if wants_voice_chat_mode(combined_for_mode):
                context.user_data["ai_voice_chat"] = True

        explicit_voice = bool(
            wants_voice_reply(caption or "")
            or wants_voice_reply(transcript or "")
            or context.user_data.get("ai_always_voice")
        )
        voice_chat = bool(context.user_data.get("ai_voice_chat"))

        # اگر فقط درخواست شروع حالت ویس بود
        if mode_msg and wants_voice_chat_mode(combined_for_mode) and len(transcript) < 50:
            try:
                await _send_ai_voice(
                    msg,
                    "باشه، با ویس حرف می‌زنیم. هر وقت خواستی بگو.",
                    user_id,
                )
            except Exception as ve:
                await msg.reply_text(f"⚠️ {ve}")
            return

        # ترجمه زنده ویس
        import re as _re
        tr = _re.search(
            r"ترجمه\s*(به)?\s*(انگلیسی|فارسی|عربی|ترکی|آلمانی|فرانسوی|en|fa|ar|tr|de|fr)?",
            (caption or "") + " " + (transcript or ""),
            _re.I,
        )
        if tr or _re.search(r"\btranslate\b", (caption or ""), _re.I):
            lang_map = {
                "انگلیسی": "en", "en": "en", "فارسی": "fa", "fa": "fa",
                "عربی": "ar", "ar": "ar", "ترکی": "tr", "tr": "tr",
                "آلمانی": "de", "de": "de", "فرانسوی": "fr", "fr": "fr",
            }
            target = "en"
            if tr and tr.group(2):
                target = lang_map.get(tr.group(2).lower(), "en")
            notice = await msg.reply_text("🌐 در حال ترجمه ویس...")
            try:
                src, dst, audio = await translate_voice(
                    data, target_lang=target, filename=filename, mime=mime
                )
                await msg.reply_text(f"📝 اصلی:\n{src}\n\n🌐 ترجمه:\n{dst}")
                from io import BytesIO
                bio = BytesIO(audio)
                bio.name = "tr.mp3"
                await msg.reply_audio(audio=bio, caption="🔊 ترجمه صوتی")
            except Exception as e:
                await msg.reply_text(f"⚠️ ترجمه: {e}")
            finally:
                try:
                    await notice.delete()
                except Exception:
                    pass
            return

        answer, provider = await _ask_ai_with_typing(
            update, context, user_id, user_text
        )
        if not (context.user_data or {}).get("_ai_already_sent"):
            await _send_ai_answer(update, user_id, answer)
        if context.user_data is not None:
            context.user_data.pop("_ai_already_sent", None)
        if should_auto_voice_reply(
            user_text,
            answer,
            input_was_voice=True,
            explicit_voice=explicit_voice,
            voice_chat_mode=bool(voice_chat),  # فقط اگر حالت ویس روشن باشد
        ):
            try:
                await _send_ai_voice(
                    msg, answer, user_id
                )
            except Exception as ve:
                await msg.reply_text(f"⚠️ ویس خروجی ساخته نشد: {ve}")
    except Exception as exc:
        await msg.reply_text(
            "❌ پردازش ویس ممکن نشد.\n\n" + str(exc)[:2500],
            reply_markup=get_ai_keyboard(user_id),
        )

