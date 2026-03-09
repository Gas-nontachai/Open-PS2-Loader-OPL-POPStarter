from __future__ import annotations

import threading
from enum import Enum


class AppState(str, Enum):
    IDLE = "IDLE"
    VALIDATING = "VALIDATING"
    VALIDATED = "VALIDATED"
    FORMATTING = "FORMATTING"
    IMPORTING = "IMPORTING"
    ARTING = "ARTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TRANSITIONS = {
    AppState.IDLE: {AppState.VALIDATING, AppState.FORMATTING, AppState.IMPORTING, AppState.ARTING, AppState.CANCELLED},
    AppState.VALIDATING: {AppState.VALIDATED, AppState.FAILED, AppState.CANCELLED},
    AppState.VALIDATED: {AppState.FORMATTING, AppState.IMPORTING, AppState.ARTING, AppState.IDLE, AppState.FAILED},
    AppState.FORMATTING: {AppState.COMPLETED, AppState.FAILED, AppState.CANCELLED, AppState.VALIDATED},
    AppState.IMPORTING: {AppState.COMPLETED, AppState.FAILED, AppState.CANCELLED, AppState.VALIDATED},
    AppState.ARTING: {AppState.COMPLETED, AppState.FAILED, AppState.CANCELLED, AppState.VALIDATED},
    AppState.COMPLETED: {AppState.IDLE, AppState.VALIDATED, AppState.ARTING, AppState.IMPORTING},
    AppState.FAILED: {AppState.IDLE, AppState.VALIDATED, AppState.VALIDATING},
    AppState.CANCELLED: {AppState.IDLE, AppState.VALIDATED, AppState.VALIDATING},
}


PROGRESS_MAP = {
    AppState.IDLE: 0.0,
    AppState.VALIDATING: 0.2,
    AppState.VALIDATED: 0.35,
    AppState.FORMATTING: 0.5,
    AppState.IMPORTING: 0.7,
    AppState.ARTING: 0.8,
    AppState.COMPLETED: 1.0,
    AppState.FAILED: 1.0,
    AppState.CANCELLED: 0.0,
}


class AppStore:
    def __init__(self) -> None:
        self.current_state = AppState.IDLE
        self.is_loading = False
        self.scanned_games: list[dict] = []
        self.storage_summary: dict = {}
        self.art_candidates: list[dict] = []
        self.art_source_choices: list[dict] = []
        self.cancel_event = threading.Event()
        self.target_path = ""

    def set_state(self, new_state: AppState) -> None:
        allowed = TRANSITIONS.get(self.current_state, set())
        if new_state != self.current_state and new_state not in allowed:
            raise ValueError(f"invalid transition: {self.current_state} -> {new_state}")
        self.current_state = new_state

    def reset(self) -> None:
        self.current_state = AppState.IDLE
        self.is_loading = False
        self.scanned_games.clear()
        self.storage_summary = {}
        self.art_candidates.clear()
        self.art_source_choices.clear()
        self.cancel_event.clear()

    def request_cancel(self) -> None:
        self.cancel_event.set()

    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()
