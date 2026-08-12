from __future__ import annotations

from io import BytesIO
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from app.core.constants import ART_EXT_HINT
from app.core.paths import artwork_cache_dir
from app.services.artwork_providers import ArtworkCandidate, fetch_url

logger = logging.getLogger("ps2_toolkit.artwork")

ARTWORK_SPECS = {
    "COV": {"label": "Front Cover", "multiple": False},
    "LAB": {"label": "Spine", "multiple": False},
    "COV2": {"label": "Back Cover", "multiple": False},
    "SCR": {"label": "Screenshots", "multiple": True},
    "BG": {"label": "Background", "multiple": False},
    "ICO": {"label": "Disc", "multiple": False},
    "LGO": {"label": "Logo", "multiple": False},
}

ART_TARGET_SIZE = {
    "COV": (256, 364),
    "COV2": (256, 364),
    "BG": (512, 288),
    "SCR": (320, 180),
    "LGO": (256, 128),
    "ICO": (128, 128),
    "LAB": (256, 64),
}

ART_TARGET_BYTES = {
    "COV": 120 * 1024,
    "COV2": 120 * 1024,
    "BG": 180 * 1024,
    "SCR": 110 * 1024,
    "LGO": 90 * 1024,
    "ICO": 60 * 1024,
    "LAB": 50 * 1024,
}


