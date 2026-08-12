from __future__ import annotations

import ctypes
import math
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable

from app.core.exceptions import OperationCancelledError

UL_ENTRY_SIZE = 64
UL_PART_SIZE = 1024 * 1024 * 1024
FAT32_MAX_FILE_BYTES = 4 * 1024 * 1024 * 1024 - 1
FAT16_MAX_FILE_BYTES = 1024 * 1024 * 1024 - 1
ProgressCB = Callable[[int, int], None]


@dataclass(frozen=True)
class UlEntry:
    name: str
    game_id: str
    parts: int
    media: str


def safe_title(title: str) -> str:
    encoded = title.encode("ascii", errors="replace").replace(b"?", b" ")
    cleaned = b" ".join(encoded.split()).decode("ascii").strip()
    return (cleaned or "PS2 Game")[:32]


def usba_crc32(title: str) -> int:
    """Return the USBExtreme filename CRC (which is not ZIP CRC32)."""
    table_values = [0] * 256
    crc = 0
    for table in range(256):
        crc = table << 24
        for _ in range(8):
            signed = ctypes.c_int32(crc).value
            crc = signed << 1 if signed < 0 else (signed << 1) ^ 0x04C11DB7
        table_values[255 - table] = ctypes.c_uint32(crc).value
    for byte in safe_title(title).encode("ascii") + b"\0":
        crc = table_values[byte ^ ((crc >> 24) & 0xFF)] ^ ((crc << 8) & 0xFFFFFF00)
        crc &= 0xFFFFFFFF
    return crc


def part_prefix(title: str, game_id: str) -> str:
    return f"ul.{usba_crc32(title):08X}.{game_id}"


def encode_entry(entry: UlEntry) -> bytes:
    name = safe_title(entry.name).encode("ascii").ljust(32, b"\0")
    image = f"ul.{entry.game_id}".encode("ascii")
    if len(image) > 14 or not 1 <= entry.parts <= 255:
        raise ValueError("Invalid USBExtreme game entry.")
    payload = bytearray(UL_ENTRY_SIZE)
    payload[0:32] = name
    payload[32 : 32 + len(image)] = image
    payload[47] = entry.parts
    payload[48] = 0x12 if entry.media == "CD" else 0x14
    payload[53] = 0x08
    return bytes(payload)


def read_entries(target: Path) -> list[UlEntry]:
    cfg = target / "ul.cfg"
    if not cfg.exists():
        return []
    data = cfg.read_bytes()
    if len(data) % UL_ENTRY_SIZE:
        raise ValueError("The existing ul.cfg game list is damaged.")
    entries: list[UlEntry] = []
    for offset in range(0, len(data), UL_ENTRY_SIZE):
        block = data[offset : offset + UL_ENTRY_SIZE]
        name = block[0:32].split(b"\0", 1)[0].decode("ascii", errors="replace").strip()
        image = block[32:47].split(b"\0", 1)[0].decode("ascii", errors="replace")
        if image.startswith("ul.") and name and block[47]:
            entries.append(UlEntry(name, image[3:], block[47], "CD" if block[48] == 0x12 else "DVD"))
    return entries


def write_entries(target: Path, entries: list[UlEntry]) -> None:
    temporary = target / "ul.cfg.part"
    temporary.write_bytes(b"".join(encode_entry(entry) for entry in entries))
    temporary.replace(target / "ul.cfg")


def entry_files(target: Path, entry: UlEntry) -> list[Path]:
    prefix = part_prefix(entry.name, entry.game_id)
    return [target / f"{prefix}.{index:02d}" for index in range(entry.parts)]


def install_iso(
    source: Path,
    target: Path,
    title: str,
    game_id: str,
    media: str,
    progress: ProgressCB | None = None,
    cancel_event: Event | None = None,
) -> tuple[UlEntry, list[Path]]:
    title = safe_title(title)
    total = source.stat().st_size
    part_count = math.ceil(total / UL_PART_SIZE)
    entry = UlEntry(title, game_id, part_count, media)
    prefix = part_prefix(title, game_id)
    temporary_files: list[Path] = []
    final_files: list[Path] = []
    copied = 0
    try:
        with source.open("rb") as source_file:
            for part_index in range(part_count):
                final_path = target / f"{prefix}.{part_index:02d}"
                temporary_path = target / f"{prefix}.{part_index:02d}.part"
                temporary_path.unlink(missing_ok=True)
                temporary_files.append(temporary_path)
                with temporary_path.open("xb") as part_file:
                    remaining = min(UL_PART_SIZE, total - copied)
                    while remaining:
                        if cancel_event and cancel_event.is_set():
                            raise OperationCancelledError("Import cancelled.")
                        chunk = source_file.read(min(4 * 1024 * 1024, remaining))
                        if not chunk:
                            raise OSError("The ISO ended before all game data was copied.")
                        part_file.write(chunk)
                        copied += len(chunk)
                        remaining -= len(chunk)
                        if progress:
                            progress(copied, total)
                    part_file.flush()
                final_files.append(final_path)
        for final_path in final_files:
            final_path.unlink(missing_ok=True)
        for temporary_path, final_path in zip(temporary_files, final_files):
            temporary_path.replace(final_path)
        return entry, final_files
    except Exception:
        for path in temporary_files:
            path.unlink(missing_ok=True)
        raise


def remove_entry(target: Path, game_id: str) -> list[str]:
    entries = read_entries(target)
    removed: list[str] = []
    kept: list[UlEntry] = []
    for entry in entries:
        if entry.game_id.upper() != game_id.upper():
            kept.append(entry)
            continue
        for part in entry_files(target, entry):
            if part.is_file():
                part.unlink()
                removed.append(str(part))
    if len(kept) != len(entries):
        write_entries(target, kept)
    return removed
