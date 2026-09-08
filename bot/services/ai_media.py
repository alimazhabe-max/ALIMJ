"""Media, voice, image, music and video helpers for AI service.

Kept separate from the main AI router to keep modules focused and easier to test.
Runtime dependencies are imported from ai_service after its initialization.
"""
from __future__ import annotations

import asyncio
import base64
import os
import re
from pathlib import Path
from urllib.parse import quote
from typing import List, Optional
import httpx

from bot.logger import logger
from bot.utils.observability import record as record_metric
from bot.utils.task_manager import spawn

from bot.services import ai_service as _ai

# Runtime aliases are resolved only when this module is imported lazily by the facade.
TIMEOUT = _ai.TIMEOUT
MAX_OUTPUT = _ai.MAX_OUTPUT
GEMINI_SAFETY_SETTINGS = _ai.GEMINI_SAFETY_SETTINGS
IMAGE_GEN_MODEL = _ai.IMAGE_GEN_MODEL
IMAGE_GEN_MODEL_FALLBACKS = _ai.IMAGE_GEN_MODEL_FALLBACKS
TTS_VOICE = _ai.TTS_VOICE

_next_keys = _ai._next_keys
_advance_rr = _ai._advance_rr
_call_provider = _ai._call_provider
_get_http = _ai._get_http
_post_json = _ai._post_json
_is_quota_error = _ai._is_quota_error
_mark_key_cooldown = _ai._mark_key_cooldown
available_model_options = _ai.available_model_options

_LOCAL_PIPELINE = None
_LOCAL_PIPELINE_MODEL = None
_LOCAL_BACKEND_CACHE = None

async def _get_image_bytes(url: str, *, headers=None) -> tuple[int, bytes, str]:
    """GET image endpoint and return status, bytes, content-type."""
    client = _get_http()
    response = await client.get(url, headers=headers, follow_redirects=True)
    return response.status_code, response.content, response.headers.get("content-type", "")


async def _generate_image_pollinations(prompt: str) -> tuple[bytes, str]:
    """Pollinations anonymous/free fallback. No key is required for the fallback path."""
    model = os.getenv("POLLINATIONS_IMAGE_MODEL", "flux").strip() or "flux"
    width = int(os.getenv("POLLINATIONS_IMAGE_WIDTH", "1024"))
    height = int(os.getenv("POLLINATIONS_IMAGE_HEIGHT", "1024"))
    encoded = quote(prompt, safe="")
    urls = [
        f"https://gen.pollinations.ai/image/{encoded}?model={quote(model)}&width={width}&height={height}",
        f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}",
    ]
    errors = []
    for url in urls:
        try:
            status, content, mime = await _get_image_bytes(url)
            if status < 400 and content and (content.startswith(b"\\x89PNG") or content.startswith(b"\\xff\\xd8") or "image" in mime.lower()):
                return content, mime or "image/png"
            errors.append(f"HTTP {status}")
        except Exception as exc:
            errors.append(str(exc)[:200])
    raise RuntimeError("Pollinations در دسترس نبود: " + " | ".join(errors[:3]))


_LOCAL_PIPELINE = None
_LOCAL_PIPELINE_MODEL = None
_LOCAL_BACKEND_CACHE = None


def _find_local_image_model() -> Optional[str]:
    """فقط مدل‌هایی را برمی‌گرداند که واقعاً روی سیستم موجودند؛ دانلود خودکار انجام نمی‌دهد."""
    candidates = []
    configured = os.getenv("LOCAL_IMAGE_MODEL_PATH", "").strip()
    if configured:
        candidates.append(configured)
    for raw in os.getenv("LOCAL_IMAGE_MODEL_PATHS", "./models/image,./models/sd15,./models/sdxl,/models/image").split(","):
        raw = raw.strip()
        if raw:
            candidates.append(raw)
    for item in candidates:
        path = Path(item).expanduser()
        if path.exists() and path.is_dir():
            # diffusers models normally have model_index.json; allow common single-file dirs too.
            if (path / "model_index.json").exists() or any(path.glob("*.safetensors")):
                return str(path)
    return None


