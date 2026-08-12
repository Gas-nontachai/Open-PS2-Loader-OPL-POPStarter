from __future__ import annotations

STRINGS = {
    "th": {
        "volume_label": "ชื่อไดรฟ์หลังฟอร์แมต",
        "format_title": "ฟอร์แมตที่เก็บข้อมูลภายนอก",
        "cancel": "ยกเลิก",
        "confirm": "ยืนยัน",
        "delete": "ลบ",
    },
    "en": {
        "volume_label": "Volume label after formatting",
        "format_title": "Format External Storage",
        "cancel": "Cancel",
        "confirm": "Confirm",
        "delete": "Delete",
    },
}

_current_lang = "en"


def set_lang(language: str) -> None:
    global _current_lang
    _current_lang = language if language in STRINGS else "th"


def get_lang() -> str:
    return _current_lang


def t(key: str) -> str:
    return STRINGS[_current_lang].get(key, key)
