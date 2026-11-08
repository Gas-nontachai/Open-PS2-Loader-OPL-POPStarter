from __future__ import annotations

from pathlib import Path
from PIL import Image, UnidentifiedImageError
from app.ui.theme import danger_style, heading
from typing import Callable

import flet as ft
from app.ui.theme import SURFACE, MUTED, BORDER, PRIMARY, SUCCESS, WARNING

from app.services.art_service import ARTWORK_SPECS


class ArtTab(ft.Column):
    """Compact single-screen artwork workspace with bounded previews."""

    def __init__(self, on_pick_manual_art: Callable[[str], None]) -> None:
        self.on_pick_manual_art = on_pick_manual_art
        self.on_game_selected: Callable[[dict], None] | None = None
        self._games: dict[str, dict] = {}
        self._all_games: list[dict] = []
        self._new_art_path = ""
        self._status: dict = {}
        self._busy = False

        self.search = ft.TextField(label="Search games", prefix_icon=ft.Icons.SEARCH, dense=True, on_change=self._filter_games)
        self.game_dropdown = ft.Dropdown(label="Game", options=[], dense=True, on_change=self._on_game_change)
        self.empty_text = ft.Text("No games found. Import or refresh first.", size=12, color=MUTED)
        self.selected_title = ft.Text("No game selected", size=18, weight=ft.FontWeight.BOLD, max_lines=2)
        self.selected_id = ft.Text("Game ID unavailable", size=12, color=PRIMARY)

        self.download_btn = ft.FilledButton("Download Missing", icon=ft.Icons.CLOUD_DOWNLOAD)
        self.replace_online_btn = ft.OutlinedButton("Replace Online", icon=ft.Icons.SYNC)
        self.refresh_btn = ft.IconButton(icon=ft.Icons.REFRESH, tooltip="Refresh artwork")
        self.batch_btn = ft.OutlinedButton("All Games", icon=ft.Icons.DOWNLOAD_FOR_OFFLINE)
        self.cancel_batch_btn = ft.TextButton("Cancel", icon=ft.Icons.CANCEL, visible=False)

        self.type_dropdown = ft.Dropdown(
            label="Artwork type",
            value="COV",
            dense=True,
            options=[ft.dropdown.Option(key=key, text=str(spec["label"])) for key, spec in ARTWORK_SPECS.items()],
            on_change=self._on_type_change,
        )
        self.asset_dropdown = ft.Dropdown(label="Image to remove", dense=True, visible=False, options=[])
        self.new_preview = ft.Image(width=150, height=105, fit=ft.ImageFit.CONTAIN, visible=False)
        self.new_placeholder = ft.Container(
            content=ft.Icon(ft.Icons.ADD_PHOTO_ALTERNATE_OUTLINED, color=MUTED),
            width=150,
            height=105,
            alignment=ft.alignment.center,
            bgcolor=SURFACE,
            border_radius=8,
        )
        self.choose_btn = ft.ElevatedButton("Choose Image", icon=ft.Icons.UPLOAD_FILE, on_click=self._pick_selected_type)
        self.save_btn = ft.FilledButton("Save", icon=ft.Icons.SAVE, disabled=True)
        self.remove_btn = ft.OutlinedButton("Remove", icon=ft.Icons.DELETE_OUTLINE, disabled=True, style=danger_style())
        self.status_text = ft.Text("Select a game to see available and missing artwork.", size=12)
        self.artwork_grid = ft.ResponsiveRow(spacing=8, run_spacing=8)

        sidebar = ft.Container(
            width=285,
            padding=12,
            border=ft.border.all(1, BORDER),
            border_radius=12,
            content=ft.Column(
                [
                    ft.Text("Game", weight=ft.FontWeight.BOLD),
                    self.search,
                    self.game_dropdown,
                    self.empty_text,
                    self.selected_title,
                    self.selected_id,
                    ft.Divider(height=12),
                    ft.Text("Manual artwork", weight=ft.FontWeight.BOLD),
                    self.type_dropdown,
                    self.asset_dropdown,
                    ft.Container(content=ft.Stack([self.new_placeholder, self.new_preview]), alignment=ft.alignment.center),
                    ft.Row([self.choose_btn, self.save_btn], wrap=True, spacing=6),
                    self.remove_btn,
                ],
                spacing=8,
                scroll=ft.ScrollMode.AUTO,
            ),
        )
        main_panel = ft.Column(
            [
                ft.Row([self.download_btn, self.replace_online_btn, self.batch_btn, self.refresh_btn, self.cancel_batch_btn], wrap=True, spacing=6),
                self.status_text,
                self.artwork_grid,
            ],
            expand=True,
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
        )
        super().__init__(
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            expand=True,
            spacing=8,
            controls=[
                ft.Row(
                    [
                        heading("Artwork"),
                        ft.Text("Matched by PS2 Game ID • no API key", size=12, color=MUTED),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    wrap=True,
                ),
                ft.Row([sidebar, main_panel], expand=True, vertical_alignment=ft.CrossAxisAlignment.START),
            ],
        )
        self._render_cards()
        self.set_busy(False)

    def _pick_selected_type(self, _: ft.ControlEvent) -> None:
        self.on_pick_manual_art(str(self.type_dropdown.value or "COV"))

    def _on_type_change(self, _: ft.ControlEvent) -> None:
        self._new_art_path = ""
        self.new_preview.visible = False
        self.new_placeholder.visible = True
        self.save_btn.disabled = True
        self._update_selected_assets()
        self._render_cards()
        self.update()

    def _select_type(self, art_type: str) -> None:
        self.type_dropdown.value = art_type
        self._update_selected_assets()
        self._render_cards()
        self.update()

    def _filter_games(self, _: ft.ControlEvent) -> None:
        query = str(self.search.value or "").strip().lower()
        current_path = str(self.selected_game().get("path") or "")
        filtered = [game for game in self._all_games if query in str(game.get("game_name") or "").lower() or query in str(game.get("game_id") or "").lower()]
        self._set_dropdown_games(filtered)
        for key, game in self._games.items():
            if str(game.get("path") or "") == current_path:
                self.game_dropdown.value = key
                break
        self._refresh_game()

    def _set_dropdown_games(self, games: list[dict]) -> None:
        self._games = {str(index): game for index, game in enumerate(games)}
        self.game_dropdown.options = [ft.dropdown.Option(key=key, text=f"{game.get('game_name', '-')} • {game.get('game_id', '-')}") for key, game in self._games.items()]
        self.empty_text.visible = not bool(games)
        if not games:
            self.game_dropdown.value = None
        if games and self.game_dropdown.value not in self._games:
            self.game_dropdown.value = "0"

    def _on_game_change(self, _: ft.ControlEvent) -> None:
        self._refresh_game()

    def _refresh_game(self) -> None:
        game = self.selected_game()
        self.refresh_selected_artwork()
        self.selected_title.value = str(game.get("game_name") or "No game selected")
        self.selected_id.value = str(game.get("game_id") or "Game ID unavailable")
        self.status_text.value = "Refreshing artwork…" if game else "Select a game first."
        self._status = {}
        self._render_cards()
        if self.on_game_selected and game:
            self.on_game_selected(game)
        self.update()

    def selected_game(self) -> dict:
        return self._games.get(str(self.game_dropdown.value or ""), {})

    def update_source_choices(self, games_list: list[dict]) -> None:
        current_path = str(self.selected_game().get("path") or "")
        self._all_games = list(games_list)
        self._set_dropdown_games(self._all_games)
        for key, game in self._games.items():
            if current_path and str(game.get("path") or "") == current_path:
                self.game_dropdown.value = key
                break
        if games_list:
            self._refresh_game()
        else:
            self._status = {}
            self.selected_title.value = "No game selected"
            self.selected_id.value = "Game ID unavailable"
            self.refresh_selected_artwork()
            self._render_cards()

    def set_artwork_status(self, result: dict) -> None:
        if result.get("status") == "success":
            self._status = dict(result.get("details", {}).get("types", {}))
            missing = sum(1 for item in self._status.values() if item.get("status") == "Missing")
            self.status_text.value = f"{missing} type(s) missing • choose an artwork type to upload or remove" if missing else "Artwork complete • choose an artwork type to manage it"
        else:
            self.status_text.value = str(result.get("message") or "Artwork could not be refreshed.")
        self._update_selected_assets()
        self._render_cards()

    def _update_selected_assets(self) -> None:
        art_type = str(self.type_dropdown.value or "COV")
        files = list(self._status.get(art_type, {}).get("files", []))
        self.asset_dropdown.options = [ft.dropdown.Option(key=str(item.get("name") or ""), text=str(item.get("name") or "")) for item in files]
        self.asset_dropdown.value = str(files[0].get("name") or "") if files else None
        self.asset_dropdown.visible = art_type == "SCR" and len(files) > 1
        self.remove_btn.disabled = not bool(files)

    def selected_filename(self) -> str | None:
        return str(self.asset_dropdown.value or "") or None

    def _render_cards(self) -> None:
        cards: list[ft.Control] = []
        selected_type = str(self.type_dropdown.value or "COV")
        for art_type, spec in ARTWORK_SPECS.items():
            status = self._status.get(art_type, {})
            files = list(status.get("files", []))
            preview_path = str(files[0].get("preview_path") or files[0].get("path") or "") if files else ""
            state = str(status.get("status") or "Missing")
            preview: ft.Control = ft.Image(src=preview_path, width=135, height=82, fit=ft.ImageFit.CONTAIN) if preview_path else ft.Container(
                content=ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED_OUTLINED, size=28, color=MUTED),
                width=135,
                height=82,
                alignment=ft.alignment.center,
                bgcolor=SURFACE,
                border_radius=6,
            )
            count_text = f"{len(files)} images" if bool(spec["multiple"]) else state
            color = SUCCESS if state in {"Available", "Custom", "Downloaded"} else WARNING
            cards.append(
                ft.Container(
                    col={"sm": 6, "md": 4, "lg": 3},
                    height=148,
                    padding=8,
                    border=ft.border.all(2 if art_type == selected_type else 1, PRIMARY if art_type == selected_type else BORDER),
                    border_radius=10,
                    content=ft.Column(
                        [ft.Text(str(spec["label"]), weight=ft.FontWeight.BOLD, size=13), preview, ft.Text(count_text, color=color, size=11)],
                        spacing=4,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            )
        self.artwork_grid.controls = cards
        self._update_selected_assets()
        self.set_busy(self._busy)

    def set_manual_file(self, art_type: str, path: str) -> None:
        try:
            source = Path(path)
            if source.stat().st_size > 20 * 1024 * 1024:
                raise ValueError("Choose an image no larger than 20 MiB.")
            with Image.open(source) as image:
                image.verify()
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
            self.refresh_selected_artwork()
            self.status_text.value = f"Image rejected: {exc}"
            return
        self.type_dropdown.value = art_type
        self._new_art_path = path
        self.new_preview.src = path
        self.new_preview.visible = bool(path)
        self.new_placeholder.visible = not bool(path)
        self.save_btn.disabled = not bool(path) or not bool(self.selected_game())
        self.status_text.value = f"Preview ready: {Path(path).name}. Click Save when it looks right." if path else "Choose an image."
        self._render_cards()

    def collect_manual_files(self) -> dict[str, str]:
        return {str(self.type_dropdown.value or "COV"): self._new_art_path} if self._new_art_path else {}

    def refresh_selected_artwork(self, cover_path: str | None = None) -> None:
        self._new_art_path = ""
        self.new_preview.visible = False
        self.new_placeholder.visible = True
        self.save_btn.disabled = True

    def set_busy(self, busy: bool, batch: bool = False) -> None:
        self._busy = busy
        game_selected = bool(self.selected_game())
        for control in (self.search, self.game_dropdown, self.type_dropdown, self.asset_dropdown):
            control.disabled = busy
        self.download_btn.disabled = self.replace_online_btn.disabled = self.choose_btn.disabled = busy or not game_selected
        self.batch_btn.disabled = busy or not bool(self._all_games)
        self.refresh_btn.disabled = busy or not game_selected
        self.remove_btn.disabled = busy or not bool(self._status.get(str(self.type_dropdown.value), {}).get("files"))
        self.save_btn.disabled = busy or not game_selected or not bool(self._new_art_path)
        self.cancel_batch_btn.visible = busy

    def translate(self) -> None:
        pass
