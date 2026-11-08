"""Real ISO opt-in; CI creates a small ISO with the same SYSTEM.CNF boot ID."""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pycdlib
import pytest

from app.controllers import game_controller, import_controller
from app.services import game_service, usbextreme_service


@pytest.fixture(scope="module")
def source_iso(tmp_path_factory):
    provided = os.environ.get("PS2_TEST_ISO")
    if provided:
        source = Path(provided).resolve()
        assert source.is_file(), "PS2_TEST_ISO does not exist"
        assert game_service.extract_game_id_from_iso(source) == "SLUS_214.23"
        return source
    source = tmp_path_factory.mktemp("iso") / "Grand Theft Auto - Liberty City Stories (USA).iso"
    content = b"BOOT2 = cdrom0:\\SLUS_214.23;1\r\nVER = 1.00\r\n"
    iso = pycdlib.PyCdlib()
    iso.new()
    iso.add_fp(io.BytesIO(content), len(content), iso_path="/SYSTEM.CNF;1")
    iso.write(str(source))
    iso.close()
    return source


def digest(paths):
    sha = hashlib.sha256()
    for path in paths:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                sha.update(block)
    return sha.hexdigest()


@pytest.fixture
def target(tmp_path, monkeypatch):
    destination = tmp_path / "USB with spaces"
    destination.mkdir()
    monkeypatch.setattr("app.services.drive_service.validate_external_storage", lambda *_: SimpleNamespace(filesystem="FAT32"))
    return destination


@pytest.mark.parametrize("filesystem", ["FAT32", "exFAT", "NTFS", "FAT16"])
def test_import_verify_duplicate_scan_delete(source_iso, target, monkeypatch, filesystem):
    monkeypatch.setattr("app.services.drive_service.validate_external_storage", lambda *_: SimpleNamespace(filesystem=filesystem))
    result = import_controller.import_isos(str(target), [str(source_iso)], False)
    assert result["status"] == "success", result
    assert result["details"]["imported_count"] == 1
    game = result["details"]["imported"][0]
    assert game["game_id"] == "SLUS_214.23"
    assert game["id_source"] == "iso"
    split = filesystem == "FAT16" and source_iso.stat().st_size > usbextreme_service.FAT16_MAX_FILE_BYTES
    if split:
        entry, = usbextreme_service.read_entries(target)
        files = usbextreme_service.entry_files(target, entry)
        assert all(p.stat().st_size <= usbextreme_service.UL_PART_SIZE for p in files)
    else:
        files = [Path(game["destination"])]
        assert game["target_folder"] == game_service.classify_iso_media(source_iso.stat().st_size)
    assert digest(files) == digest([source_iso])
    assert not list(target.rglob("*.part"))
    manifest = game_service.load_manifest(target)
    assert len(manifest["entries"]) == 1
    duplicate = import_controller.import_isos(str(target), [str(source_iso)], False)
    assert duplicate["status"] == "success", duplicate
    assert duplicate["details"]["imported_count"] == 0
    scanned = game_controller.scan_games(str(target))
    assert scanned["status"] == "success", scanned
    assert scanned["details"]["count"] == 1
    assert scanned["details"]["games"][0]["size_bytes"] == source_iso.stat().st_size
    deleted = game_controller.delete_game(str(target), game["game_id"], game["file"])
    assert deleted["status"] == "success", deleted
    assert not any(p.exists() for p in files)
    assert game_service.load_manifest(target)["entries"] == []


def test_cancel_during_copy(source_iso, target):
    cancel = Event()

    def progress(_status, message):
        if message.startswith("copying "):
            cancel.set()

    result = import_controller.import_isos(str(target), [str(source_iso)], False, progress, cancel)
    assert result["status"] == "cancelled", result
    assert not list(target.rglob("*.part"))
    assert not list(target.rglob("*.iso"))


def test_full_disk_during_copy_preserves_existing_game(source_iso, target, monkeypatch):
    folder = target / game_service.classify_iso_media(source_iso.stat().st_size)
    folder.mkdir()
    filename = game_service.build_opl_iso_filename("SLUS_214.23", source_iso.name)
    old = folder / filename
    old.write_bytes(b"existing game")

    def fail_copy(_src, dst, **_kwargs):
        dst.write_bytes(b"partial")
        error = OSError("disk full")
        error.winerror = 112
        raise error

    monkeypatch.setattr(import_controller, "_copy_with_progress", fail_copy)
    result = import_controller.import_isos(str(target), [str(source_iso)], True)
    assert result["status"] == "error", result
    assert "space" in result["message"]
    assert old.read_bytes() == b"existing game"
    assert not list(target.rglob("*.part"))


@pytest.mark.parametrize("paths, message", [([], "no files"), (["missing.iso"], "not found"), (["bad.txt"], "only .iso")])
def test_invalid_input(target, paths, message):
    if paths == ["bad.txt"]:
        file = target.parent / "bad.txt"
        file.write_text("invalid")
        paths = [str(file)]
    result = import_controller.import_isos(str(target), paths, False)
    assert result["status"] == "error"
    assert message in result["message"]


def test_overwrite_replaces_file_after_success(source_iso, target):
    folder = target / game_service.classify_iso_media(source_iso.stat().st_size)
    folder.mkdir()
    old = folder / game_service.build_opl_iso_filename("SLUS_214.23", source_iso.name)
    old.write_bytes(b"old game")
    result = import_controller.import_isos(str(target), [str(source_iso)], True)
    assert result["status"] == "success", result
    assert result["details"]["imported_count"] == 1
    assert digest([old]) == digest([source_iso])
    assert not list(target.rglob("*.part"))


@pytest.mark.parametrize("size, media", [(0, "CD"), (700 * 1024**2 - 1, "CD"), (700 * 1024**2, "DVD")])
def test_media_size_boundary(size, media):
    assert game_service.classify_iso_media(size) == media


def test_split_content_and_cancel_cleanup(tmp_path, monkeypatch):
    source = tmp_path / "source.iso"
    source.write_bytes(b"0123456789abcdefghijkl")
    target = tmp_path / "usb"
    target.mkdir()
    monkeypatch.setattr(usbextreme_service, "UL_PART_SIZE", 8)
    entry, files = usbextreme_service.install_iso(source, target, "GTA", "SLUS_214.23", "DVD")
    assert entry.parts == 3
    assert [p.stat().st_size for p in files] == [8, 8, 6]
    assert digest(files) == digest([source])
    for file in files:
        file.unlink()
    cancel = Event()

    def progress(_copied, _total):
        cancel.set()

    from app.core.exceptions import OperationCancelledError
    with pytest.raises(OperationCancelledError):
        usbextreme_service.install_iso(source, target, "GTA", "SLUS_214.23", "DVD", progress, cancel)
    assert list(target.iterdir()) == []


def test_corrupt_ul_cfg_is_rejected_without_deleting_parts(tmp_path):
    (tmp_path / "ul.cfg").write_bytes(b"broken")
    part = tmp_path / "ul.keep.00"
    part.write_bytes(b"keep")
    with pytest.raises(ValueError, match="damaged"):
        usbextreme_service.remove_entry(tmp_path, "SLUS_214.23")
    assert part.read_bytes() == b"keep"
