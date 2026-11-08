"""Flet tab compatibility for the supported Python 3.9 runtime."""
import flet as ft
from flet.core.adaptive_control import AdaptiveControl
from flet.core.types import IconEnums


class WorkspaceTab(ft.Tab):
    def before_update(self):
        # shortcut: Flet 0.25.2 checks isinstance against typing.Union; remove after a fixed Flet upgrade.
        AdaptiveControl.before_update(self)
        self._set_attr_json("iconMargin", self.icon_margin)
        if isinstance(self.icon, (str, *IconEnums)):
            self._set_enum_attr("icon", self.icon, IconEnums)
