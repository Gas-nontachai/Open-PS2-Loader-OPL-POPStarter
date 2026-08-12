from __future__ import annotations

APP_NAME = "PS2 TOOLKIT 2000X"
APP_SLUG = "PS2 Toolkit 2000X"
APP_VERSION = "1.0.0"

REQUIRED_FOLDERS = ["APPS", "ART", "CD", "CFG", "CHT", "DVD", "LNG", "POPS", "THM", "VMC"]
CD_THRESHOLD_BYTES = 700 * 1024 * 1024
SPACE_BUFFER_MIN_BYTES = 500 * 1024 * 1024
SPACE_BUFFER_RATIO = 0.05
ART_TYPES = ["COV", "LAB", "COV2", "SCR", "BG", "ICO", "LGO"]
ART_EXT_HINT = {
    "COV": ".jpg",
    "COV2": ".jpg",
    "BG": ".jpg",
    "SCR": ".jpg",
    "LGO": ".png",
    "ICO": ".png",
    "LAB": ".jpg",
}
ART_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
