from __future__ import annotations

import platform
import plistlib
import re
import subprocess
import tempfile
import time
import logging
from pathlib import Path
from typing import Any, Callable, Optional

from app.services import drive_service

logger = logging.getLogger("ps2_toolkit.format")


def sanitize_volume_label(label: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_-]", "", label).upper()
    if not sanitized:
        sanitized = "PS2USB"
    return sanitized[:11]


def run_cmd(args: list[str], *, shell: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args if not shell else " ".join(args), check=False, capture_output=True, text=True, shell=shell)


def is_macos() -> bool:
    return platform.system().lower() == "darwin"


def is_windows() -> bool:
    return platform.system().lower() == "windows"


def is_linux() -> bool:
    return platform.system().lower() == "linux"


def diskutil_info(path_or_device: str) -> dict[str, Any]:
    result = run_cmd(["diskutil", "info", "-plist", path_or_device])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"diskutil info failed for {path_or_device}")
    return plistlib.loads(result.stdout.encode("utf-8"))


def validate_format_target_macos(path: Path) -> tuple[str, dict[str, Any], dict[str, Any]]:
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


def validate_format_target_windows(path: Path, expected_device_id: str | None = None) -> dict[str, Any]:
    device = drive_service.validate_external_storage(path, expected_device_id)
    if device.disk_number is None:
        raise RuntimeError("unable to identify the external physical disk")
    disk_number = device.disk_number
    return {"disk_number": disk_number}


def _resolve_linux_device(path: Path) -> str:
    result = run_cmd(["findmnt", "-n", "-o", "SOURCE", "--target", str(path)])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "cannot resolve linux device")
    src = result.stdout.strip()
    if not src.startswith("/dev/"):
        raise RuntimeError("target path is not on a block device")
    return src


def _linux_base_block(device: str) -> str:
    name = Path(device).name
    if name.startswith("mmcblk"):
        return re.sub(r"p\d+$", "", name)
    return re.sub(r"\d+$", "", name)


def validate_format_target_linux(path: Path) -> dict[str, Any]:
    device = _resolve_linux_device(path)
    base = _linux_base_block(device)
    removable = Path("/sys/block") / base / "removable"
    if not removable.exists():
        raise RuntimeError("cannot verify removable flag for target disk")
    if removable.read_text(encoding="utf-8").strip() != "1":
        raise RuntimeError("refusing to format non-removable disk")
    return {"device": device, "base": base}


def validate_format_target(path: Path, expected_device_id: str | None = None) -> dict[str, Any]:
    if is_macos():
        disk, info, whole_info = validate_format_target_macos(path)
        return {"device": disk, "volume_info": info, "disk_info": whole_info}
    if is_windows():
        return validate_format_target_windows(path, expected_device_id)
    if is_linux():
        return validate_format_target_linux(path)
    raise RuntimeError("unsupported platform for format")


def _collect_mount_points(parsed: dict[str, Any]) -> list[str]:
    mount_points: list[str] = []
    for partition in parsed.get("Partitions", []) or []:
        if isinstance(partition, dict):
            mount = partition.get("MountPoint")
            if isinstance(mount, str) and mount:
                mount_points.append(mount)
    unique_mount_points: list[str] = []
    seen: set[str] = set()
    for mount in mount_points:
        if mount not in seen:
            seen.add(mount)
            unique_mount_points.append(mount)
    return unique_mount_points


def wait_mount_point(device: str, expected_label: Optional[str] = None, retries: int = 40, delay_sec: float = 0.5) -> Path:
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


def _powershell_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _windows_format_helper(disk_number: int, script_path: str) -> str:
    return "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            f"$disk = Get-Disk -Number {disk_number} -ErrorAction Stop",
            "if ($disk.BusType -ne 'USB' -or $disk.IsBoot -or $disk.IsSystem) { throw 'Safety check rejected this disk.' }",
            f"$process = Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\\diskpart.exe') -ArgumentList @('/s', {_powershell_literal(script_path)}) -Wait -PassThru -WindowStyle Hidden",
            "exit $process.ExitCode",
        ]
    )


