from __future__ import annotations

import argparse
from functools import partial
import sys
from pathlib import Path

from dotenv import load_dotenv
import flet as ft

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ui.app_layout import build_app
from app.core.logging import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot-page", choices=["home", "import", "library", "storage", "settings"], help="Open a page for release screenshot capture")
    args = parser.parse_args()
    load_dotenv()
    configure_logging()
    ft.app(target=partial(build_app, screenshot_page=args.screenshot_page))


if __name__ == "__main__":
    main()
