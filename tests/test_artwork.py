from __future__ import annotations

import tempfile
import json
import threading
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.controllers import art_controller, game_controller
from app.services import art_service, target_service
from app.services.artwork_providers import ArtworkCandidate, ArtworkNetworkError, GameIdNormalizer, OplArtworkProvider, Ps2CoversProvider


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

    def test_game_id_normalization_for_both_sources(self) -> None:
        self.assertEqual(GameIdNormalizer.opl(" sces_533.58 "), "SCES_533.58")
        self.assertEqual(GameIdNormalizer.hyphen("SCES_533.58"), "SCES-53358")

    def test_primary_provider_parses_real_repository_naming(self) -> None:
        payload = [
            {"name": "SCES_533.58_COV.png", "download_url": "https://example/cov.png"},
            {"name": "SCES_533.58_SCR_02.png", "download_url": "https://example/scr.png"},
            {"name": "README.md", "download_url": "https://example/readme"},
        ]
        provider = OplArtworkProvider(fetch=lambda _: json.dumps(payload).encode())
        found = provider.find("SCES_533.58")
        self.assertEqual([(item.art_type, item.suffix) for item in found], [("COV", "COV"), ("SCR", "SCR_02")])

    def test_secondary_provider_uses_hyphen_serial(self) -> None:
        provider = Ps2CoversProvider()
        found = provider.find("SLUS_209.46")
        self.assertEqual(found[0].art_type, "COV")
        self.assertTrue(found[0].url.endswith("/SLUS-20946.jpg"))

    def test_manual_upload_supports_all_types_and_multiple_screenshots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target_service.ensure_required_folders(root)
            picture = root / "picture.png"
            image_file(picture, "PNG")
            iso_name = "SLUS_209.46.Game.iso"
            (root / "DVD" / iso_name).write_bytes(b"fixture")
            for art_type in art_service.ARTWORK_SPECS:
                result = art_controller.upload_art_manual(str(root), "Game", iso_name, {art_type: str(picture)})
                self.assertEqual(result["status"], "success", art_type)
            art_controller.upload_art_manual(str(root), "Game", iso_name, {"SCR": str(picture)})
            status = art_controller.get_artwork_status(str(root), "SLUS_209.46")
            self.assertEqual(set(status["details"]["types"]), set(art_service.ARTWORK_SPECS))
            self.assertEqual(len(status["details"]["types"]["SCR"]["files"]), 2)
            self.assertEqual(status["details"]["types"]["COV"]["status"], "Custom")

    def test_download_missing_skips_custom_and_uses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target_service.ensure_required_folders(root)
            picture = root / "picture.png"
            image_file(picture, "PNG")
            art_controller.upload_art_manual(str(root), "Game", "SLUS_209.46.Game.iso", {"COV": str(picture)})
            candidate = ArtworkCandidate("SLUS_209.46", "COV", "Fake", "https://example/cov.png", "cover.png", suffix="COV")

            class Provider:
                def find(self, _game_id: str) -> list[ArtworkCandidate]:
                    return [candidate]

            with patch("app.services.art_service.cached_candidate") as download:
                result = art_controller.download_artwork(str(root), "SLUS_209.46", providers=[Provider()])
            self.assertEqual(result["status"], "success")
            download.assert_not_called()
            self.assertEqual(art_controller.get_artwork_status(str(root), "SLUS_209.46")["details"]["types"]["COV"]["status"], "Custom")

    def test_cached_candidate_only_downloads_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidate = ArtworkCandidate("SLUS_209.46", "COV", "Fake", "https://example/cov.png", "cover.png", suffix="COV")
            output = BytesIO()
            Image.new("RGB", (64, 64), "red").save(output, "PNG")
            with patch("app.services.art_service.artwork_cache_dir", return_value=Path(directory)), patch(
                "app.services.art_service.fetch_url", return_value=output.getvalue()
            ) as fetch:
                art_service.cached_candidate(candidate)
                art_service.cached_candidate(candidate)
            self.assertEqual(fetch.call_count, 1)

    def test_network_failure_is_user_friendly_and_batch_can_cancel(self) -> None:
        class OfflineProvider:
            def find(self, _game_id: str) -> list:
                raise ArtworkNetworkError("Artwork source unavailable.")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target_service.ensure_required_folders(root)
            failed = art_controller.download_artwork(str(root), "SLUS_209.46", providers=[OfflineProvider()])
            self.assertEqual(failed["status"], "error")
            self.assertNotIn("Traceback", failed["message"])
            cancelled = threading.Event()
            cancelled.set()
            batch = art_controller.download_artwork_batch(
                str(root), [{"game_id": "SLUS_209.46"}], cancel_event=cancelled, providers=[OfflineProvider()]
            )
            self.assertEqual(batch["status"], "cancelled")

    def test_large_artwork_uses_small_cached_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "large.jpg"
            Image.new("RGB", (4000, 3000), "purple").save(source, "JPEG", quality=95)
            with patch("app.services.art_service.artwork_cache_dir", return_value=root / "cache"):
                preview = Path(art_service.preview_thumbnail(source))
            self.assertTrue(preview.is_file())
            with Image.open(preview) as image:
                self.assertLessEqual(image.width, 320)
                self.assertLessEqual(image.height, 220)
            self.assertLess(preview.stat().st_size, source.stat().st_size)

    def test_remove_one_screenshot_keeps_the_other(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target_service.ensure_required_folders(root)
            picture = root / "picture.png"
            image_file(picture, "PNG")
            iso_name = "SLUS_209.46.Game.iso"
            for _ in range(2):
                art_controller.upload_art_manual(str(root), "Game", iso_name, {"SCR": str(picture)})
            before = art_controller.get_artwork_status(str(root), "SLUS_209.46")["details"]["types"]["SCR"]["files"]
            removed = art_controller.remove_artwork(str(root), "SLUS_209.46", "SCR", filename=before[0]["name"])
            after = art_controller.get_artwork_status(str(root), "SLUS_209.46")["details"]["types"]["SCR"]["files"]
            self.assertEqual(removed["status"], "success")
            self.assertEqual(len(after), 1)
