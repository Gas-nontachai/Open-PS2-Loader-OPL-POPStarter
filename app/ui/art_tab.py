from __future__ import annotations

from pathlib import Path
from typing import Callable

import flet as ft

from app.core.constants import ART_TYPES
from app.core.i18n import t


class ArtTab(ft.Column):
    def __init__(self, on_pick_manual_art: Callable[[str], None]) -> None:
        self.on_pick_manual_art = on_pick_manual_art

        self.mode_dropdown = ft.Dropdown(
            label=t("mode"),
            value="auto",
            options=[
                ft.dropdown.Option("manual", t("mode_manual")),
                ft.dropdown.Option("auto", t("mode_auto")),
            ],
        )

        self.game_name = ft.TextField(label=t("game_name"))
        self.game_dropdown = ft.Dropdown(label=t("source_game"), options=[])
        self.iso_filename = ft.TextField(label=t("iso_filename"))
        self.generated_game_id = ft.Text(f"{t('generated_game_id')}: -")

        self.manual_files: dict[str, str] = {k: "" for k in ART_TYPES}
        self.manual_filename_texts: dict[str, ft.Text] = {}
        manual_rows: list[ft.Control] = []
        for art_type in ART_TYPES:
            name_text = ft.Text("-")
            self.manual_filename_texts[art_type] = name_text
            manual_rows.append(
                ft.Row(
                    [
                        ft.Text(art_type, width=50),
                        ft.ElevatedButton(t("pick_file"), on_click=lambda _, at=art_type: self.on_pick_manual_art(at)),
                        name_text,
                    ]
                )
            )
        self.manual_upload_btn = ft.ElevatedButton(t("manual_upload"), bgcolor=ft.Colors.CYAN_700)
        self.manual_block = ft.Column(controls=[*manual_rows, self.manual_upload_btn], visible=False)

        self.search_btn = ft.ElevatedButton(t("search_art"), bgcolor=ft.Colors.INDIGO_700)
        self.save_auto_btn = ft.ElevatedButton(t("save_selected_art"), bgcolor=ft.Colors.GREEN_700)
        self.candidate_grid = ft.GridView(
            expand=True,
            max_extent=280,
            spacing=10,
            run_spacing=10,
            child_aspect_ratio=0.78,
        )
        self.candidate_cards: list[dict] = []
        self.auto_block = ft.Column(
            expand=True,
            controls=[ft.Row([self.search_btn, self.save_auto_btn], wrap=True), self.candidate_grid],
            visible=True,
        )

        self.mode_dropdown.on_change = self._on_mode_change
        self.game_dropdown.on_change = self._on_game_change

        super().__init__(
            expand=True,
            spacing=10,
            controls=[
                self.mode_dropdown,
                self.game_name,
                self.game_dropdown,
                self.iso_filename,
                self.generated_game_id,
                self.manual_block,
                self.auto_block,
            ],
        )

    def _on_mode_change(self, _: ft.ControlEvent) -> None:
        is_manual = self.mode_dropdown.value == "manual"
        self.manual_block.visible = is_manual
        self.auto_block.visible = not is_manual
        self.update()

    def _on_game_change(self, _: ft.ControlEvent) -> None:
        value = self.game_dropdown.value or ""
        if not value:
            return
        try:
            game_id, game_name, dest_name = value.split("|", 2)
        except ValueError:
            return
        self.generated_game_id.value = f"{t('generated_game_id')}: {game_id or '-'}"
        self.game_name.value = game_name
        self.iso_filename.value = dest_name
        self.update()

    def update_source_choices(self, games_list: list[dict]) -> None:
        self.game_dropdown.options = [
            ft.dropdown.Option(
                key=f"{g.get('game_id','')}|{g.get('game_name','')}|{g.get('destination_filename','')}",
                text=f"{g.get('game_name', '-') } ({g.get('game_id', '-')})",
            )
            for g in games_list
        ]

    def set_manual_file(self, art_type: str, path: str) -> None:
        self.manual_files[art_type] = path
        self.manual_filename_texts[art_type].value = Path(path).name if path else "-"

    def render_candidates(self, candidates_list: list[dict]) -> None:
        self.candidate_grid.controls.clear()
        self.candidate_cards = []
        if not candidates_list:
            self.candidate_grid.controls.append(ft.Text(t("candidate_empty")))
            self.update()
            return

        for cand in candidates_list:
            checkbox = ft.Checkbox(value=True)
            type_dropdown = ft.Dropdown(
                value="COV",
                options=[ft.dropdown.Option(x) for x in ART_TYPES],
                width=120,
            )
            self.candidate_cards.append({"candidate": cand, "check": checkbox, "type": type_dropdown})
            self.candidate_grid.controls.append(
                ft.Card(
                    content=ft.Container(
                        padding=8,
                        content=ft.Column(
                            [
                                ft.Image(
                                    src=cand.get("thumbnail_url") or cand.get("image_url"),
                                    height=140,
                                    fit=ft.ImageFit.COVER,
                                    border_radius=8,
                                ),
                                ft.Text(cand.get("title", "-"), max_lines=2),
                                checkbox,
                                type_dropdown,
                            ]
                        ),
                    )
                )
            )
        self.update()

    def collect_auto_selections(self) -> list[dict]:
        selections: list[dict] = []
        for card in self.candidate_cards:
            if card["check"].value:
                selections.append(
                    {
                        "art_type": card["type"].value,
                        "image_url": card["candidate"].get("image_url"),
                    }
                )
        return selections

    def collect_manual_files(self) -> dict[str, str]:
        return {k: v for k, v in self.manual_files.items() if v}

    def translate(self) -> None:
        self.mode_dropdown.label = t("mode")
        self.mode_dropdown.options = [
            ft.dropdown.Option("manual", t("mode_manual")),
            ft.dropdown.Option("auto", t("mode_auto")),
        ]
        self.game_name.label = t("game_name")
        self.game_dropdown.label = t("source_game")
        self.iso_filename.label = t("iso_filename")
        self.manual_upload_btn.text = t("manual_upload")
        self.search_btn.text = t("search_art")
        self.save_auto_btn.text = t("save_selected_art")
        self.generated_game_id.value = f"{t('generated_game_id')}: -"
