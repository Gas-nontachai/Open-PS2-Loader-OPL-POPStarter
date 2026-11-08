"""Set APP_VERSION in the build workspace from a stable release tag."""
from __future__ import annotations

import os
from pathlib import Path
import re

CONSTANTS = "app/core/constants.py"


def stamp_release(tag: str) -> str:
    match = re.fullmatch(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", tag)
    if not match or any(int(part) > 65535 for part in match.groups()):
        raise ValueError("Use a stable vMAJOR.MINOR.PATCH tag with Windows version components <= 65535")
    path = Path(CONSTANTS)
    original = path.read_text(encoding="utf-8")
    version = tag[1:]
    updated, count = re.subn(r'^APP_VERSION = "[^"]+"$', f'APP_VERSION = "{version}"', original, flags=re.MULTILINE)
    if count != 1:
        raise ValueError("Expected one APP_VERSION assignment")
    if updated != original:
        path.write_text(updated, encoding="utf-8")
    return version


if __name__ == "__main__":
    print(f"Build version: {stamp_release(os.environ['RELEASE_TAG'])}")
