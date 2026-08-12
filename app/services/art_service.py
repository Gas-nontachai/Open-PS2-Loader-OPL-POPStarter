from __future__ import annotations

from io import BytesIO
from typing import Any

from PIL import Image, UnidentifiedImageError

from app.core.constants import ART_EXT_HINT

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
            rgb_image.save(output, format="JPEG", quality=quality, optimize=True, progressive=True)
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