async def _detect_local_backend() -> tuple[str, str] | None:
    """هوشمندانه backend محلی موجود را پیدا می‌کند؛ هیچ چیزی دانلود نمی‌شود."""
    global _LOCAL_BACKEND_CACHE
    if _LOCAL_BACKEND_CACHE is not None:
        return _LOCAL_BACKEND_CACHE

    client = _get_http()
    candidates = []
    configured = os.getenv("LOCAL_IMAGE_API_URL", "").strip().rstrip("/")
    if configured:
        candidates.append(("a1111", configured))
    candidates.extend([
        ("a1111", "http://127.0.0.1:7860"),
        ("comfyui", "http://127.0.0.1:8188"),
    ])

    for backend, base in candidates:
        try:
            if backend == "a1111":
                r = await client.get(f"{base}/sdapi/v1/sd-models", timeout=3)
                if r.status_code < 400:
                    _LOCAL_BACKEND_CACHE = (backend, base)
                    return _LOCAL_BACKEND_CACHE
            else:
                r = await client.get(f"{base}/system_stats", timeout=3)
                if r.status_code < 400:
                    _LOCAL_BACKEND_CACHE = (backend, base)
                    return _LOCAL_BACKEND_CACHE
        except Exception:
            continue

    model_path = _find_local_image_model()
    if model_path:
        _LOCAL_BACKEND_CACHE = ("diffusers", model_path)
        return _LOCAL_BACKEND_CACHE
    return None


async def _generate_image_a1111(prompt: str, base_url: str) -> tuple[bytes, str]:
    """تولید تصویر از Stable Diffusion WebUI/Forge API روی همان سرور."""
    client = _get_http()
    payload = {
        "prompt": prompt,
        "steps": int(os.getenv("LOCAL_IMAGE_STEPS", "20")),
        "width": int(os.getenv("LOCAL_IMAGE_WIDTH", "512")),
        "height": int(os.getenv("LOCAL_IMAGE_HEIGHT", "512")),
        "batch_size": 1,
        "n_iter": 1,
    }
    response = await client.post(
        f"{base_url}/sdapi/v1/txt2img",
        json=payload,
        timeout=max(TIMEOUT, 120),
    )
    if response.status_code >= 400:
        raise RuntimeError(f"A1111 HTTP {response.status_code}: {response.text[:300]}")
    data = response.json()
    images = data.get("images") or []
    if not images:
        raise RuntimeError("A1111 تصویری برنگرداند")
    return base64.b64decode(images[0]), "image/png"


async def _generate_image_local(prompt: str) -> tuple[bytes, str]:
    """Local fallback with automatic backend detection (A1111/Forge → Diffusers)."""
    global _LOCAL_PIPELINE, _LOCAL_PIPELINE_MODEL

    backend = await _detect_local_backend()
    if not backend:
        raise RuntimeError("هیچ موتور تصویر محلی روی سرور پیدا نشد")

    backend_name, backend_value = backend
    if backend_name == "a1111":
        return await _generate_image_a1111(prompt, backend_value)

    model_path = backend_value if backend_name == "diffusers" else _find_local_image_model()
    if not model_path:
        raise RuntimeError("مدل Diffusers محلی پیدا نشد")

    try:
        import io
        import torch
        from diffusers import AutoPipelineForText2Image
    except Exception as exc:
        raise RuntimeError(f"وابستگی‌های local image نصب نیستند: {exc}")

    if _LOCAL_PIPELINE is None or _LOCAL_PIPELINE_MODEL != model_path:
        def _load():
            pipe = AutoPipelineForText2Image.from_pretrained(
                model_path,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                local_files_only=True,
            )
            if torch.cuda.is_available():
                pipe = pipe.to("cuda")
            return pipe
        _LOCAL_PIPELINE = await asyncio.to_thread(_load)
        _LOCAL_PIPELINE_MODEL = model_path

    def _run():
        image = _LOCAL_PIPELINE(prompt, num_inference_steps=int(os.getenv("LOCAL_IMAGE_STEPS", "20"))).images[0]
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()

    return await asyncio.to_thread(_run), "image/png"


