"""ALIMJ Visual Lens - API-free visual/product search helper.

Features
--------
* Optional local vision model (BLIP via transformers/torch).
* Optional local OCR (Tesseract + Pillow).
* Multi-query web retrieval using DuckDuckGo HTML (no API key).
* Soft ranking: exact match is NOT required; similar results are kept.
* Safe fallbacks when optional ML dependencies/models are unavailable.

Environment variables
---------------------
LOCAL_VISION_MODEL_PATH : local HuggingFace model directory. If empty, the
                          vision model is disabled unless an existing cached
                          Transformers model can be loaded by name.
LOCAL_VISION_MODEL      : model id/name, default Salesforce/blip-image-captioning-base.
TESSERACT_CMD            : path to tesseract executable, if not on PATH.
VISION_MAX_QUERIES       : maximum web queries, default 7.
VISION_MAX_RESULTS       : results per query, default 6.
VISION_HTTP_TIMEOUT      : HTTP timeout, default 12 seconds.
VISION_SEARCH_REGION     : DuckDuckGo region, default wt-wt.
"""

from __future__ import annotations

import asyncio
import html
import io
import os
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable, Optional
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None


DEFAULT_VISION_MODEL = os.getenv(
    "LOCAL_VISION_MODEL", "Salesforce/blip-image-captioning-base"
)
LOCAL_VISION_MODEL_PATH = os.getenv("LOCAL_VISION_MODEL_PATH", "").strip()
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "").strip()
MAX_QUERIES = max(3, int(os.getenv("VISION_MAX_QUERIES", "7")))
MAX_RESULTS_PER_QUERY = max(3, int(os.getenv("VISION_MAX_RESULTS", "6")))
HTTP_TIMEOUT = float(os.getenv("VISION_HTTP_TIMEOUT", "12"))
SEARCH_REGION = os.getenv("VISION_SEARCH_REGION", "wt-wt")


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    score: float = 0.0
    matched_query: str = ""


_STOPWORDS = {
    "و", "در", "از", "با", "برای", "به", "یک", "این", "آن", "است", "که",
    "را", "روی", "داخل", "شده", "شود", "می", "های", "the", "a", "an", "of",
    "and", "with", "for", "to", "in", "on", "this", "that", "is", "are", "image",
    "photo", "picture", "product", "find", "search", "similar", "item",
}


