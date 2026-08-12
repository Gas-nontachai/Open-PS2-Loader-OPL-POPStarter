from __future__ import annotations

from pathlib import Path
from typing import Callable

import flet as ft


class ArtTab(ft.Column):
    def __init__(self, on_pick_manual_art: Callable[[str], None]) -> None:
        self.on_pick_manual_art = on_pick_manual_art
        self.on_game_selected: Callable[[dict], None] | None = None
        self._games: dict[str, dict] = {}
        self._new_art_path = ""

        self.game_dropdown = ft.Dropdown(label="Game", options=[], expand=True)
        self.game_dropdown.on_change = self._on_game_change
        self.empty_text = ft.Text("Scan your game library, then choose a game.", color=ft.Colors.GREY_400)
        self.current_preview = ft.Image(width=260, height=360, fit=ft.ImageFit.CONTAIN, visible=False)
        self.new_preview = ft.Image(width=260, height=360, fit=ft.ImageFit.CONTAIN, visible=False)
        self.current_placeholder = ft.Container(
            content=ft.Text("No current artwork", text_align=ft.TextAlign.CENTER),
            width=260,
            height=360,
            alignment=ft.alignment.center,
            bgcolor=ft.Colors.GREY_900,
            border_radius=12,
        )
        self.new_placeholder = ft.Container(
            content=ft.Text("Choose a PNG, JPG, JPEG, or WEBP image", text_align=ft.TextAlign.CENTER),
            width=260,
            height=360,
            alignment=ft.alignment.center,
            bgcolor=ft.Colors.GREY_900,
            border_radius=12,
        )
        self.choose_btn = ft.ElevatedButton("Choose Image", icon=ft.Icons.UPLOAD_FILE)
        self.choose_btn.on_click = lambda _: self.on_pick_manual_art("COV")
        self.save_btn = ft.FilledButton("Save Artwork", icon=ft.Icons.SAVE, disabled=True)
        self.remove_btn = ft.OutlinedButton("Remove Artwork", icon=ft.Icons.DELETE_OUTLINE, disabled=True)
        self.status_text = ft.Text("Select a game to manage its cover.")

        super().__init__(
            expand=False,
            spacing=18,
            controls=[
                ft.Text("Artwork", size=28, weight=ft.FontWeight.BOLD),
                ft.Text("Choose a game and upload its cover image manually."),
                self.game_dropdown,
                self.empty_text,
                ft.ResponsiveRow(
                    [
                        ft.Column([ft.Text("Current artwork", weight=ft.FontWeight.BOLD), ft.Stack([self.current_placeholder, self.current_preview])], col={"sm": 12, "md": 6}),
                        ft.Column([ft.Text("New artwork preview", weight=ft.FontWeight.BOLD), ft.Stack([self.new_placeholder, self.new_preview])], col={"sm": 12, "md": 6}),
                    ]
                ),
                ft.Row([self.choose_btn, self.save_btn, self.remove_btn], wrap=True),
                self.status_text,
            ],
        )

    def _on_game_change(self, _: ft.ControlEvent) -> None:
        self._refresh_game()

    def _refresh_game(self) -> None:
        game = self.selected_game()
        self._new_art_path = ""
        self.new_preview.visible = False
        self.new_placeholder.visible = True
        self.save_btn.disabled = True
        cover = str(game.get("cover_path") or "") if game else ""
        self.current_preview.src = cover
        self.current_preview.visible = bool(cover)
        self.current_placeholder.visible = not bool(cover)
        self.remove_btn.disabled = not bool(cover)
        self.status_text.value = "Choose an image to replace this cover." if game else "Select a game first."
        if self.on_game_selected and game:
            self.on_game_selected(game)
        self.update()

    def selected_game(self) -> dict:
        return self._games.get(str(self.game_dropdown.value or ""), {})

    def update_source_choices(self, games_list: list[dict]) -> None:
        self._games = {str(index): game for index, game in enumerate(games_list)}
        self.game_dropdown.options = [
            ft.dropdown.Option(key=key, text=f"{game.get('game_name', '-')} ({game.get('game_id', '-')})")
            for key, game in self._games.items()
        ]
        self.empty_text.visible = not bool(games_list)
        if games_list:
            self.game_dropdown.value = "0"
            self._refresh_game()

    def set_manual_file(self, art_type: str, path: str) -> None:
        if art_type != "COV":
            return
        self._new_art_path = path
        self.new_preview.src = path
        self.new_preview.visible = bool(path)
        self.new_placeholder.visible = not bool(path)
        self.save_btn.disabled = not bool(path) or not bool(self.selected_game())
        self.status_text.value = f"Ready to save {Path(path).name}." if path else "Choose an image."

    def collect_manual_files(self) -> dict[str, str]:
        return {"COV": self._new_art_path} if self._new_art_path else {}

    def refresh_selected_artwork(self, cover_path: str | None) -> None:
        self.current_preview.src = cover_path or ""
        self.current_preview.visible = bool(cover_path)
        self.current_placeholder.visible = not bool(cover_path)
        self.remove_btn.disabled = not bool(cover_path)
        self._new_art_path = ""
        self.new_preview.visible = False
        self.new_placeholder.visible = True
        self.save_btn.disabled = True

    def translate(self) -> None:
        # The simplified artwork workflow intentionally uses plain, beginner-friendly English.
        pass