async def generate_or_edit_image(
    prompt: str,
    *,
    source_image: bytes | None = None,
    source_mime: str = "image/jpeg",
) -> tuple[bytes, str]:
    """ساخت/ویرایش تصویر با انتخاب خودکار اولین سرویس در دسترس.

    ترتیب پیش‌فرض: Gemini → Pollinations → Local.
    سرویس‌هایی که کلید/مدل لازم را ندارند خودکار رد می‌شوند. برای ویرایش عکس،
    سرویس‌هایی که فقط text-to-image هستند برای ویرایش عکس رد می‌شوند.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise RuntimeError("توضیح تصویر خالی است.")

    errors: List[str] = []

    # 1) Gemini: اگر کلید موجود باشد امتحان می‌شود؛ quota failure جلوی fallback را نمی‌گیرد.
    gemini_keys = _next_keys("gemini")
    if gemini_keys:
        models: List[str] = []
        for candidate in (IMAGE_GEN_MODEL, *IMAGE_GEN_MODEL_FALLBACKS):
            candidate = (candidate or "").strip()
            if candidate and candidate not in models:
                models.append(candidate)
        parts = []
        if source_image:
            if len(source_image) > 4_500_000:
                raise RuntimeError("حجم تصویر برای ویرایش خیلی بزرگ است.")
            parts.append({"inline_data": {"mime_type": source_mime or "image/jpeg", "data": base64.b64encode(source_image).decode("ascii")}})
            full_prompt = "Edit this image according to the following instruction. Return the edited image.\n\n" + prompt
        else:
            full_prompt = "Generate a high-quality image for this request. Return an image.\n\n" + prompt
        parts.append({"text": full_prompt})
        payload = {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}, "safetySettings": GEMINI_SAFETY_SETTINGS}

        for key in gemini_keys:
            for model in models:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                    status, data = await _post_json(url, params={"key": key}, json=payload)
                    if status >= 400:
                        err = data.get("error", {}) if isinstance(data, dict) else {}
                        detail = str(err.get("message") or err.get("status") or data).replace("\n", " ")[:450]
                        errors.append(f"gemini/{model} HTTP {status}: {detail}")
                        if _is_quota_error(status, data):
                            _mark_key_cooldown("gemini", key, daily=(status == 403))
                        continue
                    for part in ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []:
                        inline = part.get("inlineData") or part.get("inline_data")
                        if inline and inline.get("data"):
                            return base64.b64decode(inline["data"]), inline.get("mimeType") or inline.get("mime_type") or "image/png"
                    errors.append(f"gemini/{model}: تصویر برنگشت")
                except Exception as exc:
                    errors.append(f"gemini/{model}: {str(exc)[:250]}")
    else:
        errors.append("gemini: کلید موجود نیست")

    # 2) Pollinations: بدون کلید امتحان می‌شود؛ برای text-to-image.
    if not source_image:
        try:
            return await _generate_image_pollinations(prompt)
        except Exception as exc:
            errors.append(f"pollinations: {str(exc)[:350]}")
    else:
        errors.append("pollinations: برای ویرایش عکس رد شد")

    # 3) Local: فقط اگر مدل از قبل روی دیسک موجود باشد؛ هیچ دانلود خودکاری انجام نمی‌شود.
    try:
        return await _generate_image_local(prompt)
    except Exception as exc:
        errors.append(f"local: {str(exc)[:350]}")

    raise RuntimeError(
        "هیچ سرویس تصویر در دسترس نبود. سیستم همه گزینه‌های موجود را خودکار بررسی کرد.\n"
        + " | ".join(errors[:10])
    )


def extract_image_prompt(text: str) -> str:
    """دستور ساخت تصویر را از فرمان کاربر جدا می‌کند."""
    t = (text or "").strip()
    if not t:
        return ""
    import re
    patterns = (
        r"^/image(?:@\w+)?\s*[:：-]?\s*",
        r"^(?:تصویر|عکس)\s*(?:بساز|تولید کن|تولیدش کن|درست کن)\s*[:：-]?\s*",
        r"^(?:یک|یه)\s+(?:تصویر|عکس)\s+(?:بساز|درست کن)\s*[:：-]?\s*",
        r"^(?:generate|create)\s+(?:an?\s+)?image\s*[:：-]?\s*",
        r"^draw(?:\s+me)?\s*[:：-]?\s*",
    )
    for pattern in patterns:
        cleaned = re.sub(pattern, "", t, count=1, flags=re.I).strip()
        if cleaned != t:
            return cleaned[:5000]
    return t[:5000]


def looks_like_image_request(text: str) -> bool:
    """آیا پیام درخواست ساخت تصویر است؟"""
    t = (text or "").strip()
    if not t:
        return False
    # درخواست‌های صریح ساخت تصویر
    patterns = (
        r"تصویر\s*(?:بساز|تولید(?:\s*کن|ش\s*کن)?|درست\s*کن|ایجاد\s*کن)",
        r"عکس\s*(?:بساز|تولید(?:\s*کن|ش\s*کن)?|درست\s*کن|ایجاد\s*کن)",
        r"(?:نقاشی|طرح|پوستر|پرتره|لوگو|والپیپر|تصویرسازی)\s*(?:بساز|درست\s*کن|ایجاد\s*کن|طراحی\s*کن)",
        r"بکش",
        r"نقاشی\s*کن",
        r"طراحی\s*کن",
        r"پرامپت\s*تصویر",
        r"generate\s+(?:an?\s+)?image",
        r"draw(?:\s+me)?\s+",
        r"create\s+(?:an?\s+)?image",
        r"image\s+of",
    )
    import re
    if any(re.search(p, t, re.I) for p in patterns):
        return True

    # حالت محاوره‌ای فارسی مثل: «یک پارک در حال باران بساز»
    # فقط وقتی فعال می‌شود که فعل ساخت با یک موضوع بصری همراه باشد تا
    # درخواست‌هایی مثل «یک برنامه بساز» اشتباهاً تصویر محسوب نشوند.
    visual_terms = (
        r"عکس|تصویر|پارک|منظره|طبیعت|آسمان|دریا|کوه|جنگل|خیابان|شهر|خانه|"
        r"ماشین|موتور|شخص|مرد|زن|بچه|کاراکتر|شخصیت|حیوان|گربه|سگ|"
        r"باران|برف|غروب|طلوع|ماه|خورشید|گل|درخت|دشت|ساحل|لوگو|پوستر|"
        r"پرتره|نقاشی|طرح|والپیپر|فانتزی|سینمایی|واقع‌گرایانه|انیمه"
    )
    creation_verbs = r"بساز|درست\s*کن|ایجاد\s*کن|تولید\s*کن|طراحی\s*کن"
    if re.search(rf"(?:^|\s)(?:یک|یه|یکى)?\s*.+\s+(?:{creation_verbs})\s*$", t, re.I):
        return bool(re.search(visual_terms, t, re.I))

    return False


def looks_like_image_edit(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    patterns = (
        r"ویرایش",
        r"تغییر\s*بده",
        r"عوض\s*کن",
        r"اضافه\s*کن",
        r"حذف\s*کن",
        r"edit\s+(this\s+)?image",
        r"change\s+",
        r"remove\s+",
        r"add\s+",
        r"بدل\s*کن",
        r"سبک\s*",
    )
    import re
    return any(re.search(p, t, re.I) for p in patterns)



# ── تبدیل متن به ویس (TTS) ─────────────────────────────────────────────────

TTS_VOICE = os.getenv("TTS_VOICE", "fa-IR-DilaraNeural")  # فارسی زن
# جایگزین‌ها: fa-IR-FaridNeural (مرد)



# ── ویس → متن (Speech-to-Text) ─────────────────────────────────────────────

async def speech_to_text(
    audio_bytes: bytes,
    *,
    filename: str = "voice.ogg",
    mime: str = "audio/ogg",
) -> str:
    """
    تبدیل ویس/صوت به متن.
    اولویت: Groq Whisper → سپس Gemini.
    """
    if not audio_bytes:
        raise RuntimeError("فایل صوتی خالی است.")

    errors = []

    # ۱) Groq Whisper (سریع و معمولاً رایگان در سهمیه)
    groq_keys = _next_keys("groq")
    if groq_keys:
        import httpx as _httpx

        for key in groq_keys:
            try:
                url = (
                    os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
                    + "/audio/transcriptions"
                )
                model = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
                files = {
                    "file": (filename or "audio.ogg", audio_bytes, mime or "audio/ogg"),
                }
                data = {
                    "model": model,
                    "language": os.getenv("STT_LANGUAGE", "fa"),  # فارسی
                    "response_format": "text",
                }
                headers = {"Authorization": f"Bearer {key}"}
                async with _httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(
                        url, headers=headers, data=data, files=files
                    )
                if resp.status_code >= 400:
                    if _is_quota_error(resp.status_code, resp.text):
                        _mark_key_cooldown("groq", key, daily=True)
                        errors.append(f"groq STT HTTP {resp.status_code}")
                        continue
                    errors.append(f"groq STT HTTP {resp.status_code}: {resp.text[:200]}")
                    continue
                text = (resp.text or "").strip()
                # گاهی JSON برمی‌گردد
                if text.startswith("{"):
                    try:
                        import json as _json
                        text = (_json.loads(text).get("text") or "").strip()
                    except Exception:
                        pass
                if text:
                    _advance_rr("groq")
                    return text
                errors.append("groq STT empty")
            except Exception as e:
                errors.append(f"groq STT: {e}")
                continue

    # ۲) Gemini (ورودی audio)
    gemini_keys = _next_keys("gemini")
    if gemini_keys:
        model = os.getenv("GEMINI_STT_MODEL", "gemini-3.1-flash-lite")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": mime or "audio/ogg",
                                "data": base64.b64encode(audio_bytes).decode("ascii"),
                            }
                        },
                        {
                            "text": (
                                "این فایل صوتی را دقیقاً به متن پیاده کن. "
                                "فقط متن گفتار را برگردان، بدون توضیح اضافه."
                            )
                        },
                    ],
                }
            ],
            "generationConfig": {"maxOutputTokens": 2048},
            "safetySettings": GEMINI_SAFETY_SETTINGS,
        }
        for key in gemini_keys:
            try:
                status, data = await _post_json(url, params={"key": key}, json=payload)
                if status >= 400:
                    if _is_quota_error(status, data):
                        _mark_key_cooldown("gemini", key, daily=True)
                    errors.append(f"gemini STT HTTP {status}")
                    continue
                parts = data["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts).strip()
                if text:
                    _advance_rr("gemini")
                    return text
                errors.append("gemini STT empty")
            except Exception as e:
                errors.append(f"gemini STT: {e}")
                continue

    raise RuntimeError(
        "نتوانستم ویس را به متن تبدیل کنم. کلید Groq یا Gemini لازم است.\n"
        + " | ".join(errors[:5])
    )



async def analyze_voice_emotion(
    audio_bytes: bytes,
    *,
    transcript: str = "",
    filename: str = "voice.ogg",
    mime: str = "audio/ogg",
) -> str:
    """
    تشخیص احساسات و لحن از روی صدا (و در صورت وجود متن پیاده‌شده).
    با Gemini روی خود فایل صوتی کار می‌کند.
    """
    if not audio_bytes:
        raise RuntimeError("فایل صوتی خالی است.")

    keys = _next_keys("gemini")
    if not keys:
        # بدون Gemini: تخمین ضعیف از روی متن
        if transcript:
            return _emotion_from_text_fallback(transcript)
        raise RuntimeError("برای تشخیص احساس از صدا به کلید Gemini نیاز است.")

    if len(audio_bytes) > 4_500_000:
        audio_bytes = audio_bytes[:4_500_000]

    model = os.getenv("GEMINI_EMOTION_MODEL", os.getenv("GEMINI_STT_MODEL", "gemini-3.1-flash-lite"))
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    prompt = (
        "تو یک تحلیل‌گر لحن و احساس صدا هستی. این فایل صوتی را گوش بده "
        "(و اگر متن پیاده‌شده آمد از آن هم کمک بگیر) و به فارسی پاسخ بده.\n\n"
        "ساختار پاسخ دقیقاً این باشد:\n"
        "😊 احساس غالب: ...\n"
        "📊 شدت (۰ تا ۱۰): ...\n"
        "🎙 لحن/انرژی: ...\n"
        "💬 احساسات فرعی: ...\n"
        "📝 توضیح کوتاه: ...\n\n"
        "احساسات ممکن: شادی، غم، عصبانیت، اضطراب، آرامش، هیجان، خستگی، "
        "اعتمادبه‌نفس، تردید، مهربانی، بی‌حوصلگی، ترس، تعجب.\n"
        "اگر صدا واضح نبود صادقانه بگو."
    )
    if transcript:
        prompt += f"\n\nمتن پیاده‌شده از صدا:\n{transcript[:1500]}"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime or "audio/ogg",
                            "data": base64.b64encode(audio_bytes).decode("ascii"),
                        }
                    },
                    {"text": prompt},
                ],
            }
        ],
        "generationConfig": {"maxOutputTokens": 800},
        "safetySettings": GEMINI_SAFETY_SETTINGS,
    }

    errors = []
    for key in keys:
        try:
            status, data = await _post_json(url, params={"key": key}, json=payload)
            if status >= 400:
                if _is_quota_error(status, data):
                    _mark_key_cooldown("gemini", key, daily=True)
                    errors.append(f"HTTP {status}")
                    continue
                raise RuntimeError(f"Gemini emotion HTTP {status}: {str(data)[:400]}")
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(x.get("text", "") for x in parts).strip()
            if text:
                _advance_rr("gemini")
                return text
            errors.append("empty")
        except Exception as e:
            errors.append(str(e)[:200])
            continue

    if transcript:
        return _emotion_from_text_fallback(transcript)
    raise RuntimeError("تشخیص احساس ناموفق: " + " | ".join(errors[:4]))


def _emotion_from_text_fallback(transcript: str) -> str:
    """تخمین خیلی ساده فقط از روی واژه‌ها (وقتی Gemini نباشد)."""
    t = (transcript or "").lower()
    rules = [
        (["عصبانی", "خفه", "لعنت", "حالم بده از", "کیفم کوک نیست"], "عصبانیت"),
        (["میترسم", "نگران", "استرس", "دلهره"], "اضطراب/نگرانی"),
        (["خوشحالم", "عالی", "محشر", "عاشق", "خنده‌ام"], "شادی"),
        (["غمگین", "گریه", "دلتنگ", "تنها", "سخت"], "غم"),
        (["خسته‌ام", "حالم نیست", "بی‌حال"], "خستگی"),
        (["آروم", "خوبه", "ممنون", "مرسی"], "آرامش"),
    ]
    found = []
    for words, label in rules:
        if any(w in t for w in words):
            found.append(label)
    if not found:
        found = ["خنثی / نامشخص از روی متن"]
    return (
        "😊 احساس غالب (تخمین از متن، نه صدا): "
        + "، ".join(found)
        + "\n📝 برای تشخیص دقیق از لحن صدا، کلید Gemini لازم است."
    )


async def text_to_speech(text: str, *, voice: str | None = None) -> bytes:
    """
    متن → فایل صوتی ogg/mp3 (edge-tts، بدون نیاز به API Key).
    خروجی bytes مناسب ارسال با reply_voice در تلگرام.
    """
    text = (text or "").strip()
    if not text:
        raise RuntimeError("متن خالی است.")
    # تلگرام برای voice محدودیت حدود ۱ دقیقه دارد؛ متن را کمی محدود کن
    if len(text) > 1200:
        text = text[:1200] + " …"

    voice = voice or TTS_VOICE
    try:
        import edge_tts
        import tempfile
        from pathlib import Path as _P

        communicate = edge_tts.Communicate(text, voice)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp = f.name
        await communicate.save(tmp)
        data = _P(tmp).read_bytes()
        try:
            _P(tmp).unlink(missing_ok=True)
        except Exception:
            pass
        if not data:
            raise RuntimeError("فایل صوتی خالی بود.")
        return data
    except ImportError:
        raise RuntimeError(
            "کتابخانه edge-tts نصب نیست. در requirements.txt بنویس: edge-tts"
        )
    except Exception as e:
        raise RuntimeError(f"ساخت ویس ناموفق: {e}")




def wants_emotion_analysis(text: str) -> bool:
    """آیا کاربر صریحاً تشخیص احساس از صدا خواسته؟"""
    t = (text or "").strip()
    if not t:
        return False
    import re
    patterns = (
        r"تشخیص\s*احساس",
        r"احساس(ات)?\s*(من|صدا|از\s*صدا)?",
        r"لحن(م|م\s*چطور)",
        r"از\s*صدا(م)?\s*(بگو|تحلیل|تشخیص)",
        r"حالم\s*از\s*صدا",
        r"emotion",
        r"تحلیل\s*احساس",
        r"چه\s*احساسی",
    )
    return any(re.search(p, t, re.I) for p in patterns)


def wants_voice_chat_mode(text: str) -> bool:
    """درخواست شروع مکالمه ویسی پایدار (نه فقط یک‌بار)."""
    t = (text or "").strip()
    if not t:
        return False
    import re
    patterns = (
        r"ویس\s*حرف\s*بزن",
        r"با\s*ویس\s*حرف",
        r"حرف\s*بزنیم\s*(با\s*)?ویس",
        r"صحبت\s*(صوتی|ویسی|با\s*صدا)",
        r"چت\s*صوتی",
        r"مکالمه\s*(ی\s*)?(صوتی|ویسی)",
        r"از\s*این\s*به\s*بعد\s*(با\s*)?(ویس|صدا)",
        r"فقط\s*ویس",
        r"voice\s*chat",
        r"let'?s\s*talk\s*(by\s*)?voice",
        r"با\s*صدا\s*حرف",
        r"صدا\s*حرف\s*بزن",
        r"بیا\s*ویس",
        r"ویس\s*باش",
        r"حالت\s*ویس",
        r"حالت\s*صوتی",
    )
    return any(re.search(p, t, re.I) for p in patterns)


def wants_end_voice_chat(text: str) -> bool:
    """پایان حالت مکالمه ویسی."""
    t = (text or "").strip()
    if not t:
        return False
    import re
    patterns = (
        r"قطع\s*ویس",
        r"بدون\s*ویس",
        r"دیگه\s*ویس\s*ن",
        r"متن(ی)?\s*حرف\s*بزن",
        r"حالت\s*متنی",
        r"ویس\s*رو\s*خاموش",
        r"خاموش\s*کردن\s*ویس",
        r"end\s*voice",
        r"stop\s*voice",
        r"فقط\s*متن",
    )
    return any(re.search(p, t, re.I) for p in patterns)


def wants_voice_reply(text: str) -> bool:
    """درخواست صریح ویس برای همین پیام."""
    t = (text or "").strip()
    if not t:
        return False
    import re
    if wants_voice_chat_mode(t):
        return True
    patterns = (
        r"^با\s*ویس\b",
        r"^با\s*صدا\b",
        r"^ویس\s*[:：]",
        r"^صدا\s*[:：]",
        r"ویس\s*بفرست",
        r"صدا\s*بفرست",
        r"بفرست\s*ویس",
        r"بفرست\s*صدا",
        r"فایل\s*صوتی",
        r"صوتی\s*بفرست",
        r"\bبا\s*ویس\s*بگو\b",
        r"\bبا\s*صدا\s*بگو\b",
        r"\bجواب(تو)?\s*(رو\s*)?با\s*ویس\b",
        r"\bجواب(تو)?\s*(رو\s*)?با\s*صدا\b",
        r"\bبرام\s*بخون\b",
        r"\bspeak\b",
        r"\bvoice\s*reply\b",
        r"\btts\b",
        r"send\s*(a\s*)?voice",
    )
    return any(re.search(p, t, re.I) for p in patterns)


def is_voice_only_request(text: str) -> bool:
    """فقط درخواست ویس بدون سؤال دیگر (مثل: ویس بفرست)."""
    t = (text or "").strip()
    if not t:
        return False
    import re
    t2 = re.sub(
        r"^(لطفا|خواهشا|میشه|میتونی|می‌تونی)\s*",
        "",
        t,
        flags=re.I,
    ).strip()
    patterns = (
        r"^ویس\s*بفرست\s*$",
        r"^صدا\s*بفرست\s*$",
        r"^بفرست\s*ویس\s*$",
        r"^بفرست\s*صدا\s*$",
        r"^با\s*ویس\s*$",
        r"^با\s*صدا\s*$",
        r"^بخون\s*$",
        r"^بخوان\s*$",
        r"^voice\s*$",
        r"^tts\s*$",
        r"^فایل\s*صوتی\s*بفرست\s*$",
    )
    return any(re.search(p, t2, re.I) for p in patterns)



def strip_voice_prefix(text: str) -> str:
    import re
    t = (text or "").strip()
    t = re.sub(
        r"^(با\s*ویس|با\s*صدا|ویس|صدا)\s*[:：]?\s*",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(r"\b(با\s*ویس\s*بگو|با\s*صدا\s*بگو)\b", "", t, flags=re.I)
    return t.strip() or text.strip()


def should_auto_voice_reply(
    user_text: str,
    answer: str,
    *,
    input_was_voice: bool = False,
    explicit_voice: bool = False,
    voice_chat_mode: bool = False,
) -> bool:
    """
    ویس فقط وقتی:
      ۱) کاربر صریحاً خواسته (با ویس / بخون / ...)
      ۲) حالت مکالمه ویسی روشن است («ویس حرف بزنیم»)
    ورودی ویس به‌تنهایی کافی نیست — الکی ویس نمی‌فرستد.
    """
    ans = (answer or "").strip()
    if not ans:
        return False

    # فقط درخواست صریح یا حالت مکالمه ویسی
    if explicit_voice or voice_chat_mode:
        return True

    return False




# ── موسیقی / افکت صوتی (Gemini Lyria در صورت پشتیبانی کلید) ────────────────

async def generate_music(prompt: str) -> bytes:
    """
    ساخت کلیپ صوتی.
    اولویت: مدل‌های Lyria / پاسخ AUDIO در Gemini.
    اگر API موسیقی ندهد، خطای واضح برمی‌گرداند.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise RuntimeError("توضیح موسیقی خالی است.")
    keys = _next_keys("gemini")
    if not keys:
        raise RuntimeError("برای ساخت موسیقی به کلید Gemini نیاز است.")

    models = [
        os.getenv("GEMINI_MUSIC_MODEL", "").strip(),
        "lyria-3-clip-preview",
        "lyria-3-pro-preview",
    ]
    models = [m for m in models if m]
    # حذف تکراری با حفظ ترتیب
    seen = set()
    models = [m for m in models if not (m in seen or seen.add(m))]

    errors = []
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payloads = [
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        },
    ]
        for key in keys:
            for payload in payloads:
                try:
                    status, data = await _post_json(url, params={"key": key}, json=payload)
                    if status >= 400:
                        errors.append(f"{model} HTTP {status}")
                        if _is_quota_error(status, data):
                            _mark_key_cooldown("gemini", key, daily=True)
                        continue
                    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts") or []
                    for part in parts:
                        inline = part.get("inlineData") or part.get("inline_data")
                        if inline and inline.get("data"):
                            raw = base64.b64decode(inline["data"])
                            if raw:
                                _advance_rr("gemini")
                                return raw
                    errors.append(f"{model}: no audio part")
                except Exception as e:
                    errors.append(str(e)[:120])
    raise RuntimeError(
        "ساخت موسیقی روی این کلید/مدل در دسترس نبود. "
        "مدل Lyria باید روی پروژه Google AI Studio فعال باشد.\n"
        + " | ".join(errors[:5])
    )



