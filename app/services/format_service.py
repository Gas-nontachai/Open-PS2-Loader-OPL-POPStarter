from __future__ import annotations

import platform
import plistlib
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Optional


def sanitize_volume_label(label: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_-]", "", label).upper()
    if not sanitized:
        sanitized = "PS2USB"
    return sanitized[:11]


def run_cmd(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=False, capture_output=True, text=True)


def diskutil_info(path_or_device: str) -> dict[str, Any]:
    result = run_cmd(["diskutil", "info", "-plist", path_or_device])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"diskutil info failed for {path_or_device}")
    return plistlib.loads(result.stdout.encode("utf-8"))


def validate_format_target(path: Path) -> tuple[str, dict[str, Any], dict[str, Any]]:
    info = diskutil_info(str(path))
    whole_disk = info.get("ParentWholeDisk") or info.get("DeviceIdentifier")
    if not whole_disk:
        raise RuntimeError("could not identify disk device from target path")

    whole_info = diskutil_info(f"/dev/{whole_disk}")
    if whole_info.get("Internal", True):
        raise RuntimeError("refusing to format an internal disk")
    if not (whole_info.get("RemovableMedia", False) or info.get("RemovableMedia", False)):
        raise RuntimeError("target is not marked as removable media")

    return whole_disk, info, whole_info


def _collect_mount_points(parsed: dict[str, Any]) -> list[str]:
    mount_points: list[str] = []

    for partition in parsed.get("Partitions", []) or []:
        if isinstance(partition, dict):
            mount = partition.get("MountPoint")
            if isinstance(mount, str) and mount:
                mount_points.append(mount)
            for apfs_vol in partition.get("APFSVolumes", []) or []:
                if isinstance(apfs_vol, dict):
                    apfs_mount = apfs_vol.get("MountPoint")
                    if isinstance(apfs_mount, str) and apfs_mount:
                        mount_points.append(apfs_mount)

    for disk in parsed.get("AllDisksAndPartitions", []) or []:
        if not isinstance(disk, dict):
            continue
        for partition in disk.get("Partitions", []) or []:
            if not isinstance(partition, dict):
                continue
            mount = partition.get("MountPoint")
            if isinstance(mount, str) and mount:
                mount_points.append(mount)

    # Keep insertion order while removing duplicates.
    unique_mount_points: list[str] = []
    seen: set[str] = set()
    for mount in mount_points:
        if mount not in seen:
            seen.add(mount)
            unique_mount_points.append(mount)
    return unique_mount_points


def wait_mount_point(
    device: str,
    expected_label: Optional[str] = None,
    retries: int = 40,
    delay_sec: float = 0.5,
) -> Path:
    for _ in range(retries):
        list_result = run_cmd(["diskutil", "list", "-plist", f"/dev/{device}"])
        if list_result.returncode == 0:
            parsed = plistlib.loads(list_result.stdout.encode("utf-8"))
            mount_points = _collect_mount_points(parsed)
            if mount_points:
                return Path(mount_points[0])

        if expected_label:
            volume_path = Path("/Volumes") / expected_label
            if volume_path.exists() and volume_path.is_dir():
                return volume_path
        time.sleep(delay_sec)
    raise RuntimeError("formatted volume did not mount in time")


def is_macos() -> bool:
    return platform.system().lower() == "darwin"
