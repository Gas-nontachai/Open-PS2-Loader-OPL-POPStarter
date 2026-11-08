from __future__ import annotations

def retained_device(records: list[dict], path: str, identity: str) -> dict | None:
    """Refreshing is discovery, never consent to select another physical disk."""
    return next((record for record in records
                 if identity and record["path"] == path and record["device_id"] == identity), None)
