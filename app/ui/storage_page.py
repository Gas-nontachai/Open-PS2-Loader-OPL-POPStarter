from __future__ import annotations

import flet as ft

from app.core.constants import REQUIRED_FOLDERS


class StoragePage(ft.Column):
    def __init__(self) -> None:
        self.device_name = ft.Text("No external storage selected", size=22, weight=ft.FontWeight.BOLD)
        self.device_details = ft.Text("Connect a supported USB device and refresh.")
        self.structure = ft.Column([ft.Text(f"○ {folder}") for folder in REQUIRED_FOLDERS])
        self.prepare_btn = ft.FilledButton("Create / Repair OPL Structure", icon=ft.Icons.CREATE_NEW_FOLDER, disabled=True)
        self.format_btn = ft.OutlinedButton("Format Storage", icon=ft.Icons.WARNING_AMBER, disabled=True)
        super().__init__(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=16,
            controls=[
                ft.Text("USB / Storage", size=28, weight=ft.FontWeight.BOLD),
                self.device_name,
                self.device_details,
                ft.Text("OPL Structure", size=18, weight=ft.FontWeight.BOLD),
                self.structure,
                self.prepare_btn,
                ft.Divider(),
                ft.Text("Danger Zone", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_300),
                ft.Text("Formatting permanently deletes all files on this device."),
                self.format_btn,
            ],
        )

    def show_device(self, drive: dict | None, folders: dict[str, bool] | None = None) -> None:
        enabled = bool(drive)
        self.prepare_btn.disabled = not enabled
        self.format_btn.disabled = not enabled
        if not drive:
            self.device_name.value = "No external storage selected"
            self.device_details.value = "Connect a supported USB device and refresh."
        else:
            self.device_name.value = str(drive["model"])
            self.device_details.value = (
                f"{drive['letter']} • {drive['storage_type']} • {drive['connection_type']} • {drive['filesystem']}\n"
                f"{drive['total_human']} total • {drive['free_human']} free"
            )
        states = folders or {}
        self.structure.controls = [
            ft.Text(f"{'✓' if states.get(folder) else '○'} {folder}", color=ft.Colors.GREEN_300 if states.get(folder) else None)
            for folder in REQUIRED_FOLDERS
        ]
