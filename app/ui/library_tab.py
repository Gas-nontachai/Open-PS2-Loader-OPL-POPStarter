from __future__ import annotations

from typing import Callable

import flet as ft


class LibraryTab(ft.Column):
    def __init__(self) -> None:
        self.scan_btn = ft.OutlinedButton("Refresh Library", icon=ft.Icons.REFRESH)
        self.empty = ft.Text("No games found. Import games or refresh the library.", color=ft.Colors.GREY_400)
        self.games = ft.Column(spacing=10)
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
            cover = str(game.get("cover_path") or "")
            thumbnail: ft.Control = ft.Image(src=cover, width=64, height=90, fit=ft.ImageFit.COVER) if cover else ft.Container(
                width=64, height=90, alignment=ft.alignment.center, bgcolor=ft.Colors.GREY_900, content=ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED_OUTLINED)
            )
            self.games.controls.append(
                ft.Container(
                    padding=12,
                    border=ft.border.all(1, ft.Colors.GREY_800),
                    border_radius=10,
                    content=ft.Row(
                        [
                            thumbnail,
                            ft.Column(
                                [
                                    ft.Text(str(game.get("game_name") or "Unknown game"), size=17, weight=ft.FontWeight.BOLD),
                                    ft.Text(f"{game.get('game_id') or 'Unknown ID'} • {game.get('target_folder')} • {game.get('size_human')}"),
                                    ft.Text("Ready", color=ft.Colors.GREEN_300),
                                ],
                                expand=True,
                            ),
                            ft.OutlinedButton("Artwork", icon=ft.Icons.IMAGE_OUTLINED, on_click=lambda _, g=game: on_artwork(g)),
                            ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_300, tooltip="Delete game", on_click=lambda _, g=game: on_delete(g)),
                        ],
                        wrap=True,
                    ),
                )
            )

    def update_storage(self, summary: dict) -> None:
        self.storage.value = f"{summary.get('count', 0)} games • {summary.get('games_human', '0 B')} • {summary.get('free_human', '0 B')} free"

    def set_loading(self) -> None:
        self.games.controls.clear()
        self.empty.value = "Checking storage and refreshing games…"
        self.empty.visible = True
        self.storage.value = "Please wait."
