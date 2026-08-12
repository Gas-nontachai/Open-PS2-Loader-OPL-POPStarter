from __future__ import annotations

import threading
from dataclasses import asdict
from pathlib import Path
from typing import Callable

import flet as ft

from app.controllers import art_controller, game_controller, import_controller
from app.core import config as config_service, i18n
from app.core.constants import APP_NAME, APP_VERSION, REQUIRED_FOLDERS
from app.services import drive_service, target_service
from app.ui import dialogs
from app.ui.art_tab import ArtTab
from app.ui.home_page import HomePage
from app.ui.import_tab import ImportTab
from app.ui.library_tab import LibraryTab
from app.ui.state import AppState, AppStore
from app.ui.storage_page import StoragePage


def build_app(page: ft.Page) -> None:
    page.title = APP_NAME
    page.window.width = 1240
    page.window.height = 820
    page.window.min_width = 820
    page.window.min_height = 620
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.CYAN, visual_density=ft.VisualDensity.COMFORTABLE)
    page.padding = 0

    store = AppStore()
    app_config = config_service.load_config()
    available_devices: dict[str, dict] = {}
    active_page = {"name": "home"}
    device_refresh = {"running": False, "requested_page": ""}

    iso_picker = ft.FilePicker()
    art_picker = ft.FilePicker()
    page.overlay.extend([iso_picker, art_picker])

    home = HomePage()
    import_page = ImportTab(page, on_pick_isos=lambda: iso_picker.pick_files(allow_multiple=True, allowed_extensions=["iso"]))
    library = LibraryTab()
    artwork = ArtTab(on_pick_manual_art=lambda _: art_picker.pick_files(allow_multiple=False, allowed_extensions=["png", "jpg", "jpeg", "webp"]))
    storage = StoragePage()
    library_and_artwork = ft.Column(
        [library, ft.Divider(height=32), artwork],
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=20,
    )
    status_text = ft.Text("Ready")
    status_bar = ft.Container(content=status_text, padding=10, bgcolor=ft.Colors.GREY_900)

    settings_language = ft.Text("English")
    settings_toggle = ft.OutlinedButton("ไทย", icon=ft.Icons.LANGUAGE)
    settings = ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=16,
        controls=[
            ft.Text("Settings", size=28, weight=ft.FontWeight.BOLD),
            ft.Text("Language", size=18, weight=ft.FontWeight.BOLD),
            settings_language,
            settings_toggle,
            ft.Divider(),
            ft.Text(APP_NAME, size=20, weight=ft.FontWeight.BOLD),
            ft.Text(f"Version {APP_VERSION}"),
            ft.Text("PS2 Game Importer & OPL USB Manager"),
            ft.Text("All game, storage, and artwork features work offline."),
        ],
    )

    content = ft.Container(expand=True, padding=20, content=home)
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
    nav_buttons = {name: ft.TextButton(label[0], icon=nav_icons[name]) for name, label in nav_names.items()}

    def ui_call(callback: Callable[[], None]) -> None:
        caller = getattr(page, "call_from_thread", None)
        caller(callback) if callable(caller) else callback()

    def selected_device() -> dict | None:
        return available_devices.get(store.target_path)

    def set_status(message: str, error: bool = False) -> None:
        status_text.value = message
        status_text.color = ft.Colors.RED_300 if error else ft.Colors.GREEN_300

    def clear_game_views() -> None:
        store.scanned_games = []
        library.set_games([], ask_delete_game, open_artwork_for_game)
        library.update_storage({})
        artwork.update_source_choices([])
        artwork.game_dropdown.value = None
        artwork.refresh_selected_artwork(None)

    def switch_page(name: str, check_drive: bool = True, rescan: bool = True) -> None:
        pages = {"home": home, "import": import_page, "library": library_and_artwork, "storage": storage, "settings": settings}
        active_page["name"] = name
        if name == "library" and check_drive:
            clear_game_views()
            library.set_loading()
        content.content = pages[name]
        for key, button in nav_buttons.items():
            button.style = ft.ButtonStyle(
                bgcolor=ft.Colors.CYAN_800 if key == name else ft.Colors.TRANSPARENT,
                color=ft.Colors.WHITE,
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

    def apply_selected_device(device: dict | None) -> None:
        previous_device_id = store.selected_device_id
        if not device:
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
        import_page.drive_dropdown.value = store.target_path
        import_page.show_drive(device)
        home.show_device(device)
        storage.show_device(device, inspect_folders())
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
        available_devices = {str(record["path"]): record for record in records}
        import_page.set_drives(records)
        preferred = store.target_path or app_config.last_selected_drive
        device = available_devices.get(preferred)
        if not device and records:
            device = records[0]
        apply_selected_device(device)
        set_status("External storage refreshed." if records else "No external storage detected.", error=not bool(records))
        page.update()

    def refresh_devices(
        _: ft.ControlEvent | None = None,
        *,
        background: bool = True,
        rescan_library: bool = True,
    ) -> None:
        """Refresh storage without blocking navigation; concurrent requests are coalesced."""
        device_refresh["requested_page"] = active_page["name"]
        if not background:
            apply_device_refresh(collect_devices())
            return
        if device_refresh["running"]:
            return
        device_refresh["running"] = True

        def worker() -> None:
            records = collect_devices()

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

    def choose_device(_: ft.ControlEvent) -> None:
        apply_selected_device(available_devices.get(str(import_page.drive_dropdown.value or "")))
        page.update()

    def run_async(function: Callable, *args, state: AppState, done: Callable[[dict], None] | None = None) -> None:
        store.current_state = state
        import_page.set_controls_enabled(False)
        set_status("Working…")
        page.update()

        def worker() -> None:
            try:
                result = function(*args)
            except Exception:  # UI never exposes a traceback.
                result = {"status": "error", "message": "The operation could not be completed.", "details": {}}

            def finish() -> None:
                import_page.set_controls_enabled(True)
                success = result.get("status") == "success"
                set_status(str(result.get("message") or "Done"), error=not success)
                if done:
                    done(result)
                page.update()

            ui_call(finish)

        threading.Thread(target=worker, daemon=True).start()

    def progress(status: str, message: str) -> None:
        ui_call(lambda: (set_status(message, status == "error"), page.update()))

    def on_iso_result(event: ft.FilePickerResultEvent) -> None:
        import_page.set_selected_isos([item.path for item in (event.files or []) if item.path])
        page.update()

    def on_art_result(event: ft.FilePickerResultEvent) -> None:
        if event.files and event.files[0].path:
            artwork.set_manual_file("COV", event.files[0].path)
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
            storage.show_device(selected_device(), inspect_folders())
            if switch_after:
                switch_page("library", check_drive=False, rescan=False)

        run_async(
            game_controller.scan_games,
            store.target_path,
            progress,
            store.selected_device_id,
            state=AppState.VALIDATING,
            done=after,
        )

    def import_games(_: ft.ControlEvent | None = None) -> None:
        if not store.target_path or not import_page.selected_isos:
            dialogs.show_snackbar(page, "Select external storage and at least one ISO file.", True)
            return
        store.cancel_event.clear()
        import_page.clear_result()

        def after(result: dict) -> None:
            if result.get("status") == "success":
                imported = int(result.get("details", {}).get("imported_count", 0))
                message = (
                    f"นำเข้าเกมสำเร็จ {imported} เกม สามารถเปิดหน้า Games & Artwork เพื่อตรวจสอบได้"
                    if i18n.get_lang() == "th"
                    else f"Imported {imported} game(s). Open Games & Artwork to review them."
                )
                import_page.show_result(True, "นำเข้าสำเร็จ" if i18n.get_lang() == "th" else "Import complete", message)
                dialogs.show_snackbar(page, f"Import complete: {imported} game(s) imported.")
                scan_library(switch_after=True)
            elif result.get("status") == "cancelled":
                import_page.show_result(False, "ยกเลิกแล้ว" if i18n.get_lang() == "th" else "Import cancelled", "ไฟล์ที่คัดลอกไม่เสร็จถูกลบแล้ว" if i18n.get_lang() == "th" else "Incomplete files were removed.")
                dialogs.show_snackbar(page, "Import cancelled. Incomplete files were removed.", True)
            else:
                message = str(
                    (result.get("message_th") if i18n.get_lang() == "th" else None)
                    or result.get("message")
                    or "The game could not be imported."
                )
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
            state=AppState.IMPORTING,
            done=after,
        )

    def prepare_storage(_: ft.ControlEvent | None = None) -> None:
        if not store.target_path:
            return

        def after(result: dict) -> None:
            storage.show_device(selected_device(), inspect_folders())
            dialogs.show_snackbar(page, str(result.get("message")), result.get("status") != "success")

        run_async(
            import_controller.validate_target,
            store.target_path,
            True,
            progress,
            store.selected_device_id,
            state=AppState.VALIDATING,
            done=after,
        )

    def format_storage(_: ft.ControlEvent | None = None) -> None:
        device = selected_device()
        if not device:
            return

        def confirmed(label: str) -> None:
            run_async(
                import_controller.format_target,
                store.target_path,
                "FORMAT",
                label,
                progress,
                store.selected_device_id,
                state=AppState.FORMATTING,
                done=lambda result: (dialogs.show_snackbar(page, str(result.get("message")), result.get("status") != "success"), refresh_devices()),
            )

        dialogs.show_format_dialog(page, confirmed)

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
                done=lambda result: (dialogs.show_snackbar(page, str(result.get("message")), result.get("status") != "success"), scan_library()),
            )

        dialogs.show_delete_dialog(page, game, confirmed)

    def open_artwork_for_game(game: dict) -> None:
        for key, value in artwork._games.items():
            if value is game or value.get("path") == game.get("path"):
                artwork.game_dropdown.value = key
                artwork._refresh_game()
                break
        switch_page("library", check_drive=False, rescan=False)

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
            done=after,
        )

    def remove_artwork(_: ft.ControlEvent | None = None) -> None:
        game = artwork.selected_game()
        if not game:
            return

        def confirmed() -> None:
            run_async(
                art_controller.remove_artwork,
                store.target_path,
                str(game.get("game_id") or ""),
                "COV",
                progress,
                store.selected_device_id,
                state=AppState.ARTING,
                done=lambda result: (dialogs.show_snackbar(page, str(result.get("message")), result.get("status") != "success"), scan_library()),
            )

        dialogs.show_artwork_remove_dialog(page, str(game.get("game_name") or ""), confirmed)

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

    import_page.refresh_drives_btn.on_click = refresh_devices
    import_page.drive_dropdown.on_change = choose_device
    import_page.import_btn.on_click = import_games
    import_page.cancel_btn.on_click = lambda _: store.request_cancel()
    library.scan_btn.on_click = lambda _: scan_library()
    artwork.save_btn.on_click = save_artwork
    artwork.remove_btn.on_click = remove_artwork
    storage.prepare_btn.on_click = prepare_storage
    storage.format_btn.on_click = format_storage
    home.refresh_btn.on_click = refresh_devices
    home.import_btn.on_click = lambda _: switch_page("import")
    home.library_btn.on_click = lambda _: switch_page("library")
    home.artwork_btn.on_click = lambda _: switch_page("library")
    home.storage_btn.on_click = lambda _: switch_page("storage")
    settings_toggle.on_click = toggle_language

    language_button = ft.TextButton("ไทย", icon=ft.Icons.LANGUAGE, on_click=toggle_language)
    page.appbar = ft.AppBar(title=ft.Text(APP_NAME, weight=ft.FontWeight.BOLD), actions=[language_button])
    nav = ft.Container(
        padding=ft.padding.symmetric(horizontal=12, vertical=8),
        bgcolor=ft.Colors.GREY_900,
        content=ft.Row(list(nav_buttons.values()), wrap=True, spacing=4),
    )
    page.add(ft.Column([nav, content, status_bar], expand=True, spacing=0))
    switch_page("home")
