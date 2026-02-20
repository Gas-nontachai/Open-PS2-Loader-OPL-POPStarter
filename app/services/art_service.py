from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Any, Optional
from PIL import Image

from app.core.constants import (
    ART_ALLOWED_EXT,
    ART_EXT_HINT,
    ART_SEARCH_CACHE_MAX_SIZE,
    ART_SEARCH_CACHE_TTL_SEC,
    ART_SEARCH_MIN_INTERVAL_SEC,
    ART_SEARCH_RATE_LIMIT_PER_MIN,
    RAWG_SEARCH_ENDPOINT,
)

_ART_SEARCH_CACHE: dict[str, dict[str, Any]] = {}
_ART_SEARCH_CLIENT_LIMITS: dict[str, dict[str, Any]] = {}
_ART_SEARCH_LOCK = threading.Lock()


def rawg_api_key() -> str:
    key = os.getenv("RAWG_API_KEY", "").strip()
    if not key:
        raise RuntimeError("missing RAWG_API_KEY")
    return key


def art_search_cache_key(provider: str, game_id: str, query: str, max_results: int) -> str:
    return f"{provider}|{game_id}|{query.lower()}|{max_results}"


def get_cached_art_search(cache_key: str, now_ts: float) -> Optional[list[dict[str, Any]]]:
    with _ART_SEARCH_LOCK:
        entry = _ART_SEARCH_CACHE.get(cache_key)
        if not entry:
            return None
        if now_ts - entry["ts"] > ART_SEARCH_CACHE_TTL_SEC:
            _ART_SEARCH_CACHE.pop(cache_key, None)
            return None
        return entry["candidates"]


def store_cached_art_search(cache_key: str, candidates: list[dict[str, Any]], now_ts: float) -> None:
    with _ART_SEARCH_LOCK:
        _ART_SEARCH_CACHE[cache_key] = {"ts": now_ts, "candidates": candidates}
        if len(_ART_SEARCH_CACHE) > ART_SEARCH_CACHE_MAX_SIZE:
            oldest_key = min(_ART_SEARCH_CACHE.items(), key=lambda kv: kv[1]["ts"])[0]
            _ART_SEARCH_CACHE.pop(oldest_key, None)


def enforce_art_search_rate_limit(client_id: str, now_ts: float) -> tuple[bool, str, int]:
    with _ART_SEARCH_LOCK:
        limiter = _ART_SEARCH_CLIENT_LIMITS.get(client_id)
        if not limiter:
            limiter = {"window_start": now_ts, "count": 0, "last_ts": 0.0}
            _ART_SEARCH_CLIENT_LIMITS[client_id] = limiter

        if now_ts - float(limiter["window_start"]) >= 60:
            limiter["window_start"] = now_ts
            limiter["count"] = 0

        since_last = now_ts - float(limiter["last_ts"])
        if since_last < ART_SEARCH_MIN_INTERVAL_SEC:
            retry_after = max(1, int(ART_SEARCH_MIN_INTERVAL_SEC - since_last + 0.999))
            return False, "too many requests; please slow down", retry_after

        if int(limiter["count"]) >= ART_SEARCH_RATE_LIMIT_PER_MIN:
            elapsed = now_ts - float(limiter["window_start"])
            retry_after = max(1, int(60 - elapsed + 0.999))
            return False, "rate limit reached for art search", retry_after

        limiter["count"] = int(limiter["count"]) + 1
        limiter["last_ts"] = now_ts
        return True, "", 0


