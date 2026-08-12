from __future__ import annotations

import unittest
from subprocess import CompletedProcess
from unittest.mock import patch

from app.core.exceptions import UnsafeDriveError
from app.services import drive_service
from app.services import format_service
from app.services.format_service import sanitize_volume_label


def record(**overrides):
    data = {
        "Letter": "E:",
        "Label": "PS2USB",
        "FileSystem": "FAT32",
        "Total": 64 * 1024**3,
        "Free": 40 * 1024**3,
        "DriveType": "Removable",
        "DiskNumber": 2,
        "Model": "SanDisk Ultra USB",
        "BusType": "USB",
        "UniqueId": "usb-disk-2",
        "SerialNumber": "serial-2",
        "PartitionGuid": "partition-2",
        "DiskIsBoot": False,
        "DiskIsSystem": False,
        "PartitionIsBoot": False,
        "PartitionIsSystem": False,
        "PartitionType": "Basic",
        "HasPageFile": False,
        "IsReadOnly": False,
        "IsOffline": False,
    }
    data.update(overrides)
    return data


class StorageSafetyTests(unittest.TestCase):
    def test_usb_flash_drive_allowed(self) -> None:
        device = drive_service.classify_windows_records([record()])[0]
        self.assertTrue(device.is_safe_target)
        self.assertEqual(device.storage_type, "USB Flash Drive")

    def test_external_usb_fixed_disk_allowed(self) -> None:
        device = drive_service.classify_windows_records([record(DriveType="Fixed", Model="Seagate Expansion")])[0]
        self.assertTrue(device.is_safe_target)
        self.assertEqual(device.storage_type, "External USB HDD / SSD")

    def test_internal_nvme_and_sata_rejected(self) -> None:
        devices = drive_service.classify_windows_records([record(BusType="NVMe"), record(Letter="F:", BusType="SATA")])
        self.assertTrue(all(not device.is_safe_target for device in devices))

    def test_system_boot_pagefile_and_recovery_rejected(self) -> None:
        records = [
            record(Letter="C:"),
            record(DiskIsBoot=True),
            record(HasPageFile=True),
            record(PartitionType="Recovery"),
        ]
        self.assertTrue(all(not device.is_safe_target for device in drive_service.classify_windows_records(records)))

    def test_unknown_bus_rejected(self) -> None:
        self.assertFalse(drive_service.classify_windows_records([record(BusType="Unknown")])[0].is_safe_target)

    def test_disconnected_device_rejected(self) -> None:
        with patch.object(drive_service, "list_all_windows_storage", return_value=[]), patch.object(drive_service.os, "name", "nt"):
            with self.assertRaises(UnsafeDriveError):
                drive_service.validate_external_storage("E:\\")

    def test_changed_device_rejected(self) -> None:
        old = drive_service.classify_windows_records([record(UniqueId="old")])[0]
        new = drive_service.classify_windows_records([record(UniqueId="new")])[0]
        with patch.object(drive_service, "list_all_windows_storage", return_value=[new]), patch.object(drive_service.os, "name", "nt"):
            with self.assertRaises(UnsafeDriveError):
                drive_service.validate_external_storage("E:\\", old.device_id)

    def test_volume_label_is_sanitized(self) -> None:
        self.assertEqual(sanitize_volume_label('BAD" & DEL'), "BADDEL")

    def test_windows_format_requests_administrator_and_cleans_scripts(self) -> None:
        calls = []

        def successful_run(args, **_kwargs):
            calls.append(args)
            return CompletedProcess(args, 0, "", "")

        with patch.object(format_service, "run_cmd", side_effect=successful_run):
            self.assertEqual(format_service.format_windows(7, "PS2USB"), "formatted with diskpart")
        command = " ".join(calls[0])
        self.assertIn("-Verb RunAs", command)
        helper = format_service._windows_format_helper(7, "test.txt")
        self.assertIn("BusType -ne 'USB'", helper)
        self.assertIn("$disk.IsBoot", helper)
        self.assertIn("$disk.IsSystem", helper)

    def test_windows_format_reports_uac_or_diskpart_failure(self) -> None:
        failed = CompletedProcess(["powershell"], 1, "", "cancelled")
        with patch.object(format_service, "run_cmd", return_value=failed):
            with self.assertRaisesRegex(RuntimeError, "Administrator prompt"):
                format_service.format_windows(7, "PS2USB")
