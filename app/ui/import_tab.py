from __future__ import annotations

from typing import Callable

import flet as ft

from app.core.i18n import t


class ImportTab(ft.Column):
    def __init__(self, page: ft.Page, on_pick_folder: Callable[[], None], on_pick_isos: Callable[[], None]) -> None:
        self.page = page
        self.on_pick_folder = on_pick_folder
        self.on_pick_isos = on_pick_isos

        self.target_path = ft.TextField(label=t("target_path"), hint_text=t("target_hint"), expand=True)
        self.pick_folder_btn = ft.ElevatedButton(t("pick_folder"), on_click=lambda _: self.on_pick_folder())

        self.validate_btn = ft.ElevatedButton(t("validate_target"), bgcolor=ft.Colors.CYAN_700)
        self.format_btn = ft.ElevatedButton(t("format_usb"), bgcolor=ft.Colors.AMBER_700)
        self.cancel_btn = ft.ElevatedButton(t("cancel"), bgcolor=ft.Colors.RED_700, disabled=True)

        self.pick_iso_btn = ft.ElevatedButton(t("pick_iso"), on_click=lambda _: self.on_pick_isos())
        self.selected_iso_text = ft.Text(t("no_selection"))
        self.overwrite_checkbox = ft.Checkbox(label=t("overwrite"), value=True)
        self.import_btn = ft.ElevatedButton(t("import_prepare"), bgcolor=ft.Colors.GREEN_700)

        self.scan_btn = ft.ElevatedButton(t("scan_games"), bgcolor=ft.Colors.INDIGO_700)
        self.games_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text(t("col_game_id"))),
                ft.DataColumn(ft.Text(t("col_game_name"))),
                ft.DataColumn(ft.Text(t("col_file"))),
                ft.DataColumn(ft.Text(t("col_folder"))),
                ft.DataColumn(ft.Text(t("col_size"))),
                ft.DataColumn(ft.Text(t("col_art"))),
                ft.DataColumn(ft.Text(t("col_actions"))),
            ],
            rows=[],
            expand=True,
            column_spacing=14,
        )

        self.stat_games = ft.Text("0")
        self.stat_games_size = ft.Text("0 B")
        self.stat_used = ft.Text("0 B")
        self.stat_free = ft.Text("0 B")
        self.storage_meter = ft.ProgressBar(value=0, color=ft.Colors.CYAN)
        self.storage_text = ft.Text("0%")

        self.iso_section = ft.Column(
            visible=False,
            controls=[
                ft.Row([self.pick_iso_btn, self.import_btn]),
                self.overwrite_checkbox,
                self.selected_iso_text,
            ],
        )

        self.games_section = ft.Column(
            visible=False,
            controls=[
                self.scan_btn,
                ft.Container(self.games_table, expand=True),
                ft.Row(
                    [
                        ft.Column([ft.Text(t("games")), self.stat_games]),
                        ft.Column([ft.Text(t("games_size")), self.stat_games_size]),
                        ft.Column([ft.Text(t("used_space")), self.stat_used]),
                        ft.Column([ft.Text(t("free_space")), self.stat_free]),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                self.storage_meter,
                self.storage_text,
            ],
        )

        super().__init__(
            expand=True,
            spacing=12,
            controls=[
                ft.Row([self.target_path, self.pick_folder_btn]),
                ft.Row([self.validate_btn, self.format_btn, self.cancel_btn]),
                self.iso_section,
                self.games_section,
            ],
        )

        self.selected_isos: list[str] = []
        self._interactive_controls: list[ft.Control] = [
            self.target_path,
            self.pick_folder_btn,
            self.validate_btn,
            self.format_btn,
            self.pick_iso_btn,
            self.overwrite_checkbox,
            self.import_btn,
            self.scan_btn,
        ]

    def set_selected_isos(self, paths: list[str]) -> None:
        self.selected_isos = paths
        if not paths:
            self.selected_iso_text.value = t("no_selection")
            return
        names = ", ".join([p.split("/")[-1] for p in paths[:3]])
        if len(paths) > 3:
            names = f"{names} ..."
        self.selected_iso_text.value = f"{t('selected_files')}: {len(paths)} ({names})"

    def set_games(self, games: list[dict], on_delete: Callable[[dict], None]) -> None:
        rows: list[ft.DataRow] = []
        for game in games:
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(game.get("game_id") or "-"))),
                        ft.DataCell(ft.Text(str(game.get("game_name") or "-"))),
                        ft.DataCell(ft.Text(str(game.get("destination_filename") or "-"))),
                        ft.DataCell(ft.Text(str(game.get("target_folder") or "-"))),
                        ft.DataCell(ft.Text(str(game.get("size_human") or "-"))),
                        ft.DataCell(ft.Text(str(game.get("art_count") or 0))),
                        ft.DataCell(ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_300, on_click=lambda _, g=game: on_delete(g))),
                    ]
                )
            )
        self.games_table.rows = rows

    def update_storage(self, summary_dict: dict) -> None:
        self.stat_games.value = str(summary_dict.get("count", 0))
        self.stat_games_size.value = str(summary_dict.get("games_human", "0 B"))
        self.stat_used.value = str(summary_dict.get("used_human", "0 B"))
        self.stat_free.value = str(summary_dict.get("free_human", "0 B"))
        percent = float(summary_dict.get("used_percent", 0.0))
        self.storage_meter.value = max(0.0, min(1.0, percent / 100.0))
        self.storage_text.value = f"{t('storage_usage')}: {percent:.2f}%"

    def set_controls_enabled(self, enabled: bool) -> None:
        for control in self._interactive_controls:
            control.disabled = not enabled
        self.cancel_btn.disabled = enabled

    def reveal_post_validation(self) -> None:
        self.iso_section.visible = True
        self.games_section.visible = True

    def translate(self) -> None:
        self.target_path.label = t("target_path")
        self.target_path.hint_text = t("target_hint")
        self.pick_folder_btn.text = t("pick_folder")
        self.validate_btn.text = t("validate_target")
        self.format_btn.text = t("format_usb")
        self.cancel_btn.text = t("cancel")
        self.pick_iso_btn.text = t("pick_iso")
        self.overwrite_checkbox.label = t("overwrite")
        self.import_btn.text = t("import_prepare")
        self.scan_btn.text = t("scan_games")
