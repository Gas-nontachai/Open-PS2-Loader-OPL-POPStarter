"""Reversible UI/safety checks; no physical storage is used."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.controllers import art_controller, import_controller
from app.services.target_service import compute_buffer
from app.ui import dialogs
from app.ui.art_tab import ArtTab
from app.ui.device_selection import retained_device
from app.ui.import_tab import ImportTab


def test_refresh_requires_explicit_selection_and_same_identity():
    devices = [{"path": "E:", "device_id": "old"}, {"path": "F:", "device_id": "other"}]
    assert retained_device(devices, "", "") is None
    assert retained_device(devices, "E:", "old") == devices[0]
    assert retained_device(devices, "E:", "replacement") is None
    assert retained_device([], "E:", "old") is None


def test_import_review_includes_buffer_and_clears_removed_target(tmp_path):
    source = tmp_path / "game.iso"
    source.write_bytes(b"ISO")
    tab = ImportTab(None, lambda: None)
    tab.set_selected_isos([str(source)])
    assert tab.required_bytes == 3 + compute_buffer(3)
    tab.target_path.value = "E:"
    tab.available_bytes = tab.required_bytes - 1
    tab._update_ready()
    assert tab.import_btn.disabled
    tab.available_bytes += 1
    tab._update_ready()
    assert not tab.import_btn.disabled
    tab.clear_drive()
    assert tab.import_btn.disabled
    assert tab.summary_destination.value == "—"


def test_progress_uses_actual_file_and_job_counters(tmp_path):
    source = tmp_path / "game.iso"
    source.write_bytes(b"ISO")
    tab = ImportTab(None, lambda: None)
    tab.set_selected_isos([str(source)])
    tab.show_progress(dict(index=2, total=3, path=str(source), percent=50, state="Copying"))
    assert tab.job_progress.value == 0.5
    assert "Copying 50%" in tab.file_statuses[str(source)].value


@pytest.mark.parametrize("phrase", ["format", " FORMAT", "FORMAT ", ""])
def test_format_backend_rejects_nonliteral_confirmation(phrase, monkeypatch):
    validate = Mock()
    monkeypatch.setattr("app.services.drive_service.validate_external_storage", validate)
    assert import_controller.format_target("E:", phrase, "PS2USB")["status"] == "error"
    validate.assert_not_called()


def test_format_dialog_identity_and_disabled_confirmation():
    page = SimpleNamespace(open=Mock(), close=Mock(), update=Mock())
    confirmed = Mock()
    dialogs.show_format_dialog(page, confirmed, dict(model="USB", letter="E:", total_human="16 GB", device_id="physical-id"))
    dialog = page.open.call_args.args[0]
    phrase = dialog.content.controls[4]
    button = dialog.actions[1]
    assert button.disabled
    phrase.value = "format"
    phrase.on_change(None)
    assert button.disabled
    phrase.value = "FORMAT"
    phrase.on_change(None)
    assert not button.disabled
    button.on_click(None)
    confirmed.assert_called_once_with("PS2USB")
    page.close.assert_called_once_with(dialog)


def test_artwork_status_revalidates_identity(monkeypatch):
    validate = Mock(side_effect=RuntimeError("Device replaced"))
    monkeypatch.setattr("app.services.drive_service.validate_external_storage", validate)
    result = art_controller.get_artwork_status("E:", "SLUS_209.46", "old-device")
    assert result["status"] == "error"
    validate.assert_called_once_with("E:", "old-device")


def test_artwork_rejects_unreadable_preview_and_disables_empty_actions(tmp_path):
    tab = ArtTab(lambda _: None)
    assert tab.download_btn.disabled and tab.choose_btn.disabled and tab.batch_btn.disabled
    source = tmp_path / "invalid.png"
    source.write_bytes(b"invalid")
    tab.set_manual_file("COV", str(source))
    assert tab.save_btn.disabled and not tab.new_preview.visible
    assert "rejected" in tab.status_text.value


def test_format_service_keeps_physical_identity(monkeypatch):
    from pathlib import Path
    from app.services import format_service
    validate = Mock(return_value=SimpleNamespace(disk_number=7))
    monkeypatch.setattr("app.services.drive_service.validate_external_storage", validate)
    assert format_service.validate_format_target_windows(Path("E:"), "original") == {"disk_number": 7}
    validate.assert_called_once_with(Path("E:"), "original")


def test_workspace_tabs_serialize_on_supported_python():
    import flet as ft
    from app.ui.workspace_tab import WorkspaceTab
    tabs = ft.Tabs(tabs=[WorkspaceTab(text="Game Files", icon=ft.Icons.SPORTS_ESPORTS, content=ft.Text("Empty")),
                         WorkspaceTab(text="Artwork", icon=ft.Icons.IMAGE_OUTLINED, content=ArtTab(lambda _: None))])
    assert tabs._build_add_commands(index={}, added_controls=[])


@pytest.mark.parametrize("start_page", ["home", "import", "library", "storage", "settings"])
def test_shell_builds_and_serializes_all_five_pages(start_page, monkeypatch):
    from app.ui import app_layout
    from app.core.config import AppConfig

    class PreviewPage:
        window = SimpleNamespace()
        overlay = []
        controls = []

        def add(self, control):
            self.controls = [control]

        def update(self):
            for control in self.controls:
                control._build_add_commands(index={}, added_controls=[])

    monkeypatch.setattr(app_layout.config_service, "load_config", lambda: AppConfig())
    monkeypatch.setattr(app_layout.threading, "Thread", Mock())
    app_layout.build_app(PreviewPage(), start_page)
