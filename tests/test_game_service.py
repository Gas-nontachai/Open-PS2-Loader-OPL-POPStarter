from __future__ import annotations

import unittest

from app.services import game_service, target_service, usbextreme_service


class GameServiceTests(unittest.TestCase):
    def test_extract_game_id_from_system_cnf(self) -> None:
        content = "BOOT2 = cdrom0:\\SLUS_209.46;1\nVER = 1.00"
        self.assertEqual(game_service.extract_game_id_from_system_cnf(content), "SLUS_209.46")

    def test_opl_filename(self) -> None:
        self.assertEqual(
            game_service.build_opl_iso_filename("SLUS_209.46", "original.iso", "God of War"),
            "SLUS_209.46.God of War.iso",
        )

    def test_filename_normalization_removes_unsafe_characters(self) -> None:
        name = game_service.build_opl_iso_filename("SLUS_209.46", "x.iso", "Game: A/B?")
        self.assertEqual(name, "SLUS_209.46.Game A B.iso")

    def test_invalid_game_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            game_service.normalize_game_id("C:\\Windows")

    def test_human_bytes(self) -> None:
        self.assertEqual(target_service.human_bytes(1024**3), "1.00 GB")

    def test_cd_and_dvd_routing(self) -> None:
        self.assertEqual(game_service.classify_iso_media(699 * 1024**2), "CD")
        self.assertEqual(game_service.classify_iso_media(700 * 1024**2), "DVD")

    def test_usbextreme_crc_matches_known_implementation(self) -> None:
        self.assertEqual(usbextreme_service.usba_crc32("God of War (Asia)"), 0x3C0CB1A1)
        self.assertEqual(usbextreme_service.usba_crc32("Resident Evil 4 (Asia)"), 0xBDA9070E)


if __name__ == "__main__":
    unittest.main()
