from __future__ import annotations

import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.controllers import art_controller, game_controller
from app.services import art_service, target_service


def image_file(path: Path, image_format: str) -> None:
    image = Image.new("RGB", (600, 900), "blue")
    image.save(path, format=image_format)


class ArtworkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.safety = patch("app.services.drive_service.validate_external_storage")
        self.safety.start()

    def tearDown(self) -> None:
        self.safety.stop()

    def test_png_and_jpg_upload_replace_remove_and_persist_in_scan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target_service.ensure_required_folders(root)
            iso_name = "SLUS_209.46.Game.iso"
            (root / "DVD" / iso_name).write_bytes(b"fixture")
            png = root / "cover.png"
            jpg = root / "cover.jpg"
            image_file(png, "PNG")
            image_file(jpg, "JPEG")
            first = art_controller.upload_art_manual(str(root), "Game", iso_name, {"COV": str(png)})
            second = art_controller.upload_art_manual(str(root), "Game", iso_name, {"COV": str(jpg)})
            scan = game_controller.scan_games(str(root))
            self.assertEqual(first["status"], "success")
            self.assertEqual(second["status"], "success")
            self.assertTrue(scan["details"]["games"][0]["cover_path"])
            removed = art_controller.remove_artwork(str(root), "SLUS_209.46")
            self.assertEqual(removed["status"], "success")

    def test_webp_upload_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target_service.ensure_required_folders(root)
            webp = root / "cover.webp"
            image_file(webp, "WEBP")
            result = art_controller.upload_art_manual(str(root), "Game", "SLUS_209.46.Game.iso", {"COV": str(webp)})
            self.assertEqual(result["status"], "success")

    def test_invalid_artwork_rejected(self) -> None:
        with self.assertRaises(ValueError):
            art_service.optimize_art_image(b"not an image", "COV")
