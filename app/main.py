from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
import flet as ft

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ui.app_layout import build_app
from app.core.logging import configure_logging


def main() -> None:
    load_dotenv()
    configure_logging()
    ft.app(target=build_app)


if __name__ == "__main__":
    main()
