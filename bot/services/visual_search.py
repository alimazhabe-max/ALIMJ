"""Local, API-free visual search / Lens-like helper for ALIMJ.

The feature is intentionally optional:
- No cloud/API key is required.
- OCR uses local Tesseract when installed.
- Vision uses a local Hugging Face Transformers model (BLIP by default)
  only when a local model directory is available.
- Web lookup uses ordinary DuckDuckGo HTML pages (no API key).

Set LOCAL_VISION_MODEL_PATH to a downloaded local image-captioning model.
Example:
    LOCAL_VISION_MODEL_PATH=/opt/models/blip-image-captioning-base
"""
from __future__ import annotations

import asyncio
import io
import os
import re
from functools import lru_cache
from html import unescape
from typing import Any

import httpx

try:
    from PIL import Image
except Exception:
    Image = None

try:
    import pytesseract
except Exception:
    pytesseract = None

from bot.logger import logger


VISION_MODEL_PATHS = [
    os.getenv("LOCAL_VISION_MODEL_PATH", "").strip(),
    "./models/blip-image-captioning-base",
    "./models/vision",
    "/models/vision",
]
VISION_MAX_NEW_TOKENS = int(os.getenv("LOCAL_VISION_MAX_NEW_TOKENS", "80"))
VISION_TIMEOUT = float(os.getenv("LOCAL_VISION_TIMEOUT", "90"))
SEARCH_TIMEOUT = float(os.getenv("LOCAL_LENS_SEARCH_TIMEOUT", "15"))
SEARCH_RESULTS = max(1, min(8, int(os.getenv("LOCAL_LENS_SEARCH_RESULTS", "5"))))

_DDG_URL = "https://html.duckduckgo.com/html/"


def looks_like_visual_search(text: str | None) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    patterns = (
        "گوگل لنز", "google lens", "لنز", "جستجوی عکس", "جستجوی تصویری",
        "جستجو عکس", "جستجو تصویر", "سرچ عکس", "سرچ تصویری",
        "این عکس چیه", "این تصویر چیه", "این چیه",
        "پیدا کن این عکس", "پیدا کن این تصویر", "محصول این عکس",
        "what is this", "search image", "visual search", "identify this",
        "find this product",
    )
    return any(p in t for p in patterns)


def _clean_text(text: str) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _ocr(image_bytes: bytes) -> str:
    if pytesseract is None or Image is None:
        return ""
    try:
        with Image.open(io.BytesIO(image_bytes)) as im:
            # Persian+English if installed; fall back to English.
            lang = os.getenv("LOCAL_OCR_LANG", "fas+eng")
            try:
                return _clean_text(pytesseract.image_to_string(im, lang=lang))
            except Exception:
                return _clean_text(pytesseract.image_to_string(im, lang="eng"))
    except Exception as exc:
        logger.warning("Local OCR failed: %s", exc)
        return ""


@lru_cache(maxsize=1)
def _load_vision_pipeline():
    """Load a local Transformers image-captioning pipeline only.

    No model download is attempted. If the model is absent, return None.
    """
    model_path = next((p for p in VISION_MODEL_PATHS if p and os.path.isdir(p)), "")
    if not model_path:
        return None

    try:
        from transformers import BlipForConditionalGeneration, BlipProcessor

        processor = BlipProcessor.from_pretrained(model_path, local_files_only=True)
        model = BlipForConditionalGeneration.from_pretrained(
            model_path, local_files_only=True
        )
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model.to(device)
        except Exception:
            device = "cpu"
        model.eval()
        return processor, model, device
    except Exception as exc:
        logger.warning("Local vision model unavailable: %s", exc)
        return None


def _vision_caption_sync(image_bytes: bytes) -> str:
    if Image is None:
        return ""
    loaded = _load_vision_pipeline()
    if not loaded:
        return ""
    processor, model, device = loaded
    try:
        import torch
        with Image.open(io.BytesIO(image_bytes)).convert("RGB") as im:
            inputs = processor(images=im, return_tensors="pt")
            inputs = {k: v.to(device) if hasattr(v, "to") else v for k, v in inputs.items()}
            with torch.inference_mode():
                out = model.generate(
                    **inputs,
                    max_new_tokens=VISION_MAX_NEW_TOKENS,
                    num_beams=3,
                )
            return _clean_text(processor.decode(out[0], skip_special_tokens=True))
    except Exception as exc:
        logger.warning("Local vision inference failed: %s", exc)
        return ""


