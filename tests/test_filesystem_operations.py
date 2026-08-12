from __future__ import annotations

import tempfile
import unittest
import shutil
from types import SimpleNamespace
from pathlib import Path
from threading import Event
from unittest.mock import patch

from app.controllers import game_controller, import_controller
from app.core.constants import REQUIRED_FOLDERS
from app.services import target_service


class FilesystemOperationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.safety = patch("app.services.drive_service.validate_external_storage")
        self.safety.start()

    def tearDown(self) -> None:
        self.safety.stop()

    def test_prepare_folders_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, created_first = target_service.ensure_required_folders(root)
            _, created_second = target_service.ensure_required_folders(root)
            self.assertEqual(set(created_first), set(REQUIRED_FOLDERS))
            self.assertEqual(created_second, [])

    def test_scan_empty_and_populated_drive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target_service.ensure_required_folders(root)
            first = game_controller.scan_games(str(root))
            self.assertEqual(first["details"]["count"], 0)
            iso = root / "DVD" / "SLUS_209.46.God of War.iso"
            iso.write_bytes(b"fixture")
            second = game_controller.scan_games(str(root))
            self.assertEqual(second["details"]["games"][0]["game_id"], "SLUS_209.46")

    def test_invalid_iso_without_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir) / "unknown.iso"
            source.write_bytes(b"not an iso")
            result = import_controller.import_isos(target_dir, [str(source)], False)
            self.assertEqual(result["status"], "error")
            self.assertIn("game ID", result["message"])

    def test_import_uses_atomic_part_file_and_duplicate_skips(self) -> None:
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir) / "SLUS_209.46.God of War.iso"
            source.write_bytes(b"safe fixture")
            with patch("app.services.game_service.extract_game_id_from_iso", return_value=None):
                first = import_controller.import_isos(target_dir, [str(source)], False)
                second = import_controller.import_isos(target_dir, [str(source)], False)
            self.assertEqual(first["status"], "success")
            self.assertEqual(second["status"], "success")
            self.assertFalse(any(Path(target_dir).rglob("*.part")))
            self.assertEqual(len(list((Path(target_dir) / "CD").glob("*.iso"))), 1)

    def test_multiple_iso_import(self) -> None:
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            sources = []
            for name in ("SLUS_209.46.Game One.iso", "SLES_123.45.Game Two.iso"):
                source = Path(source_dir) / name
                source.write_bytes(b"fixture")
                sources.append(str(source))
            with patch("app.services.game_service.extract_game_id_from_iso", return_value=None):
                result = import_controller.import_isos(target_dir, sources, False)
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["details"]["imported_count"], 2)

    def test_large_fat32_iso_is_split_listed_and_deletable(self) -> None:
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir) / "SCUS_973.99.God of War Asia.iso"
            source.write_bytes(b"0123456789abcdefghijkl")
            with patch(
                "app.services.drive_service.validate_external_storage",
                return_value=SimpleNamespace(filesystem="FAT32"),
            ), patch("app.services.game_service.extract_game_id_from_iso", return_value=None), patch(
                "app.controllers.import_controller.usbextreme_service.UL_PART_SIZE", 8
            ), patch(
                "app.controllers.import_controller.usbextreme_service.FAT32_MAX_FILE_BYTES", 8
            ):
                result = import_controller.import_isos(target_dir, [str(source)], False)

            self.assertEqual(result["status"], "success")
            self.assertEqual(len(list(Path(target_dir).glob("ul.*.SCUS_973.99.*"))), 3)
            self.assertEqual((Path(target_dir) / "ul.cfg").stat().st_size, 64)

            scanned = game_controller.scan_games(target_dir)
            self.assertEqual(scanned["details"]["games"][0]["target_folder"], "USBExtreme")
            deleted = game_controller.delete_game(
                target_dir,
                "SCUS_973.99",
                scanned["details"]["games"][0]["destination_filename"],
            )
            self.assertEqual(deleted["status"], "success")
            self.assertFalse(list(Path(target_dir).glob("ul.*.SCUS_973.99.*")))

    def test_cancelled_copy_removes_partial_file(self) -> None:
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir) / "SLUS_209.46.Cancel.iso"
            source.write_bytes(b"x" * 1024)
            cancelled = Event()
            cancelled.set()
            with patch("app.services.game_service.extract_game_id_from_iso", return_value=None):
                result = import_controller.import_isos(target_dir, [str(source)], False, cancel_event=cancelled)
            self.assertEqual(result["status"], "cancelled")
            self.assertFalse(any(Path(target_dir).rglob("*.part")))

    def test_not_enough_space_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir) / "SLUS_209.46.Space.iso"
            source.write_bytes(b"fixture")
            no_space = shutil._ntuple_diskusage(total=100, used=100, free=0)
            with patch("app.services.game_service.extract_game_id_from_iso", return_value=None), patch(
                "app.controllers.import_controller.shutil.disk_usage", return_value=no_space
            ):
                result = import_controller.import_isos(target_dir, [str(source)], False)
            self.assertEqual(result["status"], "error")
            self.assertIn("space", result["message"])

    def test_disconnected_drive_error_cleans_partial_file(self) -> None:
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir) / "SLUS_209.46.Disconnect.iso"
            source.write_bytes(b"fixture")

            def fail_copy(_src, dst, **_kwargs):
                dst.write_bytes(b"partial")
                raise OSError("drive disconnected")

            with patch("app.services.game_service.extract_game_id_from_iso", return_value=None), patch(
                "app.controllers.import_controller._copy_with_progress", side_effect=fail_copy
            ):
                result = import_controller.import_isos(target_dir, [str(source)], False)
            self.assertEqual(result["status"], "error")
            self.assertFalse(any(Path(target_dir).rglob("*.part")))

    def test_delete_cannot_remove_mismatched_filename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target_service.ensure_required_folders(root)
            other = root / "DVD" / "SLUS_000.01.Other.iso"
            other.write_bytes(b"keep")
            result = game_controller.delete_game(str(root), "SLUS_209.46", other.name)
            self.assertEqual(result["status"], "error")
            self.assertTrue(other.exists())


if __name__ == "__main__":
    unittest.main()
