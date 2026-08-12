from __future__ import annotations

from typing import Callable

import flet as ft


class LibraryTab(ft.Column):
    def __init__(self) -> None:
        self.scan_btn = ft.OutlinedButton("Refresh Library", icon=ft.Icons.REFRESH)
        self.empty = ft.Text("No games found. Import games or refresh the library.", color=ft.Colors.GREY_400)
        self.games = ft.Column(spacing=8)
        self.storage = ft.Text("Select external storage to view its game library.")
        super().__init__(
            expand=False,
            controls=[
                ft.Text("Game Library", size=28, weight=ft.FontWeight.BOLD),
                ft.Row([self.scan_btn, self.storage], wrap=True),
                self.empty,
                self.games,
            ],
        )

    def set_games(self, games: list[dict], on_delete: Callable[[dict], None], on_artwork: Callable[[dict], None]) -> None:
        self.games.controls.clear()
        self.empty.value = "No games found. Import games or refresh the library."
        self.empty.visible = not bool(games)
        for game in games:
            cover = str(game.get("cover_preview_path") or "")
            thumbnail_image: ft.Control = (
                ft.Image(src=cover, width=64, height=90, fit=ft.ImageFit.CONTAIN)
                if cover
                else ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED_OUTLINED, size=28, color=ft.Colors.GREY_600)
            )
            thumbnail = ft.Container(
                content=thumbnail_image,
                width=64,
                height=90,
                alignment=ft.alignment.center,
                bgcolor=ft.Colors.GREY_900,
                border_radius=6,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
            )
            game_info = ft.Column(
                [
                    ft.Text(
                        str(game.get("game_name") or "Unknown game"),
                        size=17,
                        weight=ft.FontWeight.BOLD,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text(
                        f"{game.get('game_id') or 'Unknown ID'} • {game.get('target_folder')} • {game.get('size_human')}",
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text("Ready", color=ft.Colors.GREEN_300),
                ],
                expand=True,
                spacing=3,
                tight=True,
            )
            self.games.controls.append(
                ft.Container(
                    height=116,
                    padding=10,
                    border=ft.border.all(1, ft.Colors.GREY_800),
                    border_radius=10,
                    content=ft.Row(
                        [
                            thumbnail,
                            game_info,
                            ft.IconButton(
                                icon=ft.Icons.IMAGE_OUTLINED,
                                tooltip="Manage artwork",
                                on_click=lambda _, selected=game: on_artwork(selected),
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE,
                                icon_color=ft.Colors.RED_300,
                                tooltip="Delete game",
                                on_click=lambda _, selected=game: on_delete(selected),
                            ),
                        ],
                        wrap=False,
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            )

    def update_storage(self, summary: dict) -> None:
        self.storage.value = (
            f"{summary.get('count', 0)} games • {summary.get('games_human', '0 B')} • "
            f"{summary.get('free_human', '0 B')} free"
        )

    def set_loading(self) -> None:
        self.games.controls.clear()
        self.empty.value = "Checking storage and refreshing games…"
        self.empty.visible = True
        self.storage.value = "Please wait."
