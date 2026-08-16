from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from bot.database import get_user, get_user_city, set_last_main_msg_id
from bot.services.ai_service import (
    clear_history,
    available_providers,
    set_selected_provider,
    get_selected_model,
)
from bot.utils.helpers import (
    build_message,
    get_refresh_button,
    get_main_keyboard, get_more_keyboard, get_ai_keyboard, get_ai_model_keyboard,
    get_calendar_buttons,
    get_calendar_text,
)
from bot.api.calendar import get_today_tehran
from bot.handlers.middleware import check_and_rate_limit
import jdatetime
import asyncio


# جلوگیری از اجرای همزمان چند بروزرسانی برای یک کاربر
_refresh_locks = {}


def _get_refresh_lock(user_id: int):
    lock = _refresh_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _refresh_locks[user_id] = lock
    return lock


async def _safe_answer(query, text: str = None, show_alert: bool = False):
    """پاسخ به callback فقط یک‌بار؛ اگر قبلاً جواب داده شده باشد بی‌صدا رد می‌شود."""
    try:
        if text is None:
            await query.answer()
        else:
            await query.answer(text, show_alert=show_alert)
    except Exception:
        pass


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # نکته مهم: callback_query را فقط یک‌بار می‌توان answer کرد.
    # answer اولیه را حذف کردیم تا شاخه‌هایی که نیاز به Toast دارند
    # (مثل refresh_main و عضویت کانال) بتوانند پیام مناسب نشان دهند.

    if not await check_and_rate_limit(update, context):
        # middleware در صورت نیاز خودش answer کرده؛ در غیر این صورت spinner را قطع می‌کنیم
        await _safe_answer(query)
        return

    data = query.data
    user_id = update.effective_user.id

    if data == "ai_models":
        await _safe_answer(query)
        await query.edit_message_reply_markup(reply_markup=get_ai_model_keyboard(user_id))
        return

    if data == "ai_models_back":
        await _safe_answer(query)
        await query.edit_message_reply_markup(reply_markup=get_ai_keyboard(user_id))
        return

    if data == "ai_noop":
        await _safe_answer(query, "هیچ مدل فعالی تنظیم نشده است.", show_alert=True)
        return

    if data.startswith("ai_provider:") or data.startswith("ai_model:"):
        # ai_provider: انتخاب ارائه‌دهنده (همه مدل‌هایش شامل می‌شود)
        # ai_model: سازگاری با پیام‌های قدیمی
        try:
            index = int(data.split(":", 1)[1])
            providers = available_providers()
            provider, label = providers[index]
        except (ValueError, IndexError):
            await _safe_answer(query, "❌ این سرویس دیگر در دسترس نیست.", show_alert=True)
            return
        set_selected_provider(user_id, provider)
        await _safe_answer(query, f"✅ فعال شد: {label}", show_alert=False)
        await query.edit_message_reply_markup(reply_markup=get_ai_keyboard(user_id))
        return

    if data == "ai_clear_memory":
        clear_history(user_id)
        await _safe_answer(query, "حافظه AI پاک شد ✅", show_alert=False)
        try:
            await query.edit_message_reply_markup(
                reply_markup=get_ai_keyboard(user_id)
            )
        except Exception:
            pass
        await query.message.reply_text("✅ حافظه گفت‌وگو و خلاصه پاک شد. (حافظه بلندمدت با «پاک کردن همه حافظه» حذف می‌شود)")
        return

    if data == "ai_exit":
        context.user_data.pop("ai_mode", None)
        context.user_data.pop("waiting_for", None)
        await _safe_answer(query)
        await query.message.reply_text("➕ منوی بیشتر:", reply_markup=get_more_keyboard())
        return

    if data.startswith("ai_tts:"):
        from bot.services.ai_extras import get_stored_answer
        from bot.services.ai_service import text_to_speech
        from io import BytesIO
        aid = data.split(":", 1)[1]
        text = get_stored_answer(aid, user_id)
        if not text:
            await _safe_answer(query, "این جواب منقضی شده. دوباره بپرس.", show_alert=True)
            return
        await _safe_answer(query, "در حال ویس دادن...")
        try:
            notice = await query.message.reply_text("🔊 در حال ویس دادن...")
            audio = await text_to_speech(text)
            bio = BytesIO(audio)
            bio.name = "answer.mp3"
            await query.message.reply_audio(audio=bio, caption="🔊")
            try:
                await notice.delete()
            except Exception:
                pass
        except Exception as e:
            await query.message.reply_text(f"⚠️ ویس ساخته نشد: {e}")
        return

    if data.startswith("ai_quick:"):
        kind = data.split(":", 1)[1]
        await _safe_answer(query)
        try:
            from bot.database import get_user_city
            city = get_user_city(user_id) or "تهران"
            if kind == "weather":
                from bot.api.weather import get_weather
                w = get_weather(city)
                if w:
                    txt = f"🌤 هوای {city}:\nدما {w.get('temp')}°C\n{w.get('condition')}\nرطوبت {w.get('humidity')}%"
                else:
                    txt = "هوا در دسترس نیست."
            elif kind == "price":
                from bot.features.market.finance import full_market_prices
                txt = await full_market_prices()
            elif kind == "istikhara":
                from bot.features.religious.istikhara import istikhara
                txt = await istikhara(user_id)
            elif kind == "prayer":
                from bot.api.prayer import get_prayer_times
                pt = get_prayer_times(city)
                if pt:
                    txt = f"🕌 اوقات شرعی {city}:\n" + "\n".join(f"{k}: {v}" for k, v in pt.items())
                else:
                    txt = "اوقات شرعی در دسترس نیست."
            else:
                txt = "دکمه نامعتبر."
            await query.message.reply_text(txt)
        except Exception as e:
            await query.message.reply_text(f"⚠️ {e}")
        return

    # ───────────────── بروزرسانی منوی اصلی ─────────────────
    if data == "refresh_main":
        from bot.logger import logger

        lock = _get_refresh_lock(user_id)

        if lock.locked():
            await _safe_answer(query, "⏳ بروزرسانی قبلی هنوز در حال انجام است.", show_alert=False)
            return

        async with lock:
            await _safe_answer(query, "🔄 در حال بروزرسانی...", show_alert=False)

            chat_id = None
            message_id = None
            try:
                if query.message is not None:
                    chat_id = query.message.chat_id
                    message_id = query.message.message_id
                elif update.effective_chat is not None:
                    chat_id = update.effective_chat.id
            except Exception as e:
                logger.warning("refresh_main resolve chat: %s", e)
                try:
                    chat_id = update.effective_chat.id if update.effective_chat else None
                except Exception:
                    chat_id = None

            try:
                user_row = None
                try:
                    user_row = get_user(user_id)
                except Exception as e:
                    logger.warning("refresh_main get_user: %s", e)

                first_name = "کاربر"
                try:
                    if user_row and len(user_row) > 1 and user_row[1]:
                        first_name = str(user_row[1])
                except Exception:
                    pass

                city = "قم"
                try:
                    city = get_user_city(user_id) or "قم"
                except Exception as e:
                    logger.warning("refresh_main get_user_city: %s", e)

                try:
                    message = await build_message(user_id, first_name, city)
                except Exception as e:
                    logger.error("refresh_main build_message: %s", e, exc_info=True)
                    message = (
                        f"🌟 سلام {first_name} عزیز!\n\n"
                        f"⚠️ بارگذاری اطلاعات با خطا مواجه شد.\n"
                        f"کد: {type(e).__name__}\n"
                        f"/start را بفرستید."
                    )

                if not message:
                    message = "⚠️ محتوا خالی بود. /start را بفرستید."
                if len(message) > 4000:
                    message = message[:3990] + "\n…"

                sent = False

                # روش ۱: edit از طریق callback_query
                if not sent:
                    try:
                        await query.edit_message_text(
                            text=message,
                            reply_markup=get_refresh_button(),
                        )
                        sent = True
                        if message_id:
                            context.user_data["last_main_msg_id"] = message_id
                            try:
                                set_last_main_msg_id(user_id, message_id)
                            except Exception:
                                pass
                    except BadRequest as e:
                        err = str(e).lower()
                        if "message is not modified" in err or "not modified" in err:
                            sent = True
                        else:
                            logger.warning("refresh_main query.edit BadRequest: %s", e)
                    except Exception as e:
                        logger.warning("refresh_main query.edit: %s", e)

                # روش ۲: edit مستقیم با bot API
                if not sent and chat_id and message_id:
                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=message,
                            reply_markup=get_refresh_button(),
                        )
                        sent = True
                        context.user_data["last_main_msg_id"] = message_id
                        try:
                            set_last_main_msg_id(user_id, message_id)
                        except Exception:
                            pass
                    except BadRequest as e:
                        err = str(e).lower()
                        if "message is not modified" in err or "not modified" in err:
                            sent = True
                        else:
                            logger.warning("refresh_main bot.edit BadRequest: %s", e)
                    except Exception as e:
                        logger.warning("refresh_main bot.edit: %s", e)

                # روش ۳: ارسال پیام جدید
                if not sent and chat_id:
                    try:
                        msg = await context.bot.send_message(
                            chat_id=chat_id,
                            text=message,
                            reply_markup=get_refresh_button(),
                        )
                        sent = True
                        context.user_data["last_main_msg_id"] = msg.message_id
                        try:
                            set_last_main_msg_id(user_id, msg.message_id)
                        except Exception:
                            pass
                        if message_id:
                            try:
                                await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                            except Exception:
                                pass
                    except Exception as e:
                        logger.error("refresh_main send: %s", e, exc_info=True)

                if not sent:
                    tip = "⚠️ بروزرسانی انجام نشد."
                    if chat_id:
                        tip += " لطفاً /start را بفرستید."
                    else:
                        tip += " چت پیدا نشد؛ /start را بفرستید."
                    try:
                        if chat_id:
                            await context.bot.send_message(chat_id=chat_id, text=tip)
                    except Exception:
                        pass

            except Exception as e:
                logger.error("refresh_main outer: %s", e, exc_info=True)
                try:
                    cid = chat_id
                    if cid is None and update.effective_chat:
                        cid = update.effective_chat.id
                    if cid:
                        await context.bot.send_message(
                            chat_id=cid,
                            text=(
                                "⚠️ بروزرسانی موقتاً ناموفق بود.\n"
                                f"کد خطا: {type(e).__name__}: {str(e)[:120]}\n"
                                "چند ثانیه بعد دوباره بزنید یا /start بفرستید."
                            ),
                        )
                except Exception:
                    pass
        return

    if data == "back_to_main":
        from bot.logger import logger
        await _safe_answer(query)
        try:
            user_row = get_user(user_id)
            first_name = (
                (user_row[1] if user_row and len(user_row) > 1 and user_row[1] else None)
                or "کاربر"
            )
            try:
                city = get_user_city(user_id) or "قم"
            except Exception:
                city = "قم"

            try:
                message = await build_message(user_id, first_name, city)
            except Exception as e:
                logger.error(
                    f"build_message failed in back_to_main: {type(e).__name__}: {e}",
                    exc_info=True,
                )
                message = (
                    f"🌟 سلام {first_name} عزیز!\n\n"
                    f"⚠️ بارگذاری کامل اطلاعات با خطا مواجه شد.\n"
                    f"دستور /start را بفرستید.\n"
                    f"({type(e).__name__})"
                )

            if len(message) > 4000:
                message = message[:3990] + "\n…"

            sent = False
            # 1) ویرایش همان پیام
            try:
                await query.edit_message_text(message, reply_markup=get_refresh_button())
                context.user_data["last_main_msg_id"] = query.message.message_id
                try:
                    set_last_main_msg_id(user_id, query.message.message_id)
                except Exception:
                    pass
                sent = True
            except Exception as e1:
                logger.warning(f"back_to_main edit failed: {type(e1).__name__}: {e1}")

            # 2) اگر edit نشد، پیام جدید با bot.send_message
            if not sent:
                try:
                    msg = await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=message,
                        reply_markup=get_refresh_button(),
                    )
                    context.user_data["last_main_msg_id"] = msg.message_id
                    try:
                        set_last_main_msg_id(user_id, msg.message_id)
                    except Exception:
                        pass
                    sent = True
                    try:
                        await query.message.delete()
                    except Exception:
                        pass
                except Exception as e2:
                    logger.error(
                        f"back_to_main send failed: {type(e2).__name__}: {e2}",
                        exc_info=True,
                    )

            # کیبورد اصلی پایین
            try:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="",
                    reply_markup=get_main_keyboard(),
                )
            except Exception:
                pass

            if not sent:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="⚠️ بازگشت به منو ناموفق بود. لطفاً /start را بفرستید.",
                )
        except Exception as e:
            logger.error(f"back_to_main outer error: {type(e).__name__}: {e}", exc_info=True)
            try:
                chat_id = update.effective_chat.id if update.effective_chat else None
                if chat_id:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "⚠️ موقتاً مشکلی پیش آمد. دستور /start را بفرستید.\n"
                            f"کد خطا: {type(e).__name__}"
                        ),
                    )
            except Exception:
                pass
        return

    if data == "calendar_today":
        await _safe_answer(query)
        today = get_today_tehran()
        text = get_calendar_text(today.year, today.month, today.day, user_id)
        await query.edit_message_text(
            text,
            reply_markup=get_calendar_buttons(today.year, today.month, today.day, user_id)
        )
        return

    if data.startswith("day_"):
        await _safe_answer(query)
        parts = data.split("_")
        year, month, day = int(parts[1]), int(parts[2]), int(parts[3])
        try:
            jdatetime.date(year, month, day)
        except ValueError:
            if day < 1:
                month -= 1
                if month < 1:
                    month = 12
                    year -= 1
                last_day = jdatetime.date(year, month, 1) - jdatetime.timedelta(days=1)
                day = last_day.day
            else:
                month += 1
                if month > 12:
                    month = 1
                    year += 1
                day = 1
        text = get_calendar_text(year, month, day, user_id)
        await query.edit_message_text(
            text,
            reply_markup=get_calendar_buttons(year, month, day, user_id)
        )
        return

    if data.startswith("cal_"):
        await _safe_answer(query)
        parts = data.split("_")
        year, month, day = int(parts[1]), int(parts[2]), int(parts[3])
        if month < 1:
            month = 12
            year -= 1
        elif month > 12:
            month = 1
            year += 1
        text = get_calendar_text(year, month, day, user_id)
        await query.edit_message_text(
            text,
            reply_markup=get_calendar_buttons(year, month, day, user_id)
        )
        return


    # ── منوی تحلیل کریپتو (cx:action:symbol) ─────────────────
    if data.startswith("cx:"):
        await _safe_answer(query)
        parts = data.split(":")
        if len(parts) < 3:
            await query.message.reply_text("❌ درخواست نامعتبر")
            return
        action, symbol = parts[1], parts[2]
        context.user_data["crypto_symbol"] = symbol
        try:
            from bot.features.market.finance import (
                analyze_crypto, get_crypto_chart, get_crypto_analysis_keyboard,
                trading_recommendation, derivatives_radar, risk_scenarios,
                position_size_guide, entry_alert_text,
            )
            menu = get_crypto_analysis_keyboard(symbol)
            if action == "sum":
                txt = await analyze_crypto(symbol)
                await query.message.reply_text(txt[:4000], reply_markup=menu)
            elif action == "day":
                wait = await query.message.reply_text("⏳ نمودار روزانه...")
                png, cap = await get_crypto_chart(symbol, 90)
                try:
                    await wait.delete()
                except Exception:
                    pass
                if png:
                    from io import BytesIO
                    bio = BytesIO(png)
                    bio.name = f"{symbol}_daily.png"
                    await query.message.reply_photo(photo=bio, caption=(cap or "نمودار روزانه")[:1024], reply_markup=menu)
                else:
                    await query.message.reply_text(cap or "❌ نمودار روزانه در دسترس نیست", reply_markup=menu)
            elif action == "hr":
                wait = await query.message.reply_text("⏳ نمودار ساعتی...")
                png, cap = await get_crypto_chart(symbol, 7)
                try:
                    await wait.delete()
                except Exception:
                    pass
                if png:
                    from io import BytesIO
                    bio = BytesIO(png)
                    bio.name = f"{symbol}_hourly.png"
                    await query.message.reply_photo(photo=bio, caption=(cap or "نمودار ساعتی")[:1024], reply_markup=menu)
                else:
                    await query.message.reply_text(cap or "❌ نمودار ساعتی در دسترس نیست", reply_markup=menu)
            elif action == "rec":
                txt = await trading_recommendation(symbol)
                await query.message.reply_text(txt, reply_markup=menu)
            elif action == "der":
                txt = await derivatives_radar(symbol)
                await query.message.reply_text(txt, reply_markup=menu)
            elif action == "risk":
                txt = await risk_scenarios(symbol)
                await query.message.reply_text(txt, reply_markup=menu)
            elif action == "pos":
                context.user_data["waiting_for"] = "crypto_pos"
                await query.message.reply_text(position_size_guide(symbol), reply_markup=menu)
            elif action == "al":
                context.user_data["waiting_for"] = "crypto_alert"
                txt = await entry_alert_text(symbol)
                await query.message.reply_text(txt, reply_markup=menu)
            elif action == "ref":
                wait = await query.message.reply_text("⏳ بروزرسانی...")
                txt = await analyze_crypto(symbol)
                png, cap = await get_crypto_chart(symbol, 30)
                try:
                    await wait.delete()
                except Exception:
                    pass
                if png:
                    from io import BytesIO
                    bio = BytesIO(png)
                    bio.name = f"{symbol}_ref.png"
                    await query.message.reply_photo(
                        photo=bio,
                        caption=(txt + "\n\n🔄 بروزرسانی شد")[:1024],
                        reply_markup=menu,
                    )
                else:
                    await query.message.reply_text(txt[:4000], reply_markup=menu)
            else:
                await query.message.reply_text("❌ گزینه ناشناخته", reply_markup=menu)
        except Exception as e:
            await query.message.reply_text(f"⚠️ خطا: {e}")
        return

    # هر callback ناشناخته‌ای — حداقل spinner را قطع کن
    await _safe_answer(query)
