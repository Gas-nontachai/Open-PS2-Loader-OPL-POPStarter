from __future__ import annotations

import json
import logging
import re
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import base64
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from app.core.constants import APP_VERSION
from app.services.artwork_providers import fetch_url

REPOSITORY = "Gas-nontachai/Open-PS2-Loader-OPL-POPStarter"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
logger = logging.getLogger("ps2_toolkit.update")


def supports_in_app_update() -> bool:
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def download_update(release: dict[str, str], progress: Callable[[float], None]) -> Path:
    """Stage a complete, checksum-verified installer from our release only."""
    version = release["version"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Invalid update version")
    filename = f"PS2-Toolkit-2000X-Setup-{version}.exe"
    base = f"https://github.com/{REPOSITORY}/releases/download/v{version}"
    manifest = fetch_url(f"{base}/SHA256SUMS.txt", timeout=30).decode("utf-8-sig")
    matches = [line.split()[0].lower() for line in manifest.splitlines()
               if len(line.split()) == 2 and line.split()[1] == filename]
    if len(matches) != 1 or not re.fullmatch(r"[a-f0-9]{64}", matches[0]):
        raise RuntimeError("Release has no valid installer checksum")
    staging = Path(tempfile.mkdtemp(prefix="ps2-toolkit-update-"))
    target = staging / filename
    try:
        request = Request(f"{base}/{filename}", headers={"User-Agent": "PS2-Toolkit-Updater"})
        with urlopen(request, timeout=30) as response, target.open("wb") as output:
            total = int(response.headers.get("Content-Length", 0))
            digest = hashlib.sha256()
            received = 0
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
                received += len(chunk)
                progress(min(received / total, 1.0) if total else 0.0)
            if not received or (total and received != total):
                raise RuntimeError("Update download was incomplete")
        if digest.hexdigest() != matches[0]:
            raise RuntimeError("Update checksum verification failed")
        progress(1.0)
        return target
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def launch_update(installer: Path) -> None:
    """Start a detached helper; it waits for this process before replacing files."""
    if not supports_in_app_update():
        raise RuntimeError("In-app updates require the packaged Windows application")
    executable = Path(sys.executable).resolve()
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    arguments = f'/VERYSILENT /SUPPRESSMSGBOXES /SP- /NORESTART /NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS /DIR="{executable.parent}" /LOG="{installer.parent / "install.log"}"'
    script = f"""
$ErrorActionPreference = 'Stop'
try {{
    $parent = Get-Process -Id {os.getpid()} -ErrorAction SilentlyContinue
    if ($parent -and -not $parent.WaitForExit(120000)) {{ throw 'App did not close. Update cancelled.' }}
    Start-Sleep -Seconds 2
    $setup = Start-Process -FilePath {quote(installer)} -ArgumentList {quote(arguments)} -Wait -PassThru -WindowStyle Hidden
    if ($setup.ExitCode -ne 0) {{ throw "Installer failed (exit $($setup.ExitCode))." }}
    Start-Process -FilePath {quote(executable)} -WorkingDirectory {quote(executable.parent)} -WindowStyle Hidden
    Remove-Item -LiteralPath {quote(installer.parent)} -Recurse -Force
}} catch {{
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(('Update failed: ' + $_.Exception.Message + '\nLog: ' + {quote(installer.parent / 'install.log')}), 'PS2 Toolkit update')
}}
"""
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", encoded],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def check_for_update() -> dict[str, str] | None:
    """Return a newer stable release; unavailable checks never block app startup."""
    try:
        release = json.loads(fetch_url(LATEST_RELEASE_API, timeout=5))
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            return None
        tag = release.get("tag_name")
        if not isinstance(tag, str) or not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
            return None
        version = tag[1:]
        if tuple(map(int, version.split("."))) <= tuple(map(int, APP_VERSION.split("."))):
            return None
        # Build the URL ourselves so API response fields cannot redirect users elsewhere.
        return {"version": version, "url": f"https://github.com/{REPOSITORY}/releases/tag/{tag}"}
    except (OSError, ValueError, RuntimeError) as exc:
        logger.info("Update check unavailable: %s", exc)
        return None
