from __future__ import annotations

from typing import Callable

import flet as ft

from app.core.i18n import t


def show_format_dialog(page: ft.Page, on_confirm: Callable[[str], None]) -> None:
    phrase = ft.TextField(label=t("format_phrase"), autofocus=True)
    label = ft.TextField(label=t("volume_label"), value="PS2USB")
    error_text = ft.Text("", color=ft.Colors.RED_300)

    def do_confirm(_: ft.ControlEvent) -> None:
        if phrase.value.strip().upper() != "FORMAT":
            error_text.value = "FORMAT required"
            page.update()
            return
        page.dialog.open = False
        page.update()
        on_confirm((label.value or "PS2USB").strip() or "PS2USB")

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(t("format_title")),
        content=ft.Column([phrase, label, error_text], tight=True, width=420),
        actions=[
            ft.TextButton(t("cancel"), on_click=lambda _: _close_dialog(page)),
            ft.FilledButton(t("confirm"), on_click=do_confirm),
        ],
    )
    page.dialog = dialog
    dialog.open = True
    page.update()


def show_delete_dialog(page: ft.Page, game_name: str, on_confirm: Callable[[], None]) -> None:
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(t("delete_title")),
        content=ft.Text(f"{t('delete_message')}: {game_name}"),
        actions=[
            ft.TextButton(t("cancel"), on_click=lambda _: _close_dialog(page)),
            ft.FilledButton(t("delete"), on_click=lambda _: _confirm_then_close(page, on_confirm), style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700)),
        ],
    )
    page.dialog = dialog
    dialog.open = True
    page.update()


def show_snackbar(page: ft.Page, message: str, is_error: bool = False) -> None:
    page.snack_bar = ft.SnackBar(
        content=ft.Text(message),
        bgcolor=ft.Colors.RED_700 if is_error else ft.Colors.GREEN_700,
        open=True,
    )
    page.update()


def _close_dialog(page: ft.Page) -> None:
    if page.dialog:
        page.dialog.open = False
        page.update()


def _confirm_then_close(page: ft.Page, on_confirm: Callable[[], None]) -> None:
    _close_dialog(page)
    on_confirm()
