from __future__ import annotations

import flet as ft
from app.ui.theme import DESTRUCTIVE, SUCCESS, WARNING

from app.core.constants import REQUIRED_FOLDERS
from app.ui.theme import danger_style, heading, page_header, panel, BORDER, MUTED, TEXT, PRIMARY


class StoragePage(ft.Column):
    def __init__(self) -> None:
        self.device_name = ft.Text("No external storage selected", size=22, weight=ft.FontWeight.BOLD)
        self.device_details = ft.Text("Connect a supported USB device and refresh.")
        self.structure = ft.Row([ft.Text(f"{folder}: Not checked", width=200) for folder in REQUIRED_FOLDERS], wrap=True)
        self.filesystem_status = ft.Text("Connect a drive to check filesystem compatibility.", size=12, color=MUTED)
        self.prepare_btn = ft.FilledButton("Create / Repair OPL Structure", icon=ft.Icons.CREATE_NEW_FOLDER, disabled=True)
        self.format_btn = ft.OutlinedButton("Format Storage", icon=ft.Icons.WARNING_AMBER, disabled=True, style=danger_style())
        super().__init__(
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=16,
            controls=[
                page_header("USB & storage", "Prepare an OPL drive and review its structure before importing games."),
                panel([
                    ft.Row([ft.Icon(ft.Icons.USB, color=PRIMARY), self.device_name], spacing=10),
                    self.device_details,
                    self.filesystem_status,
                    ft.Divider(color=BORDER),
                    ft.Text("OPL folder structure", size=18, weight=ft.FontWeight.BOLD, color=TEXT),
                    self.structure,
                    ft.Text("Repair adds missing folders. It does not repair a file system or recover data.", size=12, color=MUTED),
                    ft.Row([self.prepare_btn], wrap=True),
                ]),
                ft.Container(
                    padding=18,
                    border=ft.border.all(1, "#62323C"),
                    bgcolor="#24151E",
                    border_radius=14,
                    content=ft.Column([
                        ft.Row([ft.Icon(ft.Icons.WARNING_AMBER, color=DESTRUCTIVE), ft.Text("Format drive", size=17, weight=ft.FontWeight.BOLD, color=DESTRUCTIVE)], spacing=9),
                        ft.Text("Formatting erases the entire physical disk and every partition. Confirm the selected device carefully.", color=MUTED),
                        ft.Row([self.format_btn], wrap=True),
                    ], spacing=10),
                ),
            ],
        )

    def show_device(
        self,
        drive: dict | None,
        folders: dict[str, bool] | None = None,
        filesystem_supported: bool = True,
    ) -> None:
        enabled = bool(drive)
        self.prepare_btn.disabled = not enabled or not filesystem_supported
        self.format_btn.disabled = not enabled
        if not drive:
            self.device_name.value = "No external storage selected"
            self.device_details.value = "Connect a supported USB device and refresh."
            self.filesystem_status.value = "Connect a drive to check filesystem compatibility."
            self.filesystem_status.color = MUTED
        else:
            filesystem = str(drive.get("filesystem") or "Unknown")
            self.device_name.value = str(drive["model"])
            self.device_details.value = (
                f"{drive['letter']} • {drive['storage_type']} • {drive['connection_type']} • {drive['filesystem']}\n"
                f"{drive['total_human']} total • {drive['free_human']} free"
            )
            if filesystem_supported:
                self.filesystem_status.value = f"{filesystem} is supported. You can still format this drive to erase all data and start fresh."
                self.filesystem_status.color = SUCCESS
            else:
                self.filesystem_status.value = f"{filesystem} is not recognized as supported. Formatting erases the entire drive."
                self.filesystem_status.color = DESTRUCTIVE
        states = folders or {}
        self.structure.controls = [
            ft.Text(f"{folder}: {'Present' if states.get(folder) else ('Missing' if drive else 'Not checked')}", color=SUCCESS if states.get(folder) else None, width=200)
            for folder in REQUIRED_FOLDERS
        ]