def search_rawg_images(query: str, max_results: int) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "key": rawg_api_key(),
            "search": query,
            "page_size": max_results,
        }
    )
    req = urllib.request.Request(
        f"{RAWG_SEARCH_ENDPOINT}?{params}",
        headers={"User-Agent": "PS2-ISO-Importer/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"rawg api error: {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"rawg api connection error: {exc.reason}") from exc

    results = payload.get("results", [])
    candidates: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    idx = 1
    for game in results:
        name = str(game.get("name", "")).strip() or "RAWG Game"
        for image_url in [game.get("background_image"), game.get("background_image_additional")]:
            image = str(image_url or "").strip()
            if not image.startswith(("http://", "https://")):
                continue
            if image in seen_urls:
                continue
            seen_urls.add(image)
            candidates.append(
                {
                    "candidate_id": idx,
                    "title": f"{name} (RAWG)",
                    "image_url": image,
                    "thumbnail_url": image,
                    "source_page": game.get("website") or f"https://rawg.io/games/{game.get('slug', '')}",
                }
            )
            idx += 1
            if len(candidates) >= max_results:
                return candidates
    return candidates


def search_art_candidates(query: str, max_results: int) -> tuple[str, list[dict[str, Any]]]:
    return "rawg", search_rawg_images(query, max_results)


def guess_ext(image_url: str, content_type: Optional[str], art_type: str) -> str:
    ctype = (content_type or "").lower()
    if "png" in ctype:
        return ".png"
    if "jpeg" in ctype or "jpg" in ctype:
        return ".jpg"

    parsed_path = Path(urllib.parse.urlparse(image_url).path)
    ext = parsed_path.suffix.lower()
    if ext in ART_ALLOWED_EXT:
        return ".jpg" if ext == ".jpeg" else ext
    return ART_EXT_HINT[art_type]


def download_image(image_url: str, art_type: str) -> tuple[bytes, str]:
    if not image_url.startswith(("http://", "https://")):
        raise ValueError("image_url must start with http:// or https://")

    req = urllib.request.Request(image_url, headers={"User-Agent": "PS2-ISO-Importer/1.0"})
    with urllib.request.urlopen(req, timeout=25) as response:
        content = response.read()
        content_type = response.headers.get("Content-Type")

    if not content:
        raise ValueError("downloaded image is empty")
    if len(content) > 20 * 1024 * 1024:
        raise ValueError("downloaded image is too large")

    ext = guess_ext(image_url, content_type, art_type)
    if ext not in {".jpg", ".png"}:
        raise ValueError("unsupported image extension")
    return content, ext


ART_TARGET_SIZE = {
    "COV": (256, 364),
    "COV2": (256, 364),
    "BG": (512, 288),
    "SCR": (320, 180),
    "SCR2": (320, 180),
    "LGO": (256, 128),
    "ICO": (128, 128),
    "LAB": (256, 64),
}

ART_TARGET_BYTES = {
    "COV": 120 * 1024,
    "COV2": 120 * 1024,
    "BG": 180 * 1024,
    "SCR": 110 * 1024,
    "SCR2": 110 * 1024,
    "LGO": 90 * 1024,
    "ICO": 60 * 1024,
    "LAB": 50 * 1024,
}


def _flatten_alpha(img: Image.Image) -> Image.Image:
    if img.mode in {"RGBA", "LA"}:
        base = Image.new("RGB", img.size, (0, 0, 0))
        base.paste(img, mask=img.split()[-1])
        return base
    if img.mode == "P":
        return img.convert("RGB")
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def optimize_art_image(content: bytes, art_type: str, source_ext: Optional[str] = None) -> tuple[bytes, str, dict[str, Any]]:
    normalized_type = art_type.strip().upper()
    if normalized_type not in ART_EXT_HINT:
        raise ValueError(f"invalid art type: {normalized_type}")

    target_width, target_height = ART_TARGET_SIZE[normalized_type]
    target_bytes = ART_TARGET_BYTES[normalized_type]
    keep_png = normalized_type in {"LGO", "ICO"}

    with Image.open(BytesIO(content)) as raw_img:
        img = raw_img.copy()

    img.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)

    output = BytesIO()
    if keep_png:
        if img.mode not in {"RGBA", "LA"}:
            img = img.convert("RGBA")
        # Quantize palette to reduce size while preserving transparency.
        img = img.quantize(colors=128)
        img.save(output, format="PNG", optimize=True, compress_level=9)
        out_ext = ".png"
    else:
        jpg_img = _flatten_alpha(img)
        best_bytes: Optional[bytes] = None
        best_size: Optional[int] = None
        for quality in (72, 66, 60, 54, 48):
            output = BytesIO()
            jpg_img.save(
                output,
                format="JPEG",
                quality=quality,
                optimize=True,
                progressive=True,
                subsampling="4:2:0",
            )
            candidate = output.getvalue()
            size = len(candidate)
            if best_size is None or size < best_size:
                best_size = size
                best_bytes = candidate
            if size <= target_bytes:
                break
        if not best_bytes:
            raise ValueError("failed to optimize image")
        out_ext = ".jpg"
        output = BytesIO(best_bytes)

    optimized = output.getvalue()
    details = {
        "art_type": normalized_type,
        "source_ext": (source_ext or "").lower(),
        "output_ext": out_ext,
        "original_bytes": len(content),
        "optimized_bytes": len(optimized),
        "width": img.width,
        "height": img.height,
    }
    return optimized, out_ext, details