async def analyze_video(
    video_bytes: bytes,
    prompt: str = "",
    *,
    mime: str = "video/mp4",
) -> str:
    """تحلیل ویدیو کوتاه با Gemini."""
    keys = _next_keys("gemini")
    if not keys:
        raise RuntimeError("برای تحلیل ویدیو به Gemini نیاز است.")
    if len(video_bytes) > 15_000_000:
        raise RuntimeError("ویدیو خیلی بزرگ است (حد حدود ۱۵ مگ).")

    model = os.getenv("GEMINI_VIDEO_MODEL", "gemini-3.1-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    text = (prompt or "").strip() or (
        "این ویدیو کوتاه را خلاصه و تحلیل کن: موضوع، افراد/اشیاء مهم، "
        "متن یا گفتار شنیده‌شده، و نکات کلیدی."
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime or "video/mp4",
                            "data": base64.b64encode(video_bytes).decode("ascii"),
                        }
                    },
                    {"text": text},
                ],
            }
        ],
        "generationConfig": {"maxOutputTokens": MAX_OUTPUT},
        "safetySettings": GEMINI_SAFETY_SETTINGS,
    }
    errors = []
    for key in keys:
        try:
            status, data = await _post_json(url, params={"key": key}, json=payload)
            if status >= 400:
                if _is_quota_error(status, data):
                    _mark_key_cooldown("gemini", key, daily=True)
                errors.append(f"HTTP {status}")
                continue
            parts = data["candidates"][0]["content"]["parts"]
            out = "".join(x.get("text", "") for x in parts).strip()
            if out:
                _advance_rr("gemini")
                return out
        except Exception as e:
            errors.append(str(e)[:150])
    raise RuntimeError("تحلیل ویدیو ناموفق: " + " | ".join(errors[:4]))


