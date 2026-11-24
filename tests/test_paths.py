from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.core import paths


class AppResourcePathTests(unittest.TestCase):
    def test_resolves_resources_from_pyinstaller_bundle(self) -> None:
        bundle_root = Path("bundle-root")
        with patch.object(paths.sys, "_MEIPASS", str(bundle_root), create=True):
            self.assertEqual(
                paths.app_resource_path("assets/app_icon.png"),
                bundle_root / "assets" / "app_icon.png",
            )

    def test_resolves_resources_from_project_root(self) -> None:
        expected = Path(paths.__file__).resolve().parents[2] / "assets" / "app_icon.png"
        with patch.object(paths, "sys", SimpleNamespace()):
            self.assertEqual(paths.app_resource_path("assets/app_icon.png"), expected)
