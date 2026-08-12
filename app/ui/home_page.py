from __future__ import annotations

import flet as ft


class HomePage(ft.Column):
    def __init__(self) -> None:
        self.device_title = ft.Text("No external storage connected", size=20, weight=ft.FontWeight.BOLD)
        self.device_details = ft.Text("Connect a USB flash drive or external HDD/SSD to begin.")
        self.refresh_btn = ft.OutlinedButton("Refresh Devices", icon=ft.Icons.REFRESH)
        self.import_btn = ft.FilledButton("Import Games", icon=ft.Icons.DOWNLOAD, disabled=True)
        self.library_btn = ft.ElevatedButton("Manage Games", icon=ft.Icons.SPORTS_ESPORTS, disabled=True)
        self.artwork_btn = ft.TextButton("Manage Artwork", icon=ft.Icons.IMAGE_OUTLINED, disabled=True)
        self.storage_btn = ft.TextButton("Storage Tools", icon=ft.Icons.USB, disabled=True)
        super().__init__(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=20,
            controls=[
                ft.Text("PS2 TOOLKIT 2000X", size=34, weight=ft.FontWeight.BOLD),
                ft.Text("Prepare your external USB storage for Open PS2 Loader.", size=18),
                ft.Container(
                    padding=20,
                    border=ft.border.all(1, ft.Colors.GREY_800),
                    border_radius=14,
                    content=ft.Column([ft.Text("Connected Device", color=ft.Colors.GREY_400), self.device_title, self.device_details, self.refresh_btn]),
                ),
                ft.Row([self.import_btn, self.library_btn], wrap=True),
                ft.Row([self.artwork_btn, self.storage_btn], wrap=True),
            ],
        )

    def show_device(self, drive: dict | None) -> None:
        connected = bool(drive)
        if drive:
            self.device_title.value = str(drive["model"])
            self.device_details.value = f"{drive['letter']} • {drive['total_human']} • {drive['filesystem']} • {drive['free_human']} free"
        else:
            self.device_title.value = "No external storage connected"
            self.device_details.value = "Connect a USB flash drive or external HDD/SSD to begin."
        for button in (self.import_btn, self.library_btn, self.artwork_btn, self.storage_btn):
            button.disabled = not connected
