"""Smoke-test the installed Windows app and capture its actual window."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import sys
import time

from PIL import ImageGrab, ImageStat


def capture(executable: Path, output: Path, page: str) -> None:
    if sys.platform != "win32" or not executable.is_file():
        raise RuntimeError("An installed Windows executable is required")
    user32 = ctypes.windll.user32
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.SetProcessDPIAware()
    process = subprocess.Popen([str(executable), "--screenshot-page", page])
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    windows = []

    @callback_type
    def find_window(hwnd, _):
        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title, len(title))
        if user32.IsWindowVisible(hwnd) and title.value == "PS2 TOOLKIT 2000X":
            windows.append(hwnd)
        return True

    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            windows.clear()
            user32.EnumWindows(find_window, 0)
            if windows:
                break
            time.sleep(0.5)
        if not windows:
            raise RuntimeError("Installed app did not show its main window within 90 seconds")
        hwnd = windows[0]
        user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
        time.sleep(8)
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise RuntimeError("Cannot locate app window")
        image = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))
        assert image.width >= 800 and image.height >= 600, "Unexpected window size"
        assert max(ImageStat.Stat(image).stddev) > 5, "Screenshot appears blank"
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output)
    finally:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)


SCREENSHOT_PAGES = ("home", "import", "library", "storage", "settings")


def main() -> None:
    executable, directory = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    captures = []
    for page in SCREENSHOT_PAGES:
        output = directory / f"windows-{page}.png"
        capture(executable, output, page)
        captures.append(output.read_bytes())
    assert len(set(captures)) == 5, "Expected five distinct page screenshots"


if __name__ == "__main__":
    main()
