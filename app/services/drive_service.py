from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.core.exceptions import UnsafeDriveError
from app.models.drive import Drive

_KNOWN_DEVICES: dict[str, str] = {}

_STORAGE_QUERY = r"""
$ErrorActionPreference = 'Stop'
$pageFileDrives = @(Get-CimInstance Win32_PageFileUsage -ErrorAction SilentlyContinue | ForEach-Object { $_.Name.Substring(0,2).ToUpper() })
$items = @()
Get-Volume | Where-Object { $_.DriveLetter } | ForEach-Object {
  $volume = $_
  try {
    $partition = Get-Partition -DriveLetter $volume.DriveLetter -ErrorAction Stop
    $disk = Get-Disk -Number $partition.DiskNumber -ErrorAction Stop
    $items += [PSCustomObject]@{
      Letter = ($volume.DriveLetter + ':').ToUpper()
      Label = [string]$volume.FileSystemLabel
      FileSystem = [string]$volume.FileSystem
      Total = [int64]$volume.Size
      Free = [int64]$volume.SizeRemaining
      DriveType = [string]$volume.DriveType
      HealthStatus = [string]$volume.HealthStatus
      DiskNumber = [int]$disk.Number
      Model = [string]$disk.FriendlyName
      BusType = [string]$disk.BusType
      UniqueId = [string]$disk.UniqueId
      SerialNumber = [string]$disk.SerialNumber
      DiskIsBoot = [bool]$disk.IsBoot
      DiskIsSystem = [bool]$disk.IsSystem
      PartitionIsBoot = [bool]$partition.IsBoot
      PartitionIsSystem = [bool]$partition.IsSystem
      PartitionType = [string]$partition.Type
      PartitionGuid = [string]$partition.Guid
      IsReadOnly = [bool]$disk.IsReadOnly
      IsOffline = [bool]$disk.IsOffline
      HasPageFile = [bool]($pageFileDrives -contains (($volume.DriveLetter + ':').ToUpper()))
    }
  } catch { }
}
@($items) | ConvertTo-Json -Compress -Depth 4
"""


def _run_storage_query() -> list[dict[str, Any]]:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _STORAGE_QUERY],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0:
        return []
    try:
        payload = json.loads(completed.stdout or "[]")
    except (TypeError, ValueError):
        return []
    if isinstance(payload, dict):
        return [payload]
    return payload if isinstance(payload, list) else []


def _device_fingerprint(record: dict[str, Any]) -> str:
    identity = "|".join(
        str(record.get(key, ""))
        for key in ("DiskNumber", "UniqueId", "SerialNumber", "PartitionGuid", "Total", "Letter")
    )
    return hashlib.sha256(identity.encode("utf-8", errors="ignore")).hexdigest()


def _record_to_drive(record: dict[str, Any], system_drive: str, app_drive: str) -> Drive:
    letter = str(record.get("Letter", "")).upper()
    bus_type = str(record.get("BusType", "")).upper()
    partition_type = str(record.get("PartitionType", "")).upper()
    reasons: list[str] = []
    if bus_type != "USB":
        reasons.append("physical disk is not connected through USB")
    if letter in {system_drive.upper(), app_drive.upper()}:
        reasons.append("system/application drive")
    if any(bool(record.get(key)) for key in ("DiskIsBoot", "DiskIsSystem", "PartitionIsBoot", "PartitionIsSystem", "HasPageFile")):
        reasons.append("boot, system, or pagefile disk")
    if "RECOVERY" in partition_type or "HIDDEN" in partition_type:
        reasons.append("recovery or hidden partition")
    if bool(record.get("IsReadOnly")) or bool(record.get("IsOffline")):
        reasons.append("disk is read-only or offline")
    total = int(record.get("Total") or 0)
    free = int(record.get("Free") or 0)
    if not letter or total <= 0:
        reasons.append("volume information is incomplete")
    model = str(record.get("Model") or "External USB storage").strip()
    storage_type = "USB Flash Drive" if str(record.get("DriveType", "")).lower() == "removable" else "External USB HDD / SSD"
    return Drive(
        path=f"{letter}\\" if letter else "",
        letter=letter,
        label=str(record.get("Label") or model or "External storage"),
        filesystem=str(record.get("FileSystem") or "Unknown"),
        total_bytes=total,
        used_bytes=max(0, total - free),
        free_bytes=free,
        kind="external" if not reasons else "unsupported",
        is_safe_target=not reasons,
        model=model,
        connection_type=bus_type or "Unknown",
        storage_type=storage_type,
        disk_number=int(record["DiskNumber"]) if record.get("DiskNumber") is not None else None,
        device_id=_device_fingerprint(record),
        rejection_reason="; ".join(reasons),
    )


def classify_windows_records(
    records: list[dict[str, Any]], system_drive: str = "C:", app_drive: str = "C:"
) -> list[Drive]:
    return [_record_to_drive(record, system_drive, app_drive) for record in records]


def list_all_windows_storage() -> list[Drive]:
    if os.name != "nt":
        return []
    system_drive = os.getenv("SystemDrive", "C:")
    app_drive = Path(sys.executable).drive or system_drive
    return classify_windows_records(_run_storage_query(), system_drive, app_drive)


def list_external_storage_devices() -> list[Drive]:
    devices = [device for device in list_all_windows_storage() if device.is_safe_target]
    _KNOWN_DEVICES.clear()
    _KNOWN_DEVICES.update({device.path.upper(): device.device_id for device in devices})
    return devices


def list_drives(include_internal: bool = False) -> list[Drive]:
    """Compatibility alias. Internal/unknown storage is intentionally never returned."""
    return list_external_storage_devices()


def validate_external_storage(path: str | Path, expected_device_id: str | None = None) -> Drive:
    if os.name != "nt":
        raise UnsafeDriveError("External storage validation is only supported on Windows.")
    candidate = Path(path)
    letter = candidate.drive.upper()
    if not letter:
        raise UnsafeDriveError("Select an external USB storage device.")
    matches = [device for device in list_all_windows_storage() if device.letter.upper() == letter]
    if not matches:
        raise UnsafeDriveError("The selected storage device was disconnected.")
    device = matches[0]
    if not device.is_safe_target:
        raise UnsafeDriveError("This destination is not verified external USB storage.")
    known_id = expected_device_id or _KNOWN_DEVICES.get(device.path.upper())
    if known_id and known_id != device.device_id:
        raise UnsafeDriveError("The selected storage device changed. Refresh devices and select it again.")
    return device


def get_drive(path: str) -> Drive | None:
    try:
        return validate_external_storage(path)
    except UnsafeDriveError:
        return None
