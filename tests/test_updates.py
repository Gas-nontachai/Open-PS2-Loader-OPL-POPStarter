from __future__ import annotations

import json
import hashlib
import io
import base64
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from app.core import i18n
from app.services import update_service
from app.services.artwork_providers import ArtworkNetworkError
from app.ui.dialogs import show_update_banner


def staged_download(monkeypatch, tmp_path, payload=b"installer", checksum=None, length=None):
    filename = "PS2-Toolkit-2000X-Setup-2.0.0.exe"
    checksum = checksum or hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(update_service, "fetch_url", Mock(return_value=f"{checksum}  {filename}\n".encode()))
    staging = tmp_path / "staged"
    staging.mkdir()
    monkeypatch.setattr(update_service.tempfile, "mkdtemp", lambda **_: str(staging))
    response = io.BytesIO(payload)
    response.headers = {"Content-Length": str(len(payload) if length is None else length)}
    opener = Mock(return_value=response)
    monkeypatch.setattr(update_service, "urlopen", opener)
    return staging, opener


def test_download_verifies_installer_and_uses_own_release_url(monkeypatch, tmp_path):
    staging, opener = staged_download(monkeypatch, tmp_path)
    progress = Mock()
    path = update_service.download_update({"version": "2.0.0", "url": "https://untrusted.example"}, progress)
    assert path.read_bytes() == b"installer"
    assert opener.call_args.args[0].full_url == f"https://github.com/{update_service.REPOSITORY}/releases/download/v2.0.0/{path.name}"
    progress.assert_called_with(1.0)


@pytest.mark.parametrize("options", [{"checksum": "0" * 64}, {"length": 999}])
def test_bad_download_is_removed(monkeypatch, tmp_path, options):
    staging, _ = staged_download(monkeypatch, tmp_path, **options)
    with pytest.raises(RuntimeError):
        update_service.download_update({"version": "2.0.0"}, Mock())
    assert not staging.exists()


def test_missing_checksum_never_downloads_installer(monkeypatch):
    monkeypatch.setattr(update_service, "fetch_url", Mock(return_value=b""))
    opener = Mock()
    monkeypatch.setattr(update_service, "urlopen", opener)
    with pytest.raises(RuntimeError):
        update_service.download_update({"version": "2.0.0"}, Mock())
    opener.assert_not_called()


def test_helper_waits_for_exit_and_only_restarts_after_success(monkeypatch, tmp_path):
    monkeypatch.setattr(update_service, "supports_in_app_update", lambda: True)
    monkeypatch.setattr(update_service.sys, "executable", str(tmp_path / "app's folder" / "PS2 Toolkit 2000X.exe"))
    monkeypatch.setattr(update_service.subprocess, "DETACHED_PROCESS", 8, raising=False)
    monkeypatch.setattr(update_service.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False)
    launch = Mock()
    monkeypatch.setattr(update_service.subprocess, "Popen", launch)
    update_service.launch_update(tmp_path / "setup.exe")
    script = base64.b64decode(launch.call_args.args[0][-1]).decode("utf-16le")
    assert "WaitForExit(120000)" in script
    assert script.index("WaitForExit") < script.index("$setup = Start-Process")
    assert script.index("$setup.ExitCode -ne 0") < script.index("Start-Process -FilePath", script.index("$setup.ExitCode"))
    assert "/NORESTART" in script and "/DIR=" in script
    assert "app''s folder" in script


def test_update_banner_calls_in_app_handler():
    page = Mock()
    update = Mock()
    show_update_banner(page, {"version": "2.0.0", "url": "https://example.com"}, update)
    banner = page.open.call_args.args[0]
    banner.actions[0].on_click(None)
    update.assert_called_once_with()
    page.launch_url.assert_not_called()


@pytest.mark.parametrize("tag, available", [
    ("v1.0.1", True), ("v1.10.0", True), ("v2.0.0", True),
    ("v1.0.0", False), ("v0.9.9", False), ("v1.1.0-rc.1", False),
    ("1.1.0", False), ("bad", False), (None, False),
])
def test_version_comparison(monkeypatch, tag, available):
    monkeypatch.setattr(update_service, "APP_VERSION", "1.0.0")
    fetch = Mock(return_value=json.dumps({"tag_name": tag}).encode())
    monkeypatch.setattr(update_service, "fetch_url", fetch)
    result = update_service.check_for_update()
    assert bool(result) == available
    fetch.assert_called_once_with(update_service.LATEST_RELEASE_API, timeout=5)
    if available:
        assert result["version"] == tag[1:]
        assert result["url"] == f"https://github.com/{update_service.REPOSITORY}/releases/tag/{tag}"


@pytest.mark.parametrize("flag", ["draft", "prerelease"])
def test_unpublished_or_preview_release_ignored(monkeypatch, flag):
    monkeypatch.setattr(update_service, "fetch_url", Mock(return_value=json.dumps({"tag_name": "v9.0.0", flag: True}).encode()))
    assert update_service.check_for_update() is None


@pytest.mark.parametrize("payload", [b"broken", b"null", b"[]", b"{}", b"\xff"])
def test_invalid_response_is_ignored(monkeypatch, payload):
    monkeypatch.setattr(update_service, "fetch_url", Mock(return_value=payload))
    assert update_service.check_for_update() is None


@pytest.mark.parametrize("error", [
    URLError("offline"), TimeoutError("timeout"),
    HTTPError("url", 404, "no release", {}, None),
    HTTPError("url", 403, "rate limited", {}, None),
    ArtworkNetworkError("offline"),
], ids=["offline", "timeout", "no-release", "rate-limit", "network-wrapper"])
def test_network_errors_do_not_interrupt_startup(monkeypatch, error):
    monkeypatch.setattr(update_service, "fetch_url", Mock(side_effect=error))
    assert update_service.check_for_update() is None


def test_release_cannot_supply_external_download_url(monkeypatch):
    monkeypatch.setattr(update_service, "fetch_url", Mock(return_value=json.dumps({
        "tag_name": "v99.0.0", "html_url": "https://untrusted.example/installer.exe",
    }).encode()))
    assert update_service.check_for_update()["url"].startswith(f"https://github.com/{update_service.REPOSITORY}/")


@pytest.mark.parametrize("language, download, later", [("en", "Download", "Later"), ("th", "ดาวน์โหลด", "ไว้ภายหลัง")])
def test_update_banner_buttons(language, download, later):
    previous = i18n.get_lang()
    try:
        i18n.set_lang(language)
        page = Mock()
        release = {"version": "2.0.0", "url": "https://github.com/example/releases/tag/v2.0.0"}
        show_update_banner(page, release)
        banner = page.open.call_args.args[0]
        assert "2.0.0" in banner.content.value
        assert [action.text for action in banner.actions] == [download, later]
        page.launch_url.assert_not_called()
        banner.actions[0].on_click(None)
        page.launch_url.assert_called_once_with(release["url"])
        banner.actions[1].on_click(None)
        page.close.assert_called_once_with(banner)
    finally:
        i18n.set_lang(previous)
