from __future__ import annotations

import threading
from typing import Callable

import flet as ft

from app.controllers import art_controller, game_controller, import_controller
from app.core import i18n
from app.core.i18n import t
from app.ui import dialogs
from app.ui.art_tab import ArtTab
from app.ui.console_panel import ConsolePanel
from app.ui.import_tab import ImportTab
from app.ui.state import AppState, AppStore


def build_app(page: ft.Page) -> None:
    page.title = "PS2 TOOLKIT 2000X"
    page.window.width = 1200
    page.window.height = 800
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.CYAN)

    store = AppStore()
    console = ConsolePanel()

    selected_manual_art_type = {"value": "COV"}

    def set_state(new_state: AppState, message: str | None = None) -> None:
        try:
            store.set_state(new_state)
        except ValueError:
            store.current_state = new_state
        console.set_state(store.current_state)
        if message:
            console.set_status(message)

    def ui_call(fn: Callable[[], None]) -> None:
        caller = getattr(page, "call_from_thread", None)
        if callable(caller):
            caller(fn)
        else:
            fn()

    folder_picker = ft.FilePicker(on_result=lambda e: on_pick_folder_result(e))
    iso_picker = ft.FilePicker(on_result=lambda e: on_pick_iso_result(e))
    manual_art_picker = ft.FilePicker(on_result=lambda e: on_pick_manual_art_result(e))
    page.overlay.extend([folder_picker, iso_picker, manual_art_picker])

    import_tab = ImportTab(page, on_pick_folder=lambda: folder_picker.get_directory_path(), on_pick_isos=lambda: iso_picker.pick_files(allow_multiple=True, allowed_extensions=["iso"]))
    art_tab = ArtTab(on_pick_manual_art=lambda art_type: pick_manual_art(art_type))

    loading_overlay = ft.Container(
        visible=False,
        expand=True,
        bgcolor=ft.Colors.with_opacity(0.7, ft.Colors.BLACK),
        alignment=ft.alignment.center,
        content=ft.ProgressRing(),
    )

    def append_console(status: str, message: str) -> None:
        def _inner() -> None:
            console.append_log(status, message)
            if status == "error":
                console.set_status(message)
            page.update()

        ui_call(_inner)

    def set_busy(busy: bool) -> None:
        store.is_loading = busy
        loading_overlay.visible = busy
        import_tab.set_controls_enabled(not busy)
        art_tab.disabled = busy

    def run_async(
        target_func: Callable,
        *args,
        busy_state: AppState,
        on_done: Callable[[dict], None] | None = None,
    ) -> None:
        set_state(busy_state, t("status_busy"))
        set_busy(True)
        page.update()

        def worker() -> None:
            try:
                result = target_func(*args)
            except Exception as exc:  # noqa: BLE001
                result = {"status": "error", "message": str(exc), "details": {"error": str(exc)}}

            def finalize() -> None:
                set_busy(False)
                if result.get("status") == "success":
                    set_state(AppState.COMPLETED, result.get("message", t("status_done")))
                elif result.get("status") == "cancelled":
                    set_state(AppState.CANCELLED, result.get("message", t("cancelled")))
                else:
                    set_state(AppState.FAILED, result.get("message", t("status_failed")))

                if on_done:
                    on_done(result)
                page.update()

            ui_call(finalize)

        threading.Thread(target=worker, daemon=True).start()

    def on_pick_folder_result(e: ft.FilePickerResultEvent) -> None:
        if e.path:
            import_tab.target_path.value = e.path
            store.target_path = e.path
            page.update()

    def on_pick_iso_result(e: ft.FilePickerResultEvent) -> None:
        paths = [f.path for f in (e.files or []) if f.path]
        import_tab.set_selected_isos(paths)
        page.update()

    def on_pick_manual_art_result(e: ft.FilePickerResultEvent) -> None:
        if not e.files:
            return
        path = e.files[0].path
        if not path:
            return
        art_type = selected_manual_art_type["value"]
        art_tab.set_manual_file(art_type, path)
        page.update()

    def pick_manual_art(art_type: str) -> None:
        selected_manual_art_type["value"] = art_type
        manual_art_picker.pick_files(allow_multiple=False, allowed_extensions=["jpg", "jpeg", "png"])

    def after_validate(result: dict) -> None:
        append_console("success" if result.get("status") == "success" else "error", result.get("message", ""))
        if result.get("status") == "success":
            import_tab.reveal_post_validation()
            set_state(AppState.VALIDATED, result.get("message", "validated"))
            store.target_path = import_tab.target_path.value.strip()

    def do_validate() -> None:
        target = import_tab.target_path.value.strip()
        if not target:
            dialogs.show_snackbar(page, "target path required", is_error=True)
            return
        store.cancel_event.clear()
        run_async(import_controller.validate_target, target, True, append_console, busy_state=AppState.VALIDATING, on_done=after_validate)

    def after_format(result: dict) -> None:
        append_console("success" if result.get("status") == "success" else "error", result.get("message", ""))
        if result.get("status") == "success":
            target = str(result.get("details", {}).get("target", import_tab.target_path.value.strip()))
            import_tab.target_path.value = target
            store.target_path = target
            do_validate()

    def do_format() -> None:
        target = import_tab.target_path.value.strip()
        if not target:
            dialogs.show_snackbar(page, "target path required", is_error=True)
            return

        def on_confirm(label: str) -> None:
            run_async(
                import_controller.format_target,
                target,
                "FORMAT",
                label,
                append_console,
                busy_state=AppState.FORMATTING,
                on_done=after_format,
            )

        dialogs.show_format_dialog(page, on_confirm)

    def after_scan(result: dict) -> None:
        if result.get("status") != "success":
            append_console("error", result.get("message", "scan failed"))
            return
        details = result.get("details", {})
        games = list(details.get("games", []))
        storage = dict(details.get("storage", {}))
        storage["count"] = int(details.get("count", len(games)))
        store.scanned_games = games
        store.storage_summary = storage
        import_tab.set_games(games, on_delete=ask_delete_game)
        import_tab.update_storage(storage)
        art_tab.update_source_choices(games)
        append_console("success", result.get("message", "scan completed"))

    def do_scan() -> None:
        target = import_tab.target_path.value.strip()
        if not target:
            dialogs.show_snackbar(page, "target path required", is_error=True)
            return
        run_async(game_controller.scan_games, target, append_console, busy_state=AppState.VALIDATING, on_done=after_scan)

    def after_import(result: dict) -> None:
        if result.get("status") == "success":
            append_console("success", result.get("message", "import completed"))
            do_scan()
        elif result.get("status") == "cancelled":
            append_console("error", result.get("message", "import cancelled"))
            set_state(AppState.CANCELLED, result.get("message", "cancelled"))
        else:
            append_console("error", result.get("message", "import failed"))

    def do_import() -> None:
        target = import_tab.target_path.value.strip()
        if not target:
            dialogs.show_snackbar(page, "target path required", is_error=True)
            return
        if not import_tab.selected_isos:
            dialogs.show_snackbar(page, t("no_selection"), is_error=True)
            return
        store.cancel_event.clear()
        run_async(
            import_controller.import_isos,
            target,
            import_tab.selected_isos,
            bool(import_tab.overwrite_checkbox.value),
            append_console,
            store.cancel_event,
            busy_state=AppState.IMPORTING,
            on_done=after_import,
        )

    def ask_delete_game(game: dict) -> None:
        def on_confirm() -> None:
            target = import_tab.target_path.value.strip()

            def after_delete(result: dict) -> None:
                append_console("success" if result.get("status") == "success" else "error", result.get("message", "delete done"))
                if result.get("status") == "success":
                    do_scan()

            run_async(
                game_controller.delete_game,
                target,
                str(game.get("game_id") or ""),
                str(game.get("destination_filename") or ""),
                append_console,
                busy_state=AppState.IMPORTING,
                on_done=after_delete,
            )

        dialogs.show_delete_dialog(page, str(game.get("game_name") or "-"), on_confirm)

    def do_cancel() -> None:
        store.request_cancel()
        set_state(AppState.CANCELLED, t("cancelled"))
        append_console("error", "operation cancelled")

    def after_art_search(result: dict) -> None:
        if result.get("status") != "success":
            append_console("error", result.get("message", "search failed"))
            return
        candidates = list(result.get("details", {}).get("candidates", []))
        store.art_candidates = candidates
        art_tab.render_candidates(candidates)
        append_console("success", result.get("message", "art ready"))

    def do_art_search() -> None:
        run_async(
            art_controller.search_art,
            import_tab.target_path.value.strip() or None,
            art_tab.game_name.value.strip() or None,
            art_tab.iso_filename.value.strip() or None,
            10,
            append_console,
            busy_state=AppState.ARTING,
            on_done=after_art_search,
        )

    def after_art_save(result: dict) -> None:
        if result.get("status") == "success":
            append_console("success", result.get("message", "saved"))
            dialogs.show_snackbar(page, t("snack_done"), is_error=False)
        else:
            append_console("error", result.get("message", "failed"))
            dialogs.show_snackbar(page, t("snack_error"), is_error=True)

    def do_art_save_auto() -> None:
        selections = art_tab.collect_auto_selections()
        run_async(
            art_controller.save_art_auto,
            import_tab.target_path.value.strip(),
            art_tab.game_name.value.strip() or None,
            art_tab.iso_filename.value.strip() or None,
            selections,
            append_console,
            busy_state=AppState.ARTING,
            on_done=after_art_save,
        )

    def do_art_upload_manual() -> None:
        files = art_tab.collect_manual_files()
        run_async(
            art_controller.upload_art_manual,
            import_tab.target_path.value.strip(),
            art_tab.game_name.value.strip() or None,
            art_tab.iso_filename.value.strip() or None,
            files,
            append_console,
            busy_state=AppState.ARTING,
            on_done=after_art_save,
        )

    def show_help(_: ft.ControlEvent) -> None:
        dialog = ft.AlertDialog(
            title=ft.Text(t("help_title")),
            content=ft.Column(
                [
                    ft.Text(t("help_step_1")),
                    ft.Text(t("help_step_2")),
                    ft.Text(t("help_step_3")),
                    ft.Text(t("help_step_4")),
                    ft.Text(t("help_step_5")),
                    ft.Text(t("help_step_6")),
                ],
                tight=True,
            ),
            actions=[ft.TextButton(t("close"), on_click=lambda _: close_dialog())],
        )
        page.dialog = dialog
        dialog.open = True
        page.update()

    def close_dialog() -> None:
        if page.dialog:
            page.dialog.open = False
            page.update()

    active_tab = {"value": "import"}

    tab_import_btn = ft.TextButton(t("tab_import"))
    tab_art_btn = ft.TextButton(t("tab_art"))
    tab_content = ft.Container(content=import_tab, expand=True)

    def apply_tab_styles() -> None:
        if active_tab["value"] == "import":
            tab_import_btn.style = ft.ButtonStyle(bgcolor=ft.Colors.CYAN_700, color=ft.Colors.WHITE)
            tab_art_btn.style = ft.ButtonStyle(bgcolor=ft.Colors.GREY_800, color=ft.Colors.WHITE)
            tab_content.content = import_tab
        else:
            tab_import_btn.style = ft.ButtonStyle(bgcolor=ft.Colors.GREY_800, color=ft.Colors.WHITE)
            tab_art_btn.style = ft.ButtonStyle(bgcolor=ft.Colors.CYAN_700, color=ft.Colors.WHITE)
            tab_content.content = art_tab

    def switch_tab(name: str) -> None:
        active_tab["value"] = name
        apply_tab_styles()
        page.update()

    tab_import_btn.on_click = lambda _: switch_tab("import")
    tab_art_btn.on_click = lambda _: switch_tab("art")

    def toggle_lang(_: ft.ControlEvent) -> None:
        i18n.set_lang("en" if i18n.get_lang() == "th" else "th")
        page.title = t("app_title")
        appbar_title.value = t("app_title")
        import_tab.translate()
        art_tab.translate()
        console.clear_log()
        console.set_status(t("status_ready"))
        console.set_state(store.current_state)
        tab_import_btn.text = t("tab_import")
        tab_art_btn.text = t("tab_art")
        apply_tab_styles()
        page.update()

    import_tab.validate_btn.on_click = lambda _: do_validate()
    import_tab.format_btn.on_click = lambda _: do_format()
    import_tab.import_btn.on_click = lambda _: do_import()
    import_tab.scan_btn.on_click = lambda _: do_scan()
    import_tab.cancel_btn.on_click = lambda _: do_cancel()
    art_tab.search_btn.on_click = lambda _: do_art_search()
    art_tab.save_auto_btn.on_click = lambda _: do_art_save_auto()
    art_tab.manual_upload_btn.on_click = lambda _: do_art_upload_manual()

    appbar_title = ft.Text(t("app_title"), weight=ft.FontWeight.BOLD)
    appbar = ft.AppBar(
        title=appbar_title,
        actions=[
            ft.IconButton(icon=ft.Icons.HELP_OUTLINE, on_click=show_help),
            ft.TextButton(i18n.get_lang().upper(), on_click=toggle_lang),
        ],
    )

    apply_tab_styles()

    tab_shell = ft.Column(
        expand=True,
        controls=[
            ft.Row([tab_import_btn, tab_art_btn], spacing=8, wrap=True),
            tab_content,
        ],
    )

    left_panel = ft.Container(content=tab_shell, padding=10, col={"xs": 12, "md": 7, "lg": 8})
    right_panel = ft.Container(content=console, padding=10, col={"xs": 12, "md": 5, "lg": 4})

    main_row = ft.ResponsiveRow(
        expand=True,
        spacing=0,
        run_spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.START,
        controls=[
            left_panel,
            right_panel,
        ],
    )

    page.appbar = appbar
    page.add(ft.Stack(expand=True, controls=[main_row, loading_overlay]))
    set_state(AppState.IDLE, t("status_ready"))
    page.update()
