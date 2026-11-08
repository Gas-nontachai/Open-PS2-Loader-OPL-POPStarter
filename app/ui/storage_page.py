from __future__ import annotations

import flet as ft
from app.ui.theme import DESTRUCTIVE, SUCCESS, WARNING

from app.core.constants import REQUIRED_FOLDERS
from app.ui.theme import danger_style, heading


class StoragePage(ft.Column):
    def __init__(self) -> None:
        self.device_name = ft.Text("No external storage selected", size=22, weight=ft.FontWeight.BOLD)
        self.device_details = ft.Text("Connect a supported USB device and refresh.")
        self.structure = ft.Row([ft.Text(f"{folder}: Not checked", width=200) for folder in REQUIRED_FOLDERS], wrap=True)
        self.prepare_btn = ft.FilledButton("Create / Repair OPL Structure", icon=ft.Icons.CREATE_NEW_FOLDER, disabled=True)
        self.format_btn = ft.OutlinedButton("Format Storage", icon=ft.Icons.WARNING_AMBER, disabled=True, style=danger_style())
        super().__init__(
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=16,
            controls=[
                heading("USB / Storage"),
                self.device_name,
                self.device_details,
                ft.Text("OPL Structure", size=18, weight=ft.FontWeight.BOLD),
                self.structure,
                ft.Row([self.prepare_btn], wrap=True),
                ft.Text("Repair adds missing folders only. It does not repair the file system or recover data."),
                ft.Divider(),
                ft.Text("Danger Zone", size=18, weight=ft.FontWeight.BOLD, color=DESTRUCTIVE),
                ft.Text("Format erases the entire physical disk and every partition. DiskPart FAT32 may fail on some capacities."),
                ft.Row([self.format_btn], wrap=True),
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
            ft.Text(f"{folder}: {'Present' if states.get(folder) else ('Missing' if drive else 'Not checked')}", color=SUCCESS if states.get(folder) else None, width=200)
            for folder in REQUIRED_FOLDERS
        ]