def format_windows(disk_number: int, label: str) -> str:
    script = "\n".join(
        [
            f"select disk {disk_number}",
            "clean",
            "convert mbr",
            "create partition primary",
            f'format fs=fat32 quick label="{label}"',
            "assign",
            "exit",
        ]
    )
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="ascii") as tmp:
        tmp.write(script)
        script_path = tmp.name
    helper_path = ""
    try:
        helper = _windows_format_helper(disk_number, script_path)
        with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8-sig") as helper_file:
            helper_file.write(helper)
            helper_path = helper_file.name
        command = (
            "$ErrorActionPreference='Stop';"
            f"$p=Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',{_powershell_literal(helper_path)}) "
            "-Verb RunAs -Wait -PassThru; exit $p.ExitCode"
        )
        result = run_cmd(["powershell", "-NoProfile", "-NonInteractive", "-Command", command])
        if result.returncode != 0:
            raise RuntimeError(
                "Formatting was cancelled or Windows DiskPart could not format the device. "
                "Approve the Administrator prompt and make sure no files on the USB are open."
            )
    finally:
        Path(script_path).unlink(missing_ok=True)
        if helper_path:
            Path(helper_path).unlink(missing_ok=True)
    return "formatted with diskpart"


def wait_windows_mount(disk_number: int, retries: int = 40, delay_sec: float = 0.5) -> Path:
    query = (
        f"$p=Get-Partition -DiskNumber {disk_number} -ErrorAction SilentlyContinue | "
        "Where-Object DriveLetter | Select-Object -First 1;"
        "if($p){Write-Output ($p.DriveLetter + ':\\')}"
    )
    for _ in range(retries):
        result = run_cmd(["powershell", "-NoProfile", "-NonInteractive", "-Command", query])
        mount = result.stdout.strip()
        if result.returncode == 0 and mount and Path(mount).is_dir():
            return Path(mount)
        time.sleep(delay_sec)
    raise RuntimeError("Formatting finished, but Windows did not mount the new volume. Reconnect the USB and refresh devices.")


def format_linux(device: str, label: str) -> str:
    run_cmd(["umount", device])
    result = run_cmd(["mkfs.vfat", "-F", "32", "-n", label, device])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "mkfs.vfat failed")
    return "formatted with mkfs.vfat"


def format_target(path: Path, label: str, on_step_callback: Callable[[str, str], None], expected_device_id: str | None = None) -> Path:
    safe_label = sanitize_volume_label(label)
    on_step_callback("info", f"format target validation: {path}")
    info = validate_format_target(path, expected_device_id)

    if is_macos():
        device = info["device"]
        on_step_callback("info", f"formatting /dev/{device} as FAT32")
        result = run_cmd(["diskutil", "eraseDisk", "MS-DOS", safe_label, "MBRFormat", f"/dev/{device}"])
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "diskutil erase failed")
        run_cmd(["diskutil", "mountDisk", f"/dev/{device}"])
        mounted = wait_mount_point(device, expected_label=safe_label)
        on_step_callback("success", f"formatted and mounted: {mounted}")
        return mounted

    if is_windows():
        disk_number = int(info["disk_number"])
        on_step_callback("info", "Waiting for Windows Administrator approval…")
        format_windows(disk_number, safe_label)
        mount = wait_windows_mount(disk_number)
        on_step_callback("success", f"Formatted and mounted as {mount}")
        return mount

    if is_linux():
        device = str(info["device"])
        on_step_callback("info", f"formatting {device} via mkfs.vfat")
        format_linux(device, safe_label)
        on_step_callback("success", f"formatted device: {device}")
        return path

    raise RuntimeError("unsupported platform for format")