async def local_vision_caption(image_bytes: bytes) -> str:
    return await asyncio.wait_for(
        asyncio.to_thread(_vision_caption_sync, image_bytes),
        timeout=VISION_TIMEOUT,
    )


def _keywords(*texts: str) -> list[str]:
    joined = " ".join(t for t in texts if t)
    words = re.findall(r"[\w\u0600-\u06ff][\w\u0600-\u06ff\-]{2,}", joined.lower())
    stop = {
        "this", "that", "image", "photo", "picture", "there", "with",
        "the", "and", "from", "برای", "این", "یک", "است", "دارد",
        "عکس", "تصویر", "در", "با", "روی", "شده",
    }
    out = []
    for w in words:
        if w in stop or w in out:
            continue
        out.append(w)
        if len(out) >= 12:
            break
    return out


async def _web_search(query: str) -> list[dict[str, str]]:
    if not query:
        return []
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(SEARCH_TIMEOUT, connect=5),
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 ALIMJ-VisualLens/1.0"},
        ) as client:
            r = await client.get(_DDG_URL, params={"q": query})
            r.raise_for_status()
            html = r.text

        results = []
        # DDG's HTML result blocks are intentionally parsed conservatively.
        for block in re.findall(
            r'<div[^>]+class="result[^"]*"[^>]*>(.*?)</div>\s*</div>',
            html,
            flags=re.I | re.S,
        ):
            title_m = re.search(r'class="result__a"[^>]*>(.*?)</a>', block, re.I | re.S)
            url_m = re.search(r'class="result__a"[^>]+href="([^"]+)"', block, re.I | re.S)
            snip_m = re.search(r'class="result__snippet"[^>]*>(.*?)</a?>', block, re.I | re.S)
            if not title_m or not url_m:
                continue
            title = _clean_text(title_m.group(1))
            url = unescape(url_m.group(1))
            snippet = _clean_text(snip_m.group(1) if snip_m else "")
            if title and url:
                results.append({"title": title, "url": url, "snippet": snippet})
            if len(results) >= SEARCH_RESULTS:
                break
        return results
    except Exception as exc:
        logger.warning("Lens web search failed: %s", exc)
        return []


async def visual_search(image_bytes: bytes, caption: str = "") -> str:
    if not image_bytes:
        raise ValueError("تصویر خالی است.")

    metadata = ""
    if Image is not None:
        try:
            with Image.open(io.BytesIO(image_bytes)) as im:
                metadata = f"{im.width}×{im.height}، {im.format or 'unknown'}"
        except Exception:
            pass

    ocr_task = asyncio.to_thread(_ocr, image_bytes)
    vision_task = local_vision_caption(image_bytes)
    ocr, vision = await asyncio.gather(
        ocr_task,
        vision_task,
        return_exceptions=True,
    )
    ocr = "" if isinstance(ocr, Exception) else ocr
    vision = "" if isinstance(vision, Exception) else vision

    keys = _keywords(caption, vision, ocr)
    query_parts = [caption.strip(), vision, ocr, " ".join(keys)]
    query = " ".join(x for x in query_parts if x).strip()
    # Avoid sending only generic Lens trigger words.
    query = re.sub(r"\b(google lens|visual search|search image)\b", " ", query, flags=re.I)
    query = re.sub(r"(گوگل لنز|لنز|جستجوی عکس|جستجوی تصویری|سرچ عکس)", " ", query, flags=re.I)
    query = re.sub(r"\s+", " ", query).strip()[:500]

    results = await _web_search(query)

    lines = ["🔎 تحلیل تصویری (Lens داخلی)"]
    if metadata:
        lines.append(f"📐 تصویر: {metadata}")
    lines.append(f"👁️ مدل بینایی محلی: {vision or 'در دسترس نبود'}")
    lines.append(f"📝 OCR: {ocr or 'متنی پیدا نشد'}")
    if keys:
        lines.append("🏷️ کلیدواژه‌ها: " + "، ".join(keys))

    if results:
        lines.append("\n🌐 نتایج جستجو:")
        for i, item in enumerate(results, 1):
            lines.append(f"{i}. {item['title']}\n{item['url']}")
            if item["snippet"]:
                lines.append(f"   {item['snippet'][:300]}")
    else:
        lines.append("\n🌐 نتیجه وبی پیدا نشد.")

    lines.append(
        "\nℹ️ این قابلیت کاملاً بدون API Key کار می‌کند. "
        "برای تشخیص دقیق‌تر، مدل بینایی محلی باید روی سرور موجود باشد."
    )
    return "\n".join(lines)
