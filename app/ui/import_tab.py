from __future__ import annotations

from pathlib import Path

import flet as ft

from app.services.target_service import human_bytes


class ImportTab(ft.Column):
    def __init__(self, page: ft.Page, on_pick_isos) -> None:
        self.page = page
        self.on_pick_isos = on_pick_isos
        self.target_path = ft.TextField(visible=False)
        self.selected_isos: list[str] = []
        self.available_bytes = 0

        self.drive_dropdown = ft.Dropdown(label="Destination Device", expand=True, options=[])
        self.refresh_drives_btn = ft.OutlinedButton("Refresh Devices", icon=ft.Icons.REFRESH)
        self.drive_details = ft.Text("No external storage detected", color=ft.Colors.AMBER_300)
        self.device_empty = ft.Text(
            "Connect a USB flash drive or external HDD/SSD and click Refresh.",
            color=ft.Colors.GREY_400,
        )
        self.pick_iso_btn = ft.ElevatedButton("Select PS2 ISO Files", icon=ft.Icons.FOLDER_OPEN, on_click=lambda _: self.on_pick_isos())
        self.selected_iso_text = ft.Text("No games selected")
        self.file_list = ft.Column(spacing=4)
        self.overwrite_checkbox = ft.Checkbox(label="Replace games that already exist", value=False)
        self.import_btn = ft.FilledButton("Import Games", icon=ft.Icons.DOWNLOAD, disabled=True)
        self.cancel_btn = ft.OutlinedButton("Cancel Import", icon=ft.Icons.CANCEL, disabled=True)
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
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=18,
            controls=[
                ft.Text("Import Games", size=28, weight=ft.FontWeight.BOLD),
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
                        ]
                    ),
                ),
                self._step("4", "Import", ft.Column([ft.Row([self.import_btn, self.cancel_btn], wrap=True), self.result_panel])),
                self.target_path,
            ],
        )
        self._interactive_controls = [self.drive_dropdown, self.refresh_drives_btn, self.pick_iso_btn, self.overwrite_checkbox, self.import_btn]

    @staticmethod
    def _step(number: str, title: str, content: ft.Control) -> ft.Control:
        return ft.Container(
            padding=16,
            border=ft.border.all(1, ft.Colors.GREY_800),
            border_radius=12,
            content=ft.Column([ft.Text(f"Step {number} — {title}", size=18, weight=ft.FontWeight.BOLD), content]),
        )

    @staticmethod
    def _summary_row(label: str, value: ft.Text) -> ft.Control:
        return ft.Row([ft.Text(label, width=150, color=ft.Colors.GREY_400), value])

    def set_drives(self, drives: list[dict]) -> None:
        self.drive_dropdown.options = [
            ft.dropdown.Option(key=str(item["path"]), text=f"{item['letter']} • {item['model']} • {item['total_human']} • {item['filesystem']}")
            for item in drives
        ]
        self.device_empty.visible = not bool(drives)
        if not drives:
            self.drive_dropdown.value = None
            self.target_path.value = ""
            self.drive_details.value = "No external storage detected"
            self.available_bytes = 0
        self._update_ready()

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
        total = 0
        for path in paths:
            source = Path(path)
            try:
                size = source.stat().st_size
            except OSError:
                size = 0
            total += size
            large_note = "  • Large ISO: FAT32 will be handled automatically" if size > 4 * 1024**3 - 1 else ""
            self.file_list.controls.append(ft.Text(f"• {source.name}  ({human_bytes(size)}){large_note}"))
        self.selected_iso_text.value = f"{len(paths)} game(s) selected" if paths else "No games selected"
        self.summary_games.value = str(len(paths))
        self.summary_required.value = human_bytes(total)
        self._update_ready()

    def _update_ready(self) -> None:
        self.import_btn.disabled = not bool(self.target_path.value and self.selected_isos)

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
