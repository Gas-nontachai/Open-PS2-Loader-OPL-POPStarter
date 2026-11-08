from __future__ import annotations

import json
import logging
import re

from app.core.constants import APP_VERSION
from app.services.artwork_providers import fetch_url

REPOSITORY = "Gas-nontachai/Open-PS2-Loader-OPL-POPStarter"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
logger = logging.getLogger("ps2_toolkit.update")


def check_for_update() -> dict[str, str] | None:
    """Return a newer stable release; unavailable checks never block app startup."""
    try:
        release = json.loads(fetch_url(LATEST_RELEASE_API, timeout=5))
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            return None
        tag = release.get("tag_name")
        if not isinstance(tag, str) or not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
            return None
        version = tag[1:]
        if tuple(map(int, version.split("."))) <= tuple(map(int, APP_VERSION.split("."))):
            return None
        # Build the URL ourselves so API response fields cannot redirect users elsewhere.
        return {"version": version, "url": f"https://github.com/{REPOSITORY}/releases/tag/{tag}"}
    except (OSError, ValueError, RuntimeError) as exc:
        logger.info("Update check unavailable: %s", exc)
        return None
