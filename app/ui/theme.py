"""Shared semantic tokens and compact Flet building blocks."""
import flet as ft

SURFACE = "#151D29"
BACKGROUND = "#0E141E"
TEXT = "#E8EEF6"
MUTED = "#B0BDCE"
BORDER = "#44556B"
PRIMARY = "#8DD9E7"
DESTRUCTIVE = "#FFB4AB"
WARNING = "#FFD18A"
SUCCESS = "#A3D6AE"
SPACE = 16
RADIUS = 8


def heading(text: str) -> ft.Text:
    return ft.Text(text, size=28, weight=ft.FontWeight.BOLD, color=TEXT)


def panel(controls: list[ft.Control]) -> ft.Container:
    return ft.Container(padding=SPACE, bgcolor=SURFACE,
                        border=ft.border.all(1, BORDER), border_radius=RADIUS,
                        content=ft.Column(controls, spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH))


def danger_style() -> ft.ButtonStyle:
    return ft.ButtonStyle(color=DESTRUCTIVE, side=ft.BorderSide(1, DESTRUCTIVE))


def app_theme() -> ft.Theme:
    return ft.Theme(color_scheme_seed=PRIMARY,
                    color_scheme=ft.ColorScheme(primary=PRIMARY, on_primary=BACKGROUND,
                                                surface=SURFACE, on_surface=TEXT,
                                                on_surface_variant=MUTED, error=DESTRUCTIVE,
                                                outline=BORDER),
                    visual_density=ft.VisualDensity.STANDARD)
