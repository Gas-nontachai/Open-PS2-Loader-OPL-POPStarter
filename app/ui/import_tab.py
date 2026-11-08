from __future__ import annotations

from pathlib import Path

import flet as ft
from app.ui.theme import MUTED, WARNING

from app.services.target_service import human_bytes, compute_buffer
from app.ui.theme import heading, panel


class ImportTab(ft.Column):
    def __init__(self, page: ft.Page, on_pick_isos) -> None:
        self.page = page
        self.on_pick_isos = on_pick_isos
        self.target_path = ft.TextField(visible=False)
        self.selected_isos: list[str] = []
        self.available_bytes = 0
        self.required_bytes = 0
        self.file_statuses: dict[str, ft.Text] = {}

        self.drive_dropdown = ft.Dropdown(label="Destination Device", expand=True, options=[])
        self.refresh_drives_btn = ft.OutlinedButton("Refresh Devices", icon=ft.Icons.REFRESH)
        self.drive_details = ft.Text("No external storage detected", color=WARNING)
        self.device_empty = ft.Text(
            "Connect a USB flash drive or external HDD/SSD and click Refresh.",
            color=MUTED,
        )
        self.pick_iso_btn = ft.ElevatedButton("Select PS2 ISO Files", icon=ft.Icons.FOLDER_OPEN, on_click=lambda _: self.on_pick_isos())
        self.selected_iso_text = ft.Text("No games selected")
        self.file_list = ft.Column(spacing=4)
        self.overwrite_checkbox = ft.Checkbox(label="Replace games that already exist", value=False)
        self.import_btn = ft.FilledButton("Import Games", icon=ft.Icons.DOWNLOAD, disabled=True)
        self.cancel_btn = ft.OutlinedButton("Cancel Import", icon=ft.Icons.CANCEL, disabled=True)
        self.job_progress = ft.ProgressBar(value=0, visible=False)
        self.progress_text = ft.Text("Select ISO files to begin.")
        self.result_title = ft.Text("", size=17, weight=ft.FontWeight.BOLD)
        self.result_message = ft.Text("", selectable=True)
        self.result_panel = ft.Container(
            visible=False,
            padding=14,
            border_radius=10,
            content=ft.Column([self.result_title, self.result_message], spacing=6),
        )
        self.summary_destination = ft.Text("—")
        self.summary_games = ft.Text("0")
        self.summary_required = ft.Text("0 B")
        self.summary_available = ft.Text("—")

        super().__init__(
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=18,
            controls=[
                heading("Import Games"),
                ft.Text("Copy PS2 ISO files to verified external USB storage for Open PS2 Loader."),
                self._step("1", "Select Storage", ft.Column([ft.Row([self.drive_dropdown, self.refresh_drives_btn]), self.drive_details, self.device_empty])),
                self._step("2", "Select Games", ft.Column([self.pick_iso_btn, self.selected_iso_text, self.file_list])),
                self._step(
                    "3",
                    "Review",
                    ft.Column(
                        [
                            self._summary_row("Destination", self.summary_destination),
                            self._summary_row("Games", self.summary_games),
                            self._summary_row("Required Space", self.summary_required),
                            self._summary_row("Available Space", self.summary_available),
                            self.overwrite_checkbox,
                            ft.Text("Existing games are skipped unless replacement is enabled. USBExtreme replacement removes the old game first; failure can lose it."),
                        ]
                    ),
                ),
                self._step("4", "Import", ft.Column([ft.Row([self.import_btn, self.cancel_btn], wrap=True), self.job_progress, self.progress_text, self.result_panel])),
                self.target_path,
            ],
        )
        self._interactive_controls = [self.drive_dropdown, self.refresh_drives_btn, self.pick_iso_btn, self.overwrite_checkbox, self.import_btn]

    @staticmethod
    def _step(number: str, title: str, content: ft.Control) -> ft.Control:
        return panel([ft.Text(f"{number}. {title}", size=18, weight=ft.FontWeight.BOLD), content])

    @staticmethod
    def _summary_row(label: str, value: ft.Text) -> ft.Control:
        return ft.Row([ft.Text(label, width=150, color=MUTED), ft.Container(content=value, expand=True)])

    def clear_drive(self) -> None:
        self.drive_dropdown.value = None
        self.target_path.value = ""
        self.available_bytes = 0
        self.drive_details.value = "No external storage selected"
        self.summary_destination.value = "—"
        self.summary_available.value = "—"
        self._update_ready()

    def set_drives(self, drives: list[dict]) -> None:
        self.drive_dropdown.options = [
            ft.dropdown.Option(key=str(item["path"]), text=f"{item['letter']} | {item['model']} | {item['total_human']} | {item['filesystem']}")
            for item in drives
        ]
        self.device_empty.visible = not bool(drives)

    def show_drive(self, drive: dict) -> None:
        self.target_path.value = str(drive["path"])
        self.available_bytes = int(drive["free_bytes"])
        self.drive_details.value = (
            f"{drive['model']} • {drive['storage_type']} • {drive['free_human']} Free / "
            f"{drive['total_human']} • {drive['filesystem']} • {drive['connection_type']}"
        )
        self.device_empty.visible = False
        self.summary_destination.value = f"{drive['model']} ({drive['letter']})"
        self.summary_available.value = drive["free_human"]
        self._update_ready()

    def set_selected_isos(self, paths: list[str]) -> None:
        self.selected_isos = paths
        self.file_list.controls.clear()
        self.file_statuses.clear()
        total = 0
        for path in paths:
            source = Path(path)
            try:
                size = source.stat().st_size
            except OSError:
                size = 0
            total += size
            large_note = "  • Large ISO: FAT32 will be handled automatically" if size > 4 * 1024**3 - 1 else ""
            status = ft.Text(f"{source.name} ({human_bytes(size)}): Pending{large_note}")
            self.file_statuses[str(source.resolve())] = status
            self.file_list.controls.append(status)
        self.selected_iso_text.value = f"{len(paths)} game(s) selected" if paths else "No games selected"
        self.summary_games.value = str(len(paths))
        self.required_bytes = total + compute_buffer(total) if paths else 0
        self.summary_required.value = human_bytes(self.required_bytes) + " (includes safety buffer)"
        self._update_ready()

    def _update_ready(self) -> None:
        self.import_btn.disabled = not bool(self.target_path.value and self.selected_isos and self.available_bytes >= self.required_bytes)
        if self.target_path.value and self.selected_isos and self.available_bytes < self.required_bytes:
            self.progress_text.value = "Not enough space. Remove games or select a larger USB."
        elif not self.job_progress.visible:
            self.progress_text.value = "Review the destination and files, then start import."

    def set_controls_enabled(self, enabled: bool) -> None:
        for control in self._interactive_controls:
            control.disabled = not enabled
        self.cancel_btn.disabled = enabled
        if enabled:
            self._update_ready()

    def show_result(self, success: bool, title: str, message: str) -> None:
        self.result_panel.visible = True
        self.result_panel.bgcolor = ft.Colors.GREEN_900 if success else ft.Colors.RED_900
        self.result_panel.border = ft.border.all(1, ft.Colors.GREEN_500 if success else ft.Colors.RED_400)
        self.result_title.value = title
        self.result_message.value = message

    def clear_result(self) -> None:
        self.result_panel.visible = False

    def translate(self, language: str = "en") -> None:
        # Page-level translation is applied by the shell; controls retain recognizable action labels.
        self.refresh_drives_btn.text = "Refresh Devices" if language == "en" else "รีเฟรชอุปกรณ์"
        self.pick_iso_btn.text = "Select PS2 ISO Files" if language == "en" else "เลือกไฟล์ PS2 ISO"
        self.import_btn.text = "Import Games" if language == "en" else "นำเข้าเกม"
        self.cancel_btn.text = "Cancel Import" if language == "en" else "ยกเลิกการนำเข้า"

    def show_progress(self, event: dict) -> None:
        index, total = event["index"], event["total"]
        percent = event["percent"]
        state = event["state"]
        name = Path(event["path"]).name
        self.job_progress.visible = True
        if state not in {"Checking", "Validated"} and not state.startswith("Failed:"):
            self.job_progress.value = ((index - 1) + percent / 100) / total
        self.progress_text.value = f"{index}/{total}: {name} | {state} {percent}%"
        status = self.file_statuses.get(event["path"])
        if status:
            status.value = f"{name}: {state} {percent}%"
