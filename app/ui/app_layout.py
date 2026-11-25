from __future__ import annotations

import asyncio
import threading
import os
from dataclasses import asdict
from pathlib import Path
from typing import Callable

import flet as ft

from app.controllers import art_controller, game_controller, import_controller
from app.core import config as config_service, i18n
from app.core.constants import APP_NAME, APP_VERSION, REQUIRED_FOLDERS
from app.core.paths import app_resource_path
from app.services import drive_service, target_service, update_service
from app.ui import dialogs
from app.ui.theme import app_theme, BACKGROUND, SURFACE, PRIMARY, PRIMARY_SOFT, TEXT, MUTED, BORDER, SUCCESS, heading, danger_style, page_header, panel
from app.ui.device_selection import retained_device
from app.ui.art_tab import ArtTab
from app.ui.home_page import HomePage
from app.ui.import_tab import ImportTab
from app.ui.library_tab import LibraryTab
from app.ui.state import AppState, AppStore
from app.ui.storage_page import StoragePage
from app.ui.workspace_tab import WorkspaceTab


def build_app(page: ft.Page, screenshot_page: str | None = None) -> None:
    page.title = APP_NAME
    page.window.icon = str(app_resource_path("assets/app_icon.png"))
    page.window.width = 1240
    page.window.height = 820
    page.window.min_width = 820
    page.window.min_height = 620
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = app_theme()
    page.bgcolor = BACKGROUND
    page.padding = 0

    store = AppStore()
    app_config = config_service.load_config()
    available_devices: dict[str, dict] = {}
    active_page = {"name": "home"}
    device_refresh = {"running": False, "requested_page": ""}
    pending_art_type = {"value": "COV"}
    auto_art_pending = {"value": False}

    iso_picker = ft.FilePicker()
    art_picker = ft.FilePicker()
    page.overlay.extend([iso_picker, art_picker])

    home = HomePage()
    import_page = ImportTab(page, on_pick_isos=lambda: iso_picker.pick_files(allow_multiple=True, allowed_extensions=["iso"]))
    library = LibraryTab()
    def pick_manual_art(art_type: str) -> None:
        pending_art_type["value"] = art_type
        art_picker.pick_files(allow_multiple=False, allowed_extensions=["png", "jpg", "jpeg", "webp"])

    artwork = ArtTab(on_pick_manual_art=pick_manual_art)
    storage = StoragePage()
    library_and_artwork = ft.Tabs(
        selected_index=0,
        animation_duration=180,
        expand=True,
        tabs=[
            WorkspaceTab(
                text="Game Files",
                icon=ft.Icons.SPORTS_ESPORTS,
                content=ft.Column([library], expand=True, scroll=ft.ScrollMode.AUTO),
            ),
            WorkspaceTab(text="Artwork", icon=ft.Icons.IMAGE_OUTLINED, content=artwork),
        ],
    )
    status_text = ft.Text("No external storage selected", expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
    activity_text = ft.Text("", size=12, weight=ft.FontWeight.BOLD, color=PRIMARY, visible=False, max_lines=1)
    activity_spinner = ft.ProgressRing(width=15, height=15, stroke_width=2, color=PRIMARY, visible=False)
    activity_progress = ft.ProgressBar(value=None, height=2, visible=False)
    cancel_operation_btn = ft.TextButton("Cancel", icon=ft.Icons.CANCEL_OUTLINED, visible=False)
    status_bar = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [ft.Icon(ft.Icons.USB, size=17, color=PRIMARY), status_text, ft.Container(expand=True), activity_spinner, activity_text, cancel_operation_btn],
                    spacing=9,
                ),
                activity_progress,
            ],
            spacing=5,
        ),
        padding=ft.padding.symmetric(horizontal=22, vertical=8),
        bgcolor=SURFACE,
        border=ft.border.only(top=ft.BorderSide(1, BORDER)),
    )

    settings_language = ft.Text("English")
    auto_artwork_checkbox = ft.Checkbox(
        label="Automatically download missing artwork after importing games",
        value=app_config.auto_download_artwork,
    )
    settings_toggle = ft.OutlinedButton("ไทย", icon=ft.Icons.LANGUAGE)
    settings = ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=16,
        controls=[
            page_header("Settings", "Tune the way PS2 TOOLKIT works on this PC."),
            panel([
                ft.Text("Language", size=18, weight=ft.FontWeight.BOLD),
                settings_language,
                settings_toggle,
            ]),
            panel([
                ft.Text("Artwork downloads", size=18, weight=ft.FontWeight.BOLD),
                auto_artwork_checkbox,
                ft.Text("Artwork matches by PS2 Game ID. No API key is required.", color=MUTED),
            ]),
            panel([
                ft.Text(APP_NAME, size=20, weight=ft.FontWeight.BOLD),
                ft.Text(f"Version {APP_VERSION}"),
                ft.Text("USB, import, library and manual artwork work offline. Artwork downloads and release checks require internet.", color=MUTED),
            ]),
        ],
    )

    content = ft.Container(expand=True, padding=ft.padding.symmetric(horizontal=32, vertical=28), content=home)
    nav_names = {
        "home": ("Home", "หน้าหลัก"),
        "import": ("Import Games", "นำเข้าเกม"),
        "library": ("Games & Artwork", "เกมและภาพปก"),
        "storage": ("USB / Storage", "USB / ที่เก็บข้อมูล"),
        "settings": ("Settings", "ตั้งค่า"),
    }
    nav_icons = {
        "home": ft.Icons.HOME_OUTLINED,
        "import": ft.Icons.DOWNLOAD,
        "library": ft.Icons.SPORTS_ESPORTS,
        "storage": ft.Icons.USB,
        "settings": ft.Icons.SETTINGS_OUTLINED,
    }
    nav_buttons = {
        name: ft.TextButton(
            label[0],
            icon=nav_icons[name],
            style=ft.ButtonStyle(
                color=MUTED,
                bgcolor=ft.Colors.TRANSPARENT,
                padding=ft.padding.symmetric(horizontal=15, vertical=11),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
        )
        for name, label in nav_names.items()
    }

    def ui_call(callback: Callable[[], None]) -> None:
        caller = getattr(page, "call_from_thread", None)
        caller(callback) if callable(caller) else callback()

    def selected_device() -> dict | None:
        return available_devices.get(store.target_path)

    def set_status(message: str, error: bool = False) -> None:
        status_text.value = message
        status_text.color = ft.Colors.RED_300 if error else ft.Colors.GREEN_300

    def set_activity(message: str = "", *, busy: bool = False, cancellable: bool = False) -> None:
        activity_text.value = message
        activity_text.visible = busy
        activity_spinner.visible = busy
        activity_progress.visible = busy
        activity_progress.value = None if busy else 0
        cancel_operation_btn.visible = busy and cancellable
        cancel_operation_btn.disabled = False
        cancel_operation_btn.text = "Cancel"

    def clear_game_views() -> None:
        store.scanned_games = []
        library.set_games([], ask_delete_game, open_artwork_for_game)
        library.update_storage({})
        artwork.update_source_choices([])
        artwork.game_dropdown.value = None
        artwork.refresh_selected_artwork(None)
        library.scan_btn.disabled = True

    def switch_page(name: str, check_drive: bool = True, rescan: bool = True) -> None:
        pages = {"home": home, "import": import_page, "library": library_and_artwork, "storage": storage, "settings": settings}
        active_page["name"] = name
        check_drive = check_drive and name != "settings" and not store.is_loading
        if name == "library" and check_drive:
            clear_game_views()
            library.set_loading()
        content.content = pages[name]
        for key, button in nav_buttons.items():
            button.style = ft.ButtonStyle(
                bgcolor=PRIMARY_SOFT if key == name else ft.Colors.TRANSPARENT,
                color=PRIMARY if key == name else MUTED,
                padding=ft.padding.symmetric(horizontal=15, vertical=11),
                shape=ft.RoundedRectangleBorder(radius=10),
            )
        set_status("Checking connected storage…") if check_drive else None
        page.update()
        if check_drive:
            refresh_devices(background=True, rescan_library=rescan)
        elif name == "library" and rescan and store.target_path:
            scan_library()

    for name, button in nav_buttons.items():
        button.on_click = lambda _, destination=name: switch_page(destination)

    def inspect_folders() -> dict[str, bool]:
        if not store.target_path:
            return {}
        root = Path(store.target_path)
        return {folder: (root / folder).is_dir() for folder in REQUIRED_FOLDERS}

    def selected_filesystem_supported(device: dict | None = None) -> bool:
        record = device or selected_device()
        filesystem = str((record or {}).get("filesystem") or "Unknown").strip().upper()
        # These are the filesystems exercised by the import pipeline and its integration coverage.
        return filesystem in {"FAT", "FAT16", "FAT32", "EXFAT", "NTFS"}

    def apply_selected_device(device: dict | None) -> None:
        previous_device_id = store.selected_device_id
        if not device:
            import_page.clear_drive()
            home.device_dropdown.value = None
            store.target_path = ""
            store.selected_device_id = ""
            clear_game_views()
            home.show_device(None)
            storage.show_device(None)
            return
        store.target_path = str(device["path"])
        store.selected_device_id = str(device["device_id"])
        if previous_device_id and previous_device_id != store.selected_device_id:
            clear_game_views()
        library.scan_btn.disabled = False
        home.device_dropdown.value = store.target_path
        import_page.drive_dropdown.value = store.target_path
        folders = inspect_folders()
        supported = selected_filesystem_supported(device)
        import_page.show_drive(device, supported)
        home.show_device(device, folders, supported)
        storage.show_device(device, folders, supported)
        app_config.last_selected_drive = store.target_path
        config_service.save_config(app_config)

    def collect_devices() -> list[dict]:
        records: list[dict] = []
        for device in drive_service.list_external_storage_devices():
            record = asdict(device)
            record["total_human"] = target_service.human_bytes(device.total_bytes)
            record["free_human"] = target_service.human_bytes(device.free_bytes)
            records.append(record)
        return records

    def apply_device_refresh(records: list[dict]) -> None:
        nonlocal available_devices
        device_refresh["running"] = False
        home.refresh_btn.disabled = False
        import_page.refresh_drives_btn.disabled = False
        home.device_dropdown.disabled = False
        import_page.drive_dropdown.disabled = False
        set_activity()
        available_devices = {str(record["path"]): record for record in records}
        import_page.set_drives(records)
        home.device_dropdown.options = [ft.dropdown.Option(key=r["path"], text=f"{r['letter']} | {r['model']} | {r['total_human']}") for r in records]
        device = retained_device(records, store.target_path, store.selected_device_id)
        apply_selected_device(device)
        set_status(("Selected USB refreshed." if device else "Select an external USB device to continue.") if records else "No external storage detected.", error=not bool(records))
        page.update()

    def refresh_devices(
        _: ft.ControlEvent | None = None,
        *,
        background: bool = True,
        rescan_library: bool = True,
    ) -> None:
        """Refresh storage without blocking navigation; concurrent requests are coalesced."""
        if store.is_loading:
            return
        device_refresh["requested_page"] = active_page["name"]
        if not background:
            apply_device_refresh(collect_devices())
            return
        if device_refresh["running"]:
            return
        device_refresh["running"] = True
        home.refresh_btn.disabled = True
        import_page.refresh_drives_btn.disabled = True
        home.device_dropdown.disabled = True
        import_page.drive_dropdown.disabled = True
        set_activity("Checking connected USB drives…", busy=True)
        page.update()

        def worker() -> None:
            try:
                records = collect_devices()
            except Exception:
                records = []

            def finish() -> None:
                device_refresh["running"] = False
                requested_page = device_refresh["requested_page"]
                apply_device_refresh(records)
                if (
                    rescan_library
                    and requested_page == "library"
                    and active_page["name"] == "library"
                    and store.target_path
                ):
                    scan_library()

            ui_call(finish)

        threading.Thread(target=worker, daemon=True).start()

    def choose_device(event: ft.ControlEvent) -> None:
        if store.is_loading or device_refresh["running"]:
            return
        apply_selected_device(available_devices.get(str(event.control.value or "")))
        page.update()

    operation_cancellable = {"value": False}

    def request_cancel(_: ft.ControlEvent | None = None) -> None:
        if not store.is_loading or not operation_cancellable["value"] or store.cancel_event.is_set():
            return
        store.request_cancel()
        cancel_operation_btn.disabled = True
        cancel_operation_btn.text = "Stopping…"
        set_status("Cancellation requested. Finishing the current safe cleanup…")
        page.update()

    cancel_operation_btn.on_click = request_cancel

    def run_async(
        function: Callable,
        *args,
        state: AppState,
        activity: str,
        cancellable: bool = False,
        done: Callable[[dict], None] | None = None,
    ) -> None:
        if device_refresh["running"]:
            set_status("Please wait until the USB check is complete before starting another operation.")
            page.update()
            return
        if store.is_loading:
            return
        store.is_loading = True
        store.current_state = state
        operation_cancellable["value"] = cancellable
        if cancellable:
            store.cancel_event.clear()
        home.disabled = storage.disabled = library.disabled = True
        artwork.set_busy(True, cancellable=cancellable)
        import_page.set_controls_enabled(False)
        set_activity(activity, busy=True, cancellable=cancellable)
        set_status("Please wait. Keep the USB connected until this operation finishes.")
        page.update()

        def worker() -> None:
            try:
                result = function(*args)
            except Exception:  # UI never exposes a traceback.
                result = {"status": "error", "message": "The operation could not be completed.", "details": {}}

            if result.get("status") == "error" and store.target_path and state != AppState.FORMATTING:
                try:
                    drive_service.validate_external_storage(store.target_path, store.selected_device_id)
                except Exception:
                    result["device_unavailable"] = True

            def finish() -> None:
                store.is_loading = False
                operation_cancellable["value"] = False
                home.disabled = storage.disabled = library.disabled = False
                artwork.set_busy(False)
                import_page.set_controls_enabled(True)
                set_activity()
                if result.get("device_unavailable"):
                    apply_selected_device(None)
                success = result.get("status") == "success"
                set_status(str(result.get("message") or "Done"), error=not success)
                if done:
                    done(result)
                page.update()

            ui_call(finish)

        threading.Thread(target=worker, daemon=True).start()

    def progress(status: str, message: str) -> None:
        if status == "progress" and message.startswith(("download|", "save|")):
            phase, completed, total, filename = (message.split("|", 3) + [""] * 4)[:4]
            try:
                current, count = int(completed), int(total)
            except ValueError:
                return
            ratio = current / count if count else 1.0
            def update_art_progress() -> None:
                if phase == "download":
                    activity_progress.value = ratio * 0.85
                    activity_text.value = f"Downloaded artwork {current}/{count} · {filename}"
                else:
                    activity_progress.value = 0.85 + ratio * 0.15
                    activity_text.value = f"Saving artwork {current}/{count} · {filename}"
                page.update()
            ui_call(update_art_progress)
            return
        if message.startswith("copying "):
            # Detailed per-file transfer progress is already shown in Import.
            # Keep the global status bar concise so it does not get squeezed
            # between the operation label and cancel control.
            return
        ui_call(lambda: (set_status(message, status == "error"), page.update()))

    def on_iso_result(event: ft.FilePickerResultEvent) -> None:
        import_page.set_selected_isos([item.path for item in (event.files or []) if item.path])
        page.update()

    def on_art_result(event: ft.FilePickerResultEvent) -> None:
        if event.files and event.files[0].path:
            artwork.set_manual_file(pending_art_type["value"], event.files[0].path)
            page.update()

    iso_picker.on_result = on_iso_result
    art_picker.on_result = on_art_result

    def scan_library(switch_after: bool = False) -> None:
        if not store.target_path:
            dialogs.show_snackbar(page, "Connect external storage first.", True)
            return

        def after(result: dict) -> None:
            if result.get("status") != "success":
                dialogs.show_snackbar(page, str(result.get("message")), True)
                return
            details = result["details"]
            games = list(details.get("games", []))
            summary = dict(details.get("storage", {}))
            summary["count"] = len(games)
            store.scanned_games = games
            library.set_games(games, ask_delete_game, open_artwork_for_game)
            library.update_storage(summary)
            artwork.update_source_choices(games)
            storage.show_device(selected_device(), inspect_folders(), selected_filesystem_supported())
            if switch_after:
                switch_page("library", check_drive=False, rescan=False)
            if auto_art_pending["value"] and games:
                auto_art_pending["value"] = False
                download_all_artwork()

        run_async(
            game_controller.scan_games,
            store.target_path,
            progress,
            store.selected_device_id,
            state=AppState.VALIDATING,
            activity="Scanning the USB game library…",
            done=after,
        )

    def import_games(_: ft.ControlEvent | None = None) -> None:
        if not store.target_path or not import_page.selected_isos:
            dialogs.show_snackbar(page, "Select external storage and at least one ISO file.", True)
            return
        import_page.clear_result()
        import_page.job_progress.visible = True
        import_page.job_progress.value = 0

        def after(result: dict) -> None:
            if result.get("status") == "success":
                imported = int(result.get("details", {}).get("imported_count", 0))
                message = (
                    f"นำเข้าเกมสำเร็จ {imported} เกม สามารถเปิดหน้า Games & Artwork เพื่อตรวจสอบได้"
                    if i18n.get_lang() == "th"
                    else f"Imported {imported} game(s); skipped {result.get('details', {}).get('skipped_count', 0)}. Open Games & Artwork to review them."
                )
                import_page.show_result(True, "นำเข้าสำเร็จ" if i18n.get_lang() == "th" else "Import complete", message)
                dialogs.show_snackbar(page, f"Import complete: {imported} game(s) imported.")
                auto_art_pending["value"] = bool(app_config.auto_download_artwork)
                scan_library(switch_after=True)
            elif result.get("status") == "cancelled":
                import_page.show_result(False, "ยกเลิกแล้ว" if i18n.get_lang() == "th" else "Import cancelled", "ไฟล์ที่คัดลอกไม่เสร็จถูกลบแล้ว" if i18n.get_lang() == "th" else f"Completed games remain on USB: {result.get('details', {}).get('imported_count', 0)}. Unfinished games were not imported.")
                dialogs.show_snackbar(page, "Import cancelled. Incomplete files were removed.", True)
            else:
                message = str(
                    (result.get("message_th") if i18n.get_lang() == "th" else None)
                    or result.get("message")
                    or "The game could not be imported."
                )
                if result.get("details", {}).get("file"):
                    message += f" File: {result['details']['file']}"
                import_page.show_result(False, "นำเข้าไม่สำเร็จ" if i18n.get_lang() == "th" else "Import failed", message)
                dialogs.show_snackbar(page, message, True)

        run_async(
            import_controller.import_isos,
            store.target_path,
            import_page.selected_isos,
            bool(import_page.overwrite_checkbox.value),
            progress,
            store.cancel_event,
            store.selected_device_id,
            lambda event: ui_call(lambda: (import_page.show_progress(event), page.update())),
            state=AppState.IMPORTING,
            activity="Importing selected games…",
            cancellable=True,
            done=after,
        )

    def prepare_storage(_: ft.ControlEvent | None = None) -> None:
        if not store.target_path:
            return

        def after(result: dict) -> None:
            device = selected_device()
            folders = inspect_folders()
            supported = selected_filesystem_supported(device)
            storage.show_device(device, folders, supported)
            home.show_device(device, folders, supported)
            dialogs.show_snackbar(page, str(result.get("message")), result.get("status") != "success")

        run_async(
            import_controller.validate_target,
            store.target_path,
            True,
            progress,
            store.selected_device_id,
            state=AppState.VALIDATING,
            activity="Creating missing OPL folders…",
            done=after,
        )

    def format_storage(_: ft.ControlEvent | None = None) -> None:
        device = selected_device()
        if not device:
            return

        target_path, device_id = store.target_path, store.selected_device_id

        def confirmed(label: str) -> None:
            run_async(
                import_controller.format_target,
                target_path,
                "FORMAT",
                label,
                progress,
                device_id,
                state=AppState.FORMATTING,
                activity="Formatting USB drive…",
                done=lambda result: (dialogs.show_snackbar(page, str(result.get("message")), result.get("status") != "success"), refresh_devices()),
            )

        dialogs.show_format_dialog(page, confirmed, device)

    def ask_delete_game(game: dict) -> None:
        def confirmed() -> None:
            run_async(
                game_controller.delete_game,
                store.target_path,
                str(game.get("game_id") or ""),
                str(game.get("destination_filename") or ""),
                progress,
                False,
                False,
                store.selected_device_id,
                state=AppState.IMPORTING,
                activity="Deleting selected game…",
                done=lambda result: (dialogs.show_snackbar(page, str(result.get("message")), result.get("status") != "success"), scan_library()),
            )

        dialogs.show_delete_dialog(page, game, confirmed)

    def open_artwork_for_game(game: dict) -> None:
        library_and_artwork.selected_index = 1
        for key, value in artwork._games.items():
            if value is game or value.get("path") == game.get("path"):
                artwork.game_dropdown.value = key
                artwork._refresh_game()
                break
        switch_page("library", check_drive=False, rescan=False)

    def refresh_artwork_status(game: dict | None = None) -> None:
        selected = game or artwork.selected_game()
        game_id = str(selected.get("game_id") or "") if selected else ""
        if not store.target_path or not game_id:
            return
        artwork.set_artwork_status(art_controller.get_artwork_status(store.target_path, game_id, store.selected_device_id))
        page.update()

    artwork.on_game_selected = refresh_artwork_status

    def save_artwork(_: ft.ControlEvent | None = None) -> None:
        game = artwork.selected_game()
        if not game:
            dialogs.show_snackbar(page, "Select a game first.", True)
            return

        def after(result: dict) -> None:
            dialogs.show_snackbar(page, str(result.get("message")), result.get("status") != "success")
            if result.get("status") == "success":
                scan_library()

        run_async(
            art_controller.upload_art_manual,
            store.target_path,
            str(game.get("game_name") or ""),
            str(game.get("destination_filename") or ""),
            artwork.collect_manual_files(),
            progress,
            store.selected_device_id,
            state=AppState.ARTING,
            activity="Saving artwork…",
            done=after,
        )

    def remove_artwork(_: ft.ControlEvent | None = None) -> None:
        game = artwork.selected_game()
        if not game:
            return

        art_type = str(artwork.type_dropdown.value or "COV")
        label = str(artwork._status.get(art_type, {}).get("label") or art_type)

        def confirmed() -> None:
            page.close(confirm_dialog)
            run_async(
                art_controller.remove_artwork,
                store.target_path,
                str(game.get("game_id") or ""),
                art_type,
                progress,
                store.selected_device_id,
                artwork.selected_filename() if art_type == "SCR" else None,
                state=AppState.ARTING,
                activity="Removing artwork…",
                done=lambda result: (dialogs.show_snackbar(page, str(result.get("message")), result.get("status") != "success"), refresh_artwork_status()),
            )

        confirm_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Remove {label}?"),
            content=ft.Text("This artwork will be removed from the selected OPL storage."),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: page.close(confirm_dialog)),
                ft.OutlinedButton("Remove", on_click=lambda _: confirmed(), style=danger_style()),
            ],
        )
        page.open(confirm_dialog)

    def download_selected_artwork(_: ft.ControlEvent | None = None, replace: bool = False) -> None:
        game = artwork.selected_game()
        if not game:
            dialogs.show_snackbar(page, "Select a game first.", True)
            return
        def after(result: dict) -> None:
            dialogs.show_snackbar(page, str(result.get("message")), result.get("status") not in {"success", "cancelled"})
            refresh_artwork_status()

        run_async(
            art_controller.download_artwork,
            store.target_path,
            str(game.get("game_id") or ""),
            replace,
            progress,
            store.cancel_event,
            store.selected_device_id,
            state=AppState.ARTING,
            activity="Downloading artwork…",
            cancellable=True,
            done=after,
        )

    def confirm_replace_online(_: ft.ControlEvent | None = None) -> None:
        if not artwork.selected_game():
            return

        def confirmed(_: ft.ControlEvent) -> None:
            page.close(confirm_dialog)
            download_selected_artwork(replace=True)

        confirm_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Replace artwork from online sources?"),
            content=ft.Text("Existing artwork, including custom images, may be replaced for this game."),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: page.close(confirm_dialog)),
                ft.OutlinedButton("Replace", on_click=confirmed, style=danger_style()),
            ],
        )
        page.open(confirm_dialog)

    def download_all_artwork(_: ft.ControlEvent | None = None) -> None:
        if not store.scanned_games:
            dialogs.show_snackbar(page, "Scan the game library first.", True)
            return
        def after(result: dict) -> None:
            dialogs.show_snackbar(page, str(result.get("message")), result.get("status") not in {"success", "cancelled"})
            scan_library()

        run_async(
            art_controller.download_artwork_batch,
            store.target_path,
            list(store.scanned_games),
            progress,
            store.cancel_event,
            store.selected_device_id,
            state=AppState.ARTING,
            activity="Checking artwork for all games…",
            cancellable=True,
            done=after,
        )

    def save_auto_artwork(_: ft.ControlEvent | None = None) -> None:
        app_config.auto_download_artwork = bool(auto_artwork_checkbox.value)
        config_service.save_config(app_config)
        dialogs.show_snackbar(page, "Artwork setting saved.")

    def toggle_language(_: ft.ControlEvent | None = None) -> None:
        new_language = "en" if i18n.get_lang() == "th" else "th"
        i18n.set_lang(new_language)
        english = new_language == "en"
        settings_language.value = "English" if english else "ภาษาไทย"
        settings_toggle.text = "ไทย" if english else "English"
        language_button.text = "ไทย" if english else "English"
        for name, button in nav_buttons.items():
            button.text = nav_names[name][0 if english else 1]
        import_page.translate(new_language)
        page.update()

    def request_import(event: ft.ControlEvent) -> None:
        if not import_page.overwrite_checkbox.value:
            import_games(event)
            return

        def confirmed(_: ft.ControlEvent) -> None:
            page.close(confirm_dialog)
            import_games(event)

        confirm_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Replace existing games?"),
            content=ft.Text(
                f"Destination: {import_page.summary_destination.value}. "
                "Matching games will be replaced. USBExtreme replacement deletes the old parts first; "
                "a failure or cancellation can lose the original game. Completed imports remain on USB."
            ),
            actions=[ft.TextButton("Cancel", on_click=lambda _: page.close(confirm_dialog)),
                     ft.OutlinedButton("Replace and import", style=danger_style(), on_click=confirmed)],
        )
        page.open(confirm_dialog)

    import_page.refresh_drives_btn.on_click = refresh_devices
    import_page.drive_dropdown.on_change = choose_device
    import_page.import_btn.on_click = request_import
    import_page.cancel_btn.on_click = request_cancel
    library.scan_btn.on_click = lambda _: scan_library()
    artwork.save_btn.on_click = save_artwork
    artwork.remove_btn.on_click = remove_artwork
    artwork.download_btn.on_click = download_selected_artwork
    artwork.refresh_btn.on_click = lambda _: refresh_artwork_status()
    artwork.replace_online_btn.on_click = confirm_replace_online
    artwork.batch_btn.on_click = download_all_artwork
    artwork.cancel_batch_btn.on_click = request_cancel
    storage.prepare_btn.on_click = prepare_storage
    storage.format_btn.on_click = format_storage
    home.readiness_action.on_click = lambda _: (
        prepare_storage() if home.readiness_action_mode == "repair" else switch_page("storage")
    )
    home.device_dropdown.on_change = choose_device
    home.refresh_btn.on_click = refresh_devices
    home.import_btn.on_click = lambda _: switch_page("import")
    home.library_btn.on_click = lambda _: (setattr(library_and_artwork, "selected_index", 0), switch_page("library"))
    home.artwork_btn.on_click = lambda _: (setattr(library_and_artwork, "selected_index", 1), switch_page("library"))
    home.storage_btn.on_click = lambda _: switch_page("storage")
    settings_toggle.on_click = toggle_language
    auto_artwork_checkbox.on_change = save_auto_artwork

    language_button = ft.TextButton("ไทย", icon=ft.Icons.LANGUAGE, on_click=toggle_language)
    page.appbar = ft.AppBar(
        title=ft.Row(
            [
                ft.Container(
                    width=34,
                    height=34,
                    border_radius=10,
                    bgcolor=PRIMARY_SOFT,
                    alignment=ft.alignment.center,
                    content=ft.Icon(ft.Icons.SPORTS_ESPORTS, color=PRIMARY, size=20),
                ),
                ft.Column(
                    [
                        ft.Text("PS2 TOOLKIT", size=15, weight=ft.FontWeight.BOLD, color=TEXT),
                        ft.Text("2000X  /  OPL LIBRARY", size=10, color=MUTED),
                    ],
                    spacing=0,
                    tight=True,
                ),
            ],
            spacing=11,
        ),
        actions=[language_button],
        bgcolor=BACKGROUND,
        elevation=0,
    )
    nav = ft.Container(
        padding=ft.padding.symmetric(horizontal=24, vertical=10),
        bgcolor=BACKGROUND,
        border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
        content=ft.Row(
            [
                *list(nav_buttons.values()),
                ft.Container(expand=True),
                ft.Container(
                    padding=ft.padding.symmetric(horizontal=11, vertical=7),
                    bgcolor=SURFACE,
                    border_radius=30,
                    content=ft.Row(
                        [ft.Container(width=7, height=7, bgcolor=SUCCESS, border_radius=10), ft.Text("LOCAL MODE", size=10, weight=ft.FontWeight.BOLD, color=MUTED)],
                        spacing=7,
                    ),
                ),
            ],
            spacing=5,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )
    page.add(ft.Column([nav, content, status_bar], expand=True, spacing=0, horizontal_alignment=ft.CrossAxisAlignment.STRETCH))
    switch_page(screenshot_page or "home")

    update_running = False

    async def install_update(release: dict[str, str]) -> None:
        nonlocal update_running
        if update_running:
            return
        if store.is_loading or device_refresh["running"]:
            dialogs.show_snackbar(page, "Wait for the current operation to finish before updating.", True)
            dialogs.show_update_banner(page, release, lambda: page.run_task(install_update, release))
            return
        update_running = True
        root = page.controls[0]
        root.disabled = True
        progress_bar = ft.ProgressBar(value=0)
        message = ft.Text("Downloading update… The app will close and reopen after installation.")
        dialog = ft.AlertDialog(modal=True, title=ft.Text("Updating PS2 Toolkit"), content=ft.Column([message, progress_bar], tight=True, width=460))
        page.open(dialog)
        installer = None
        try:
            def report(value: float) -> None:
                progress_bar.value = value
                message.value = f"Downloading update… {int(value * 100)}%"
                page.update()

            installer = await asyncio.to_thread(update_service.download_update, release, report)
            message.value = "Installing update… The app will reopen automatically."
            page.update()
            update_service.launch_update(installer)
            page.window.destroy()
            os._exit(0)
        except Exception as exc:
            if installer is not None:
                import shutil
                shutil.rmtree(installer.parent, ignore_errors=True)
            root.disabled = False
            page.close(dialog)
            dialogs.show_snackbar(page, f"Update failed: {exc}. Please try again.", True)
            dialogs.show_update_banner(page, release, lambda: page.run_task(install_update, release))
        finally:
            update_running = False

    async def check_updates() -> None:
        release = await asyncio.to_thread(update_service.check_for_update)
        if release:
            callback = (lambda: page.run_task(install_update, release)) if update_service.supports_in_app_update() else None
            dialogs.show_update_banner(page, release, callback)

    if screenshot_page is None:
        page.run_task(check_updates)
