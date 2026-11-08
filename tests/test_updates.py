from __future__ import annotations

import json
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from app.core import i18n
from app.services import update_service
from app.services.artwork_providers import ArtworkNetworkError
from app.ui.dialogs import show_update_banner


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
