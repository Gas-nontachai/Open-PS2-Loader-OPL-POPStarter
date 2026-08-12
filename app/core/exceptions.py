from __future__ import annotations


class AppError(Exception):
    """A failure that can be shown to an end user without a traceback."""


class InvalidIsoError(AppError):
    pass


class InsufficientSpaceError(AppError):
    pass


class DuplicateGameError(AppError):
    pass


class OperationCancelledError(AppError):
    pass


class UnsafeDriveError(AppError):
    pass
