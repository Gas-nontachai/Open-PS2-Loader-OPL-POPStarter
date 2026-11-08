import sys
from unittest.mock import Mock

import pytest

from scripts import capture_windows, release_notes


def test_notes_have_five_linked_previews_and_actual_changes():
    notes = release_notes.render_notes("owner/project", "v1.2.0", "Setup-1.2.0.exe", "v1.1.0", "- Fix cancelled imports (abc123)", "abc123")
    assert notes.count('width="150"') == 5
    for page in release_notes.PAGES:
        assert f'windows-{page}.png' in notes
    assert "Fix cancelled imports (abc123)" in notes
    assert "/compare/v1.1.0...v1.2.0" in notes
    assert "Setup-1.2.0.exe" in notes
    assert "SHA256SUMS.txt" in notes
    assert "Source commit: [abc123]" in notes
    assert set(release_notes.PAGES) == set(capture_windows.SCREENSHOT_PAGES)


def test_first_release_notes():
    notes = release_notes.render_notes("owner/project", "v1.0.0", "Setup.exe", None, "- Initial release", "abc")
    assert "รุ่นแรก" in notes
    assert "/compare/" not in notes


@pytest.mark.parametrize("repository, tag", [("https://bad", "v1.0.0"), ("owner/project", "invalid")])
def test_invalid_release_coordinates(repository, tag):
    with pytest.raises(ValueError):
        release_notes.render_notes(repository, tag, "Setup.exe", None, "changes", "abc")


def test_capture_visits_all_five_pages(tmp_path, monkeypatch):
    visited = []

    def capture(_executable, output, page):
        visited.append(page)
        output.write_bytes(page.encode())

    monkeypatch.setattr(capture_windows, "capture", capture)
    monkeypatch.setattr(sys, "argv", ["capture_windows.py", "app.exe", str(tmp_path)])
    capture_windows.main()
    assert visited == list(release_notes.PAGES)
    assert len(list(tmp_path.glob("windows-*.png"))) == 5


def test_duplicate_captures_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_windows, "capture", lambda _exe, output, _page: output.write_bytes(b"same screen"))
    monkeypatch.setattr(sys, "argv", ["capture_windows.py", "app.exe", str(tmp_path)])
    with pytest.raises(AssertionError, match="distinct"):
        capture_windows.main()


@pytest.mark.parametrize("page", [None, *capture_windows.SCREENSHOT_PAGES])
def test_app_start_page_argument(page, monkeypatch):
    from app import main

    argv = ["app.exe"] + (["--screenshot-page", page] if page else [])
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(main, "load_dotenv", Mock())
    monkeypatch.setattr(main, "configure_logging", Mock())
    build = Mock()
    monkeypatch.setattr(main, "build_app", build)
    launcher = Mock()
    monkeypatch.setattr(main.ft, "app", launcher)
    main.main()
    target = launcher.call_args.kwargs["target"]
    target("page")
    build.assert_called_once_with("page", screenshot_page=page)


def test_change_history_first_and_subsequent_release(tmp_path, monkeypatch):
    import subprocess

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    git("init", "-b", "main")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.com")
    file = tmp_path / "app.txt"
    file.write_text("first")
    git("add", ".")
    git("commit", "-m", "Initial app")
    git("tag", "v1.0.0")
    monkeypatch.chdir(tmp_path)
    baseline, changes, commit = release_notes.change_history("v1.0.0")
    assert baseline is None
    assert "Initial app" in changes
    assert commit == git("rev-parse", "HEAD")
    file.write_text("second")
    git("commit", "-am", "Improve artwork import")
    git("tag", "v1.1.0")
    baseline, changes, commit = release_notes.change_history("v1.1.0")
    assert baseline == "v1.0.0"
    assert "Improve artwork import" in changes
    assert "Initial app" not in changes
    assert commit == git("rev-parse", "v1.1.0")
