from __future__ import annotations

import flet as ft
from app.ui.theme import BACKGROUND, BORDER, MUTED, PRIMARY, PRIMARY_SOFT, SUCCESS, SURFACE, SURFACE_RAISED, TEXT, eyebrow, heading, panel


class HomePage(ft.Column):
    def __init__(self) -> None:
        self.device_title = ft.Text("Connect your OPL drive", size=22, weight=ft.FontWeight.BOLD, color=TEXT)
        self.device_details = ft.Text("Plug in an external USB drive to get your game library ready.", color=MUTED)
        self.device_dropdown = ft.Dropdown(label="External USB device", options=[], border_radius=10)
        self.refresh_btn = ft.OutlinedButton("Refresh", icon=ft.Icons.REFRESH)
        self.import_btn = ft.FilledButton("Add games", icon=ft.Icons.ADD, disabled=True)
        self.library_btn = ft.OutlinedButton("Open library", icon=ft.Icons.SPORTS_ESPORTS, disabled=True)
        self.artwork_btn = ft.TextButton("Artwork", icon=ft.Icons.IMAGE_OUTLINED, disabled=True)
        self.storage_btn = ft.TextButton("USB setup", icon=ft.Icons.USB, disabled=True)
        hero = ft.Container(
            padding=28,
            border_radius=18,
            gradient=ft.LinearGradient(begin=ft.alignment.top_left, end=ft.alignment.bottom_right, colors=["#22243A", "#151B2C", "#251D19"]),
            border=ft.border.all(1, BORDER),
            content=ft.Row(
                [
                    ft.Column(
                        [
                            eyebrow("Your PS2 collection, ready to play"),
                            ft.Text("Manage your\nOPL library.", size=34, weight=ft.FontWeight.BOLD, color=TEXT),
                            ft.Text("Import games, organize artwork, and prepare your USB drive in one place.", size=14, color=MUTED, width=380),
                            ft.Row([self.import_btn, self.library_btn], spacing=10, wrap=True),
                        ],
                        spacing=16,
                        expand=True,
                    ),
                    ft.Container(
                        width=180,
                        height=180,
                        border_radius=90,
                        bgcolor="#201E27",
                        border=ft.border.all(1, "#483A29"),
                        alignment=ft.alignment.center,
                        content=ft.Icon(ft.Icons.SPORTS_ESPORTS, size=92, color=PRIMARY),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        self.storage_card = ft.Container(
            padding=22,
            bgcolor=SURFACE,
            border=ft.border.all(1, BORDER),
            border_radius=16,
            content=ft.Column(
                [
                    ft.Row([ft.Icon(ft.Icons.USB, color=PRIMARY), ft.Text("Storage", size=17, weight=ft.FontWeight.BOLD, color=TEXT), ft.Container(expand=True), self.refresh_btn]),
                    self.device_title,
                    self.device_details,
                    ft.Row([self.device_dropdown], expand=True),
                    ft.Container(
                        padding=14,
                        border_radius=12,
                        bgcolor=SURFACE_RAISED,
                        content=ft.Row(
                            [ft.Icon(ft.Icons.SHIELD_OUTLINED, color=SUCCESS), ft.Text("Only verified external USB drives are available.", size=12, color=MUTED, expand=True)],
                            spacing=10,
                        ),
                    ),
                ],
                spacing=11,
            ),
        )
        super().__init__(
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=22,
            controls=[
                ft.Row([eyebrow("YOUR PLAYSPACE"), ft.Container(expand=True), ft.Text("LOCAL • OFFLINE READY", size=11, color=MUTED)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                hero,
                ft.ResponsiveRow(
                    [
                        ft.Container(col={"sm": 12, "md": 7}, content=self.storage_card),
                        ft.Container(col={"sm": 12, "md": 5}, content=panel([
                            eyebrow("QUICK ACTIONS"),
                            ft.Text("Pick up where you left off", size=18, weight=ft.FontWeight.BOLD, color=TEXT),
                            ft.Row([ft.Icon(ft.Icons.IMAGE_OUTLINED, color=PRIMARY), ft.Column([ft.Text("Artwork studio", weight=ft.FontWeight.BOLD), ft.Text("Covers and game assets", size=12, color=MUTED)], spacing=2, expand=True), self.artwork_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            ft.Divider(color=BORDER, height=1),
                            ft.Row([ft.Icon(ft.Icons.FOLDER_COPY_OUTLINED, color=PRIMARY), ft.Column([ft.Text("OPL folder setup", weight=ft.FontWeight.BOLD), ft.Text("Prepare drive structure", size=12, color=MUTED)], spacing=2, expand=True), self.storage_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ])),
                    ],
                    spacing=16,
                    run_spacing=16,
                ),
            ],
        )

    def show_device(self, drive: dict | None) -> None:
        connected = bool(drive)
        if drive:
            self.device_title.value = str(drive["model"])
            self.device_details.value = f"{drive['letter']} • {drive['total_human']} • {drive['filesystem']} • {drive['free_human']} free"
        else:
            self.device_title.value = "No external storage selected"
            self.device_details.value = "Connect a USB flash drive or external HDD/SSD to begin."
        for button in (self.import_btn, self.library_btn, self.artwork_btn, self.storage_btn):
            button.disabled = not connected