async def translate_voice(
    audio_bytes: bytes,
    *,
    target_lang: str = "en",
    filename: str = "voice.ogg",
    mime: str = "audio/ogg",
) -> tuple[str, str, bytes]:
    """ویس → متن → ترجمه → ویس مقصد. خروجی: (متن اصلی, ترجمه, audio)."""
    src_text = await speech_to_text(audio_bytes, filename=filename, mime=mime)
    target_lang = (target_lang or "en").lower()
    lang_name = {
        "en": "English",
        "fa": "Persian",
        "ar": "Arabic",
        "tr": "Turkish",
        "de": "German",
        "fr": "French",
    }.get(target_lang, target_lang)

    prompt = (
        "Translate the following text to "
        + lang_name
        + ". Return only the translation.\n\n"
        + src_text
    )
    translated = None
    options = available_model_options()
    for provider, _label, model in options:
        try:
            translated = await _call_provider(provider, 0, prompt, model)
            if translated:
                break
        except Exception:
            continue
    if not translated:
        raise RuntimeError("ترجمه ناموفق بود.")

    voice = TTS_VOICE
    if target_lang.startswith("en"):
        voice = "en-US-JennyNeural"
    elif target_lang.startswith("ar"):
        voice = "ar-SA-ZariyahNeural"
    elif target_lang.startswith("de"):
        voice = "de-DE-KatjaNeural"
    elif target_lang.startswith("fr"):
        voice = "fr-FR-DeniseNeural"
    elif target_lang.startswith("tr"):
        voice = "tr-TR-EmelNeural"
    elif target_lang.startswith("fa"):
        voice = TTS_VOICE

    audio_out = await text_to_speech(translated, voice=voice)
    return src_text, translated, audio_out



