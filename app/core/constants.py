from __future__ import annotations

import os

REQUIRED_FOLDERS = ["APPS", "ART", "CD", "CFG", "CHT", "DVD", "LNG", "POPS", "THM", "VMC"]
CD_THRESHOLD_BYTES = 700 * 1024 * 1024
SPACE_BUFFER_MIN_BYTES = 500 * 1024 * 1024
SPACE_BUFFER_RATIO = 0.05
ART_TYPES = ["COV", "COV2", "BG", "SCR", "SCR2", "LGO", "ICO", "LAB"]
ART_EXT_HINT = {
    "COV": ".jpg",
    "COV2": ".jpg",
    "BG": ".jpg",
    "SCR": ".jpg",
    "SCR2": ".jpg",
    "LGO": ".png",
    "ICO": ".png",
    "LAB": ".jpg",
}
ART_ALLOWED_EXT = {".jpg", ".jpeg", ".png"}
RAWG_SEARCH_ENDPOINT = "https://api.rawg.io/api/games"
ART_SEARCH_CACHE_TTL_SEC = int(os.getenv("ART_SEARCH_CACHE_TTL_SEC", "1800"))
ART_SEARCH_CACHE_MAX_SIZE = int(os.getenv("ART_SEARCH_CACHE_MAX_SIZE", "200"))
ART_SEARCH_RATE_LIMIT_PER_MIN = int(os.getenv("ART_SEARCH_RATE_LIMIT_PER_MIN", "30"))
ART_SEARCH_MIN_INTERVAL_SEC = float(os.getenv("ART_SEARCH_MIN_INTERVAL_SEC", "1.5"))
