"""Shared semantic tokens and compact Flet building blocks."""
import flet as ft

SURFACE = "#151B2C"
SURFACE_RAISED = "#1B2236"
BACKGROUND = "#0B0E18"
TEXT = "#F3F4F8"
MUTED = "#9AA2B6"
BORDER = "#30374B"
PRIMARY = "#E9A23B"
PRIMARY_SOFT = "#342719"
DESTRUCTIVE = "#FF727D"
WARNING = "#F2BF66"
SUCCESS = "#74D3AA"
SPACE = 20
RADIUS = 14


def heading(text: str) -> ft.Text:
    return ft.Text(text, size=28, weight=ft.FontWeight.BOLD, color=TEXT)


def panel(controls: list[ft.Control]) -> ft.Container:
    return ft.Container(
        padding=SPACE,
        bgcolor=SURFACE,
        border=ft.border.all(1, BORDER),
        border_radius=RADIUS,
        content=ft.Column(controls, spacing=14, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
    )


def eyebrow(text: str) -> ft.Text:
    return ft.Text(text.upper(), size=11, weight=ft.FontWeight.BOLD, color=PRIMARY)


def page_header(title: str, subtitle: str | None = None) -> ft.Column:
    controls: list[ft.Control] = [heading(title)]
    if subtitle:
        controls.append(ft.Text(subtitle, size=14, color=MUTED))
    return ft.Column(controls, spacing=5, tight=True)


def danger_style() -> ft.ButtonStyle:
    return ft.ButtonStyle(color=DESTRUCTIVE, side=ft.BorderSide(1, DESTRUCTIVE))


def app_theme() -> ft.Theme:
    return ft.Theme(color_scheme_seed=PRIMARY,
                    color_scheme=ft.ColorScheme(primary=PRIMARY, on_primary=BACKGROUND,
                                                surface=SURFACE, on_surface=TEXT,
                                                on_surface_variant=MUTED, error=DESTRUCTIVE,
                                                outline=BORDER),
                    visual_density=ft.VisualDensity.COMPACT)
