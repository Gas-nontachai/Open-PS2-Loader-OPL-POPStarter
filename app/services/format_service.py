from __future__ import annotations

import platform
import plistlib
import re
import subprocess
import time
from pathlib import Path
from typing import Any


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


def wait_mount_point(device: str, retries: int = 12, delay_sec: float = 0.5) -> Path:
    for _ in range(retries):
        list_result = run_cmd(["diskutil", "list", "-plist", f"/dev/{device}"])
        if list_result.returncode == 0:
            parsed = plistlib.loads(list_result.stdout.encode("utf-8"))
            partitions = parsed.get("Partitions", [])
            for partition in partitions:
                mount_point = partition.get("MountPoint")
                if mount_point:
                    return Path(mount_point)
        time.sleep(delay_sec)
    raise RuntimeError("formatted volume did not mount in time")


def is_macos() -> bool:
    return platform.system().lower() == "darwin"
