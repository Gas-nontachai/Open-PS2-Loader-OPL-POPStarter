from pathlib import Path
from threading import Event

import pytest

from app.core.exceptions import OperationCancelledError
from app.services import integrity_service, usbextreme_service as ul


def test_readback_rejects_same_size_corruption_and_truncation(tmp_path):
    source = tmp_path / "source.iso"
    source.write_bytes(b"original data")
    part = tmp_path / "copy.part"
    for data in (b"modified data", b"short"):
        part.write_bytes(data)
        with pytest.raises(OSError, match="verification failed"):
            integrity_service.verify_copy(source, [part])


def test_verification_can_cancel(tmp_path):
    source = tmp_path / "source.iso"
    source.write_bytes(b"data")
    cancel = Event()
    cancel.set()
    with pytest.raises(OperationCancelledError):
        integrity_service.verify_copy(source, [source], cancel)


@pytest.mark.parametrize("failure", ["verify", "index", "rename"])
def test_split_overwrite_failure_preserves_old_game(tmp_path, monkeypatch, failure):
    source = tmp_path / "source.iso"
    source.write_bytes(b"old game data")
    target = tmp_path / "usb"
    target.mkdir()
    monkeypatch.setattr(ul, "UL_PART_SIZE", 4)
    old, files = ul.install_iso(source, target, "Game", "SLUS_214.23", "DVD", entries=[])
    before = {p.name: p.read_bytes() for p in target.iterdir()}
    source.write_bytes(b"new game")
    def fail(*args, **kwargs):
        raise OSError("simulated failure")
    if failure == "verify":
        monkeypatch.setattr(ul, "verify_copy", fail)
    elif failure == "index":
        monkeypatch.setattr(ul, "write_entries", fail)
    else:
        replace = Path.replace
        def fail_publish(path, destination):
            if path.name.endswith(".01.part"):
                raise OSError("simulated failure")
            return replace(path, destination)
        monkeypatch.setattr(Path, "replace", fail_publish)
    with pytest.raises(OSError):
        ul.install_iso(source, target, "Game", "SLUS_214.23", "DVD", entries=[])
    assert {p.name: p.read_bytes() for p in target.iterdir()} == before


def test_split_overwrite_updates_index_and_removes_extra_old_parts(tmp_path, monkeypatch):
    source = tmp_path / "source.iso"
    source.write_bytes(b"old game data")
    target = tmp_path / "usb"
    target.mkdir()
    monkeypatch.setattr(ul, "UL_PART_SIZE", 4)
    ul.install_iso(source, target, "Old title", "SLUS_214.23", "DVD", entries=[])
    source.write_bytes(b"new game")
    entry, files = ul.install_iso(source, target, "New title", "SLUS_214.23", "DVD", entries=[])
    assert ul.read_entries(target) == [entry]
    assert b"".join(p.read_bytes() for p in files) == source.read_bytes()
    assert set(target.iterdir()) == set(files + [target / "ul.cfg"])
