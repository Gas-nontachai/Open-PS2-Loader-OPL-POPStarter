from __future__ import annotations

from typing import Callable

import flet as ft
from app.ui.theme import DESTRUCTIVE

from app.core.i18n import t
from app.ui.theme import danger_style


def show_format_dialog(page: ft.Page, on_confirm: Callable[[str], None], device: dict) -> None:
    confirmation = "FORMAT"
    phrase = ft.TextField(label="Type FORMAT to format this storage", autofocus=True)
    label = ft.TextField(label=t("volume_label"), value="PS2USB")
    error_text = ft.Text("", color=DESTRUCTIVE)

    def do_confirm(_: ft.ControlEvent) -> None:
        if phrase.value != confirmation:
            error_text.value = f"Type {confirmation} exactly to continue."
            page.update()
            return
        page.close(dialog)
        on_confirm((label.value or "PS2USB").strip() or "PS2USB")

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(t("format_title")),
        content=ft.Column(
            [
                ft.Text(
                    "Format permanently erases this entire physical disk, including all partitions.",
                    color=DESTRUCTIVE,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Text(f"{device['model']} ({device['letter']}) | {device['total_human']}"),
                ft.Text(f"Physical identity: {device['device_id']}", selectable=True),
                ft.Text("DiskPart FAT32 can fail on some capacities. Type FORMAT exactly."),
                phrase,
                label,
                error_text,
            ],
            tight=True,
            width=460,
        ),
        actions=[
            ft.TextButton(t("cancel"), on_click=lambda _: page.close(dialog)),
            ft.OutlinedButton("Erase disk and format", on_click=do_confirm, style=danger_style(), disabled=True),
        ],
    )
    def check_phrase(_: ft.ControlEvent) -> None:
        dialog.actions[1].disabled = phrase.value != confirmation
        page.update()

    phrase.on_change = check_phrase
    page.open(dialog)


def show_delete_dialog(page: ft.Page, game: dict, on_confirm: Callable[[], None]) -> None:
    game_name = str(game.get("game_name") or "Unknown game")
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(f'Delete "{game_name}"?'),
        content=ft.Column(
            [
                ft.Text("This permanently removes the game files. Artwork and CFG are kept. There is no Undo."),
                ft.Text(f"Game ID: {game.get('game_id') or '-'}"),
                ft.Text(f"Size: {game.get('size_human') or '-'}"),
                ft.Text(f"File: {game.get('destination_filename') or '-'}"),
            ],
            tight=True,
        ),
        actions=[
            ft.TextButton(t("cancel"), on_click=lambda _: page.close(dialog)),
            ft.FilledButton(t("delete"), on_click=lambda _: (page.close(dialog), on_confirm()), style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700)),
        ],
    )
    page.open(dialog)


def show_artwork_remove_dialog(page: ft.Page, game_name: str, on_confirm: Callable[[], None]) -> None:
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Remove artwork?"),
        content=ft.Text(f'This removes the cover for "{game_name}" from the selected external storage.'),
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: page.close(dialog)),
            ft.FilledButton(
                "Remove",
                on_click=lambda _: (page.close(dialog), on_confirm()),
                style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700),
            ),
        ],
    )
    page.open(dialog)


def show_snackbar(page: ft.Page, message: str, is_error: bool = False) -> None:
    page.snack_bar = ft.SnackBar(
        content=ft.Text(message),
        bgcolor=ft.Colors.RED_700 if is_error else ft.Colors.GREEN_700,
        open=True,
    )
    page.update()


def show_update_banner(page: ft.Page, release: dict[str, str]) -> None:
    from app.core.constants import APP_VERSION
    from app.core.i18n import get_lang

    thai = get_lang() == "th"
    message = (
        f"มีเวอร์ชันใหม่ {release['version']} (ปัจจุบัน {APP_VERSION}) แนะนำให้อัปเดต"
        if thai else
        f"Version {release['version']} is available (installed: {APP_VERSION}). We recommend updating."
    )
    banner = ft.Banner(
        leading=ft.Icon(ft.Icons.SYSTEM_UPDATE),
        content=ft.Text(message),
        actions=[
            ft.TextButton("ดาวน์โหลด" if thai else "Download", on_click=lambda _: page.launch_url(release["url"])),
            ft.TextButton("ไว้ภายหลัง" if thai else "Later", on_click=lambda _: page.close(banner)),
        ],
    )
    page.open(banner)
