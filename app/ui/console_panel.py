from __future__ import annotations

import flet as ft

from app.core.i18n import t
from app.ui.state import AppState, PROGRESS_MAP


STATE_COLORS = {
    AppState.IDLE: ft.Colors.GREY_700,
    AppState.VALIDATING: ft.Colors.BLUE_700,
    AppState.VALIDATED: ft.Colors.CYAN_700,
    AppState.FORMATTING: ft.Colors.AMBER_700,
    AppState.IMPORTING: ft.Colors.INDIGO_700,
    AppState.ARTING: ft.Colors.PURPLE_700,
    AppState.COMPLETED: ft.Colors.GREEN_700,
    AppState.FAILED: ft.Colors.RED_700,
    AppState.CANCELLED: ft.Colors.ORANGE_700,
}

LOG_ICONS = {
    "info": (ft.Icons.INFO_OUTLINED, ft.Colors.BLUE_300),
    "success": (ft.Icons.CHECK_CIRCLE_OUTLINE, ft.Colors.GREEN_300),
    "error": (ft.Icons.ERROR_OUTLINE, ft.Colors.RED_300),
}


class ConsolePanel(ft.Column):
    def __init__(self) -> None:
        self.state_text = ft.Text(t("idle"), color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)
        self.state_pill = ft.Container(
            content=self.state_text,
            bgcolor=STATE_COLORS[AppState.IDLE],
            border_radius=20,
            padding=ft.padding.symmetric(horizontal=12, vertical=6),
        )
        self.status_text = ft.Text(t("status_ready"))
        self.progress = ft.ProgressBar(value=0.0, color=ft.Colors.CYAN)
        self.log_list = ft.ListView(expand=True, spacing=4, auto_scroll=True)
        super().__init__(
            expand=True,
            spacing=10,
            controls=[
                ft.Row([ft.Text(t("status"), weight=ft.FontWeight.BOLD), self.state_pill]),
                self.status_text,
                self.progress,
                ft.Divider(),
                ft.Text(t("log"), weight=ft.FontWeight.BOLD),
                self.log_list,
            ],
        )

    def set_state(self, state_enum: AppState) -> None:
        self.state_text.value = t(state_enum.value.lower())
        self.state_pill.bgcolor = STATE_COLORS.get(state_enum, ft.Colors.GREY_700)
        self.progress.value = PROGRESS_MAP.get(state_enum, 0.0)

    def set_status(self, message: str) -> None:
        self.status_text.value = message

    def set_progress(self, value: float) -> None:
        self.progress.value = max(0.0, min(1.0, value))

    def append_log(self, status: str, message: str) -> None:
        icon_name, color = LOG_ICONS.get(status, LOG_ICONS["info"])
        self.log_list.controls.append(
            ft.ListTile(
                dense=True,
                leading=ft.Icon(icon_name, color=color, size=16),
                title=ft.Text(message, size=12),
            )
        )
        if len(self.log_list.controls) > 200:
            self.log_list.controls = self.log_list.controls[-200:]

    def clear_log(self) -> None:
        self.log_list.controls.clear()