def _flatten_alpha(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"}:
        base = Image.new("RGB", image.size, (0, 0, 0))
        base.paste(image, mask=image.split()[-1])
        return base
    return image.convert("RGB") if image.mode != "RGB" else image


def optimize_art_image(content: bytes, art_type: str, source_ext: str | None = None) -> tuple[bytes, str, dict[str, Any]]:
    normalized_type = art_type.strip().upper()
    if normalized_type not in ART_EXT_HINT:
        raise ValueError(f"invalid art type: {normalized_type}")
    if len(content) > 20 * 1024 * 1024:
        raise ValueError("image is larger than 20 MB")
    try:
        with Image.open(BytesIO(content)) as raw_image:
            raw_image.verify()
        with Image.open(BytesIO(content)) as raw_image:
            image = raw_image.copy()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("The selected file is not a valid image.") from exc

    target_width, target_height = ART_TARGET_SIZE[normalized_type]
    target_bytes = ART_TARGET_BYTES[normalized_type]
    image.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
    keep_png = normalized_type in {"LGO", "ICO"}
    if keep_png:
        output = BytesIO()
        if image.mode not in {"RGBA", "LA"}:
            image = image.convert("RGBA")
        image.quantize(colors=128).save(output, format="PNG", optimize=True, compress_level=9)
        optimized, output_ext = output.getvalue(), ".png"
    else:
        rgb_image = _flatten_alpha(image)
        optimized = b""
        for quality in (84, 78, 72, 66, 60, 54):
            output = BytesIO()
            rgb_image.save(output, format="JPEG", quality=quality, optimize=True, progressive=False)
            optimized = output.getvalue()
            if len(optimized) <= target_bytes:
                break
        output_ext = ".jpg"
    return optimized, output_ext, {
        "art_type": normalized_type,
        "source_ext": (source_ext or "").lower(),
        "output_ext": output_ext,
        "original_bytes": len(content),
        "optimized_bytes": len(optimized),
        "width": image.width,
        "height": image.height,
    }


def metadata_path(target: Path) -> Path:
    return target / "ART" / ".ps2-toolkit-artwork.json"


def load_metadata(target: Path) -> dict[str, dict[str, str]]:
    try:
        payload = json.loads(metadata_path(target).read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_metadata(target: Path, metadata: dict[str, dict[str, str]]) -> None:
    destination = metadata_path(target)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(destination)


def artwork_files(target: Path, game_id: str, art_type: str | None = None) -> list[Path]:
    art_dir = target / "ART"
    if not art_dir.is_dir():
        return []
    prefix = f"{game_id}_"
    result: list[Path] = []
    for candidate in art_dir.iterdir():
        if not candidate.is_file() or candidate.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        stem = candidate.stem.upper()
        if not stem.startswith(prefix):
            continue
        suffix = stem[len(prefix):]
        base_type = suffix.split("_", 1)[0]
        if art_type is None or base_type == art_type.upper():
            result.append(candidate)
    return sorted(result, key=lambda item: item.name)


def next_suffix(target: Path, game_id: str, art_type: str) -> str:
    if art_type != "SCR":
        return art_type
    used: set[int] = set()
    for path in artwork_files(target, game_id, "SCR"):
        match = __import__("re").search(r"_SCR(?:_)?(\d+)", path.stem.upper())
        if match:
            used.add(int(match.group(1)))
    index = next((number for number in range(100) if number not in used), len(used))
    return f"SCR_{index:02d}"


def write_artwork(
    target: Path,
    game_id: str,
    art_type: str,
    content: bytes,
    source_ext: str,
    *,
    provenance: str,
    suffix: str | None = None,
    replace: bool = False,
) -> dict[str, Any]:
    normalized_type = art_type.upper()
    actual_suffix = suffix or next_suffix(target, game_id, normalized_type)
    metadata = load_metadata(target)
    if replace:
        for existing in artwork_files(target, game_id, normalized_type):
            existing.unlink()
            metadata.pop(existing.name, None)
    optimized, extension, info = optimize_art_image(content, normalized_type, source_ext)
    destination = target / "ART" / f"{game_id}_{actual_suffix}{extension}"
    temporary = destination.with_name(destination.name + ".part")
    temporary.write_bytes(optimized)
    temporary.replace(destination)
    metadata[destination.name] = {"provenance": provenance, "art_type": normalized_type}
    save_metadata(target, metadata)
    logger.info("Artwork saved game_id=%s type=%s provider=%s destination=%s conversion=%s", game_id, normalized_type, provenance, destination, info)
    return {"art_type": normalized_type, "path": str(destination), "optimize": info, "provenance": provenance}


def cached_candidate(candidate: ArtworkCandidate, *, invalidate: bool = False) -> tuple[bytes, str, bool]:
    root = artwork_cache_dir()
    root.mkdir(parents=True, exist_ok=True)
    key = f"{candidate.game_id}|{candidate.art_type}|{candidate.provider}|{candidate.index}|{candidate.url}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    extension = Path(candidate.source_name).suffix.lower() or ".img"
    destination = root / f"{digest}{extension}"
    if destination.is_file() and not invalidate:
        return destination.read_bytes(), extension, True
    content = fetch_url(candidate.url)
    if len(content) > 25 * 1024 * 1024:
        raise ValueError("Artwork image is too large.")
    # Validate before caching so an HTML error page never becomes a preview.
    optimize_art_image(content, candidate.art_type, extension)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(content)
    temporary.replace(destination)
    return content, extension, False


def invalidate_cache() -> int:
    root = artwork_cache_dir()
    if not root.is_dir():
        return 0
    removed = 0
    for path in root.iterdir():
        if path.is_file():
            path.unlink()
            removed += 1
    return removed


def preview_thumbnail(source: Path, max_size: tuple[int, int] = (320, 220)) -> str:
    """Create a small local preview so very large artwork never bloats the UI."""
    try:
        stat = source.stat()
        key = f"preview|{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{max_size}"
        root = artwork_cache_dir() / "previews"
        root.mkdir(parents=True, exist_ok=True)
        destination = root / f"{hashlib.sha256(key.encode('utf-8')).hexdigest()}.jpg"
        if destination.is_file():
            return str(destination)
        with Image.open(source) as raw:
            image = _flatten_alpha(raw.copy())
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        temporary = destination.with_suffix(".part")
        image.save(temporary, format="JPEG", quality=78, optimize=True, progressive=False)
        temporary.replace(destination)
        return str(destination)
    except (OSError, UnidentifiedImageError):
        logger.exception("Artwork preview failed source=%s", source)
        return str(source)
