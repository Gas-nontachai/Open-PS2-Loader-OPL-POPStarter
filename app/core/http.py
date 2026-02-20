from __future__ import annotations

from typing import Any, Optional

from fastapi.responses import JSONResponse


def step(state: str, status: str, message: str, details: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "state": state,
        "status": status,
        "message": message,
    }
    if details:
        payload["details"] = details
    return payload


def api_response(
    status: str,
    state: str,
    message: str,
    details: Optional[dict[str, Any]] = None,
    next_action: Optional[str] = None,
    steps: Optional[list[dict[str, Any]]] = None,
    status_code: int = 200,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "status": status,
            "state": state,
            "message": message,
            "details": details or {},
            "next_action": next_action,
            "steps": steps or [],
        },
    )
