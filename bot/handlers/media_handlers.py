"""Media and voice Telegram handlers extracted from messages.py (V25).

The public handler names remain available from bot.handlers.messages via thin
compatibility wrappers, so existing registrations and imports continue to work.
"""
from __future__ import annotations

from io import BytesIO
import re

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.middleware import check_and_rate_limit
from bot.logger import logger
from bot.services.ai_service import (
    _extract_text_from_bytes, ask_ai_media, analyze_video, generate_or_edit_image,
    looks_like_image_edit, speech_to_text,
    analyze_voice_emotion, should_auto_voice_reply, wants_voice_reply,
    wants_voice_chat_mode, wants_end_voice_chat, is_voice_only_request,
    translate_voice, wants_emotion_analysis,
)
from bot.services.ai_extras import enhance_ocr_prompt
from bot.services.visual_search import looks_like_visual_search
from bot.features.market.shopping import search_shopping
from bot.services.visual_search import visual_search
from bot.utils.helpers import get_ai_keyboard

async def media_ai_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحلیل عکس و فایل در حالت دستیار هوشمند."""
    # Imported lazily to avoid a circular import with messages.py compatibility facade.
    from bot.handlers.messages import (
        _send_ai_answer, _send_ai_voice, _ask_ai_with_typing, _apply_voice_chat_flags,
    )
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

        # Visual Lens: مسیر کاملاً جدا از تحلیل قدیمی عکس.
        # فقط با درخواست صریح Lens/جستجوی تصویری فعال می‌شود.
        if images and prompt and looks_like_visual_search(prompt):
            notice = await msg.reply_text("🔎 در حال بررسی تصویر با Lens محلی...")
            try:
                result = await visual_search(images[0][0], caption=prompt)
                await msg.reply_text(
                    result[:4000],
                    reply_markup=get_ai_keyboard(user_id),
                )
            finally:
                try:
                    await notice.delete()
                except Exception:
                    pass
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

        # خرید از روی عکس: همه‌چیز داخل همان دستیار هوشمند انجام می‌شود.
        # ابتدا Vision فقط یک عبارت جستجوی کوتاه و قابل‌استفاده می‌سازد؛ سپس موتور خرید واقعاً وب/فروشگاه‌ها را می‌گردد.
        shopping_image_intent = bool(
            images and prompt and re.search(
                r"خرید|قیمت|فروشگاه|فروشنده|لینک|پیدا.?کن|مشابه|ارزان|سرچ|جستجو|شاپ|buy|price|shop|find",
                prompt, re.I,
            )
        )
        if images and shopping_image_intent:
            notice = await msg.reply_text("🛒 در حال تشخیص محصول و جستجوی واقعی فروشگاه‌ها...")
            try:
                vision_prompt = (
                    "این عکس یک محصول است. فقط یک عبارت جستجوی کوتاه برای پیدا کردن همین محصول یا مشابه نزدیک آن بنویس. "
                    "برند، مدل، نوع محصول، رنگ، جنس، طرح و ویژگی‌های قابل‌تشخیص را وارد کن. "
                    "حداکثر 18 کلمه؛ بدون توضیح، بدون قیمت و بدون جمله اضافی."
                )
                search_query, _ = await ask_ai_media(
                    user_id, vision_prompt, images=images, file_text=file_text, filename=filename
                )
                search_query = re.sub(r"[\n\r]+", " ", (search_query or "")).strip()[:500]
                if not search_query:
                    search_query = prompt[:500]

                from bot.features.market.shopping import search_shopping
                shopping_result = await search_shopping(
                    query=search_query, source="all", max_results=10, user_id=user_id
                )
                # اگر موتور خرید هیچ لینک واقعی نداد، Lens وب را به‌عنوان fallback اجرا کن.
                if "🔗" not in shopping_result:
                    shopping_result = await visual_search(
                        images[0][0], caption=search_query, include_web=True
                    )
                await msg.reply_text(
                    "🛒 جستجوی خرید بر اساس عکس\n\n" + shopping_result[:7000],
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
    # Imported lazily to avoid a circular import with messages.py compatibility facade.
    from bot.handlers.messages import (
        _send_ai_answer, _send_ai_voice, _ask_ai_with_typing, _apply_voice_chat_flags,
    )
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