def _normalize(text: str) -> str:
    text = (text or "").lower()
    replacements = {
        "ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه",
        "ؤ": "و", "إ": "ا", "أ": "ا", "ٱ": "ا",
        "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
        "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    }
    for a, b in replacements.items():
        text = text.replace(a, b)
    text = re.sub(r"[^\w\u0600-\u06ff\s.-]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text: str) -> list[str]:
    return [
        t for t in _normalize(text).split()
        if len(t) > 1 and t not in _STOPWORDS
    ]


def _unique(items: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        item = _normalize(item)
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _extract_keywords(text: str, limit: int = 14) -> list[str]:
    words = _tokens(text)
    if not words:
        return []
    counts = Counter(words)
    return [w for w, _ in counts.most_common(limit)]


def _image_info(image_bytes: bytes) -> dict[str, Any]:
    if Image is None:
        return {}
    try:
        with Image.open(io.BytesIO(image_bytes)) as im:
            return {
                "format": im.format or "unknown",
                "width": im.width,
                "height": im.height,
                "mode": im.mode,
                "aspect_ratio": round(im.width / max(1, im.height), 3),
            }
    except Exception:
        return {}


def _ocr(image_bytes: bytes) -> str:
    """Run Tesseract locally. Returns empty text when OCR is unavailable."""
    try:
        import pytesseract
        if TESSERACT_CMD:
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        elif shutil.which("tesseract") is None:
            return ""
        if Image is None:
            return ""
        with Image.open(io.BytesIO(image_bytes)) as im:
            im = im.convert("RGB")
            texts = []
            for lang in ("fas+eng", "eng"):
                try:
                    txt = pytesseract.image_to_string(im, lang=lang, config="--psm 6")
                    if txt and len(txt.strip()) > 1:
                        texts.append(txt.strip())
                        if lang == "fas+eng":
                            break
                except Exception:
                    continue
            return "\n".join(_unique(texts))[:2500]
    except Exception:
        return ""


# BLIP is deliberately lazy-loaded: normal bot startup does not import torch.
_VISION_STATE: dict[str, Any] = {"ready": False, "failed": False, "processor": None, "model": None}


def _vision_model_source() -> str:
    return LOCAL_VISION_MODEL_PATH or DEFAULT_VISION_MODEL


def _load_vision_model() -> tuple[Any, Any] | tuple[None, None]:
    if _VISION_STATE["ready"]:
        return _VISION_STATE["processor"], _VISION_STATE["model"]
    if _VISION_STATE["failed"]:
        return None, None
    try:
        from transformers import BlipProcessor, BlipForConditionalGeneration
        import torch  # noqa: F401

        source = _vision_model_source()
        # Do not silently download on Render when a local path was explicitly requested.
        if LOCAL_VISION_MODEL_PATH and not os.path.exists(LOCAL_VISION_MODEL_PATH):
            _VISION_STATE["failed"] = True
            return None, None

        processor = BlipProcessor.from_pretrained(source, local_files_only=bool(LOCAL_VISION_MODEL_PATH))
        model = BlipForConditionalGeneration.from_pretrained(source, local_files_only=bool(LOCAL_VISION_MODEL_PATH))
        model.eval()
        _VISION_STATE.update({"ready": True, "processor": processor, "model": model})
        return processor, model
    except Exception:
        _VISION_STATE["failed"] = True
        return None, None


def _vision_caption(image_bytes: bytes) -> str:
    if Image is None:
        return ""
    processor, model = _load_vision_model()
    if processor is None or model is None:
        return ""
    try:
        import torch
        with Image.open(io.BytesIO(image_bytes)) as im:
            image = im.convert("RGB")
        inputs = processor(images=image, return_tensors="pt")
        with torch.no_grad():
            output = model.generate(**inputs, max_new_tokens=45, num_beams=3)
        return processor.decode(output[0], skip_special_tokens=True).strip()
    except Exception:
        return ""


def _strip_ddg_url(url: str) -> str:
    url = html.unescape(url or "").strip()
    if url.startswith("//"):
        url = "https:" + url
    try:
        parsed = urlparse(url)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            target = parse_qs(parsed.query).get("uddg", [""])[0]
            if target:
                return unquote(target)
    except Exception:
        pass
    return url


def _clean_html(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


async def _ddg_search(query: str, limit: int = MAX_RESULTS_PER_QUERY) -> list[SearchResult]:
    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ALIMJ-VisualLens/2.0; +https://example.com)",
        "Accept-Language": "fa,en;q=0.8",
    }
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True, headers=headers) as client:
            response = await client.get(url, params={"q": query, "kl": SEARCH_REGION})
            response.raise_for_status()
        body = response.text
    except Exception:
        return []

    results: list[SearchResult] = []
    # DuckDuckGo HTML markup is intentionally parsed conservatively.
    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<div class="result|$)',
        re.I | re.S,
    )
    for match in pattern.finditer(body):
        raw_url, raw_title, tail = match.groups()
        title = _clean_html(raw_title)
        link = _strip_ddg_url(raw_url)
        snippet_match = re.search(r'class="result__snippet"[^>]*>(.*?)</(?:a|div)>', tail, re.I | re.S)
        snippet = _clean_html(snippet_match.group(1)) if snippet_match else ""
        if title and link.startswith(("http://", "https://")):
            results.append(SearchResult(title=title, url=link, snippet=snippet, matched_query=query))
        if len(results) >= limit:
            break
    return results


def _query_variants(description: str, ocr: str, caption: str = "") -> list[str]:
    """Generate short, complementary queries instead of one overly-specific sentence."""
    text = " ".join(x for x in (description, caption, ocr) if x)
    keys = _extract_keywords(text, 16)
    if not keys:
        return []

    # Keep phrases around product nouns/visual attributes, but avoid a huge exact sentence.
    variants: list[str] = []
    base = " ".join(keys[:6])
    if base:
        variants.append(base)
    if len(keys) >= 3:
        variants.append(" ".join(keys[:3]) + " محصول")
        variants.append(" ".join(keys[:3]) + " خرید")
    if len(keys) >= 5:
        variants.append(" ".join(keys[:5]) + " فروشگاه")
        variants.append(" ".join(keys[1:6]))

    # English fallback can improve recall for globally indexed product pages.
    english_terms = [
        k for k in keys
        if re.fullmatch(r"[a-z0-9.-]+", k)
    ]
    if english_terms:
        variants.append(" ".join(english_terms[:6]) + " product")

    # Always have a broader query based on the first semantic terms.
    variants.append(" ".join(keys[:4]))
    return _unique(variants)[:MAX_QUERIES]


def _score_result(result: SearchResult, query_terms: list[str], all_terms: list[str]) -> float:
    hay = _normalize(f"{result.title} {result.snippet} {result.url}")
    tokens = set(_tokens(hay))
    if not tokens:
        return 0.0

    q_overlap = len(set(query_terms) & tokens) / max(1, len(set(query_terms)))
    global_overlap = len(set(all_terms) & tokens) / max(1, len(set(all_terms)))

    # Domain/product signals help but never make the result mandatory.
    bonus = 0.0
    if any(x in hay for x in ("product", "محصول", "بطری", "shop", "store", "فروشگاه", "digikala", "basalam")):
        bonus += 0.03
    if any(x in result.url.lower() for x in ("instagram.com", "digikala.com", "basalam.com")):
        bonus += 0.04

    score = 0.62 * q_overlap + 0.35 * global_overlap + bonus
    return max(0.0, min(1.0, score))


def _dedupe_and_rank(results: list[SearchResult], description: str, ocr: str, caption: str) -> list[SearchResult]:
    terms = _tokens(" ".join(x for x in (description, ocr, caption) if x))
    best_by_url: dict[str, SearchResult] = {}
    for r in results:
        key = _strip_ddg_url(r.url).split("#", 1)[0].rstrip("/").lower()
        if not key:
            continue
        q_terms = _tokens(r.matched_query)
        r.score = _score_result(r, q_terms, terms)
        old = best_by_url.get(key)
        if old is None or r.score > old.score:
            best_by_url[key] = r
    ranked = sorted(best_by_url.values(), key=lambda x: x.score, reverse=True)
    return ranked[:15]


def looks_like_visual_search(text: str) -> bool:
    """Return True for explicit Lens / image-search requests."""
    t = _normalize(text)
    patterns = (
        "گوگل لنز", "لنز", "جستجوی عکس", "جستجوی تصویری", "سرچ عکس", "سرچ تصویری",
        "این عکس چیه", "این تصویر چیه", "پیدا کن عکس", "پیدا کن تصویر",
        "محصول مشابه", "محصول شبیه", "مشابه این عکس", "what is this", "search image",
        "visual search", "find similar", "find this product", "shop by image",
    )
    return any(p in t for p in patterns)


async def visual_search(
    image_bytes: bytes,
    caption: str = "",
    *,
    include_web: bool = True,
) -> str:
    """Analyze an image locally and return Lens-like ranked similar results."""
    if not image_bytes:
        return "❌ تصویر دریافت نشد."

    info = _image_info(image_bytes)
    ocr = await asyncio.to_thread(_ocr, image_bytes)
    vision = await asyncio.to_thread(_vision_caption, image_bytes)
    description = " ".join(x for x in (vision, caption) if x).strip()
    keywords = _extract_keywords(" ".join(x for x in (vision, ocr, caption) if x))

    results: list[SearchResult] = []
    queries = _query_variants(description, ocr, caption)
    if include_web and queries:
        batches = await asyncio.gather(*(_ddg_search(q) for q in queries), return_exceptions=True)
        for batch in batches:
            if isinstance(batch, list):
                results.extend(batch)
    ranked = _dedupe_and_rank(results, description, ocr, caption)

    lines = ["🔎 تحلیل تصویری / Visual Lens", ""]
    if info:
        lines.append(f"📐 تصویر: {info.get('width')}×{info.get('height')} | {info.get('format', '')}")
    if vision:
        lines.append(f"👁️ تشخیص مدل: {vision[:500]}")
    if ocr:
        lines.append(f"📝 متن داخل تصویر: {ocr[:700]}")
    if keywords:
        lines.append("🔑 کلیدواژه‌ها: " + "، ".join(keywords[:12]))

    if queries:
        lines.append("\n🔍 جستجوهای ساخته‌شده:")
        lines.extend(f"• {q}" for q in queries[:MAX_QUERIES])

    lines.append("")
    if ranked:
        lines.append("🛍️ نزدیک‌ترین نتایج پیدا شده (نیازی به تطابق ۱۰۰٪ نیست):")
        for i, r in enumerate(ranked[:8], 1):
            pct = round(r.score * 100)
            lines.append(f"\n{i}. ⭐ {pct}% — {r.title[:180]}\n{r.url}")
            if r.snippet:
                lines.append(f"   {r.snippet[:260]}")
    else:
        lines.append("ℹ️ نتیجه دقیق پیدا نشد؛ جستجوی وب نتیجه قابل اتکایی برنگرداند.")
        lines.append("💡 اگر عکس واضح‌تر یا نمای نزدیک‌تر بفرستید، شانس پیدا کردن مشابه بیشتر می‌شود.")

    lines.append("\n⚠️ درصدها «شباهت تقریبی متنی/جستجویی» هستند، نه تضمین تطابق محصول.")
    return "\n".join(lines)[:12000]


__all__ = ["visual_search", "looks_like_visual_search"]
