"""Read back staged game data before publishing it to OPL."""
from __future__ import annotations

import hashlib
from pathlib import Path
from threading import Event
from typing import Callable

from app.core.exceptions import OperationCancelledError


def verify_copy(source: Path, parts: list[Path], cancel_event: Event | None = None,
                progress: Callable[[int], None] | None = None) -> None:
    def digest(paths: list[Path], report: bool = False) -> tuple[int, bytes]:
        sha = hashlib.sha256()
        count = 0
        for path in paths:
            with path.open("rb") as stream:
                while True:
                    if cancel_event and cancel_event.is_set():
                        raise OperationCancelledError("Import cancelled during verification.")
                    block = stream.read(4 * 1024 * 1024)
                    if not block:
                        break
                    sha.update(block)
                    count += len(block)
                    if report and progress:
                        progress(min(100, int(count * 100 / max(1, source.stat().st_size))))
        return count, sha.digest()

    expected = digest([source])
    if digest(parts, True) != expected:
        raise OSError("USB verification failed: copied data does not match the source ISO. Check the USB and try again.")
