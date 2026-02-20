from __future__ import annotations

import os
import platform
import plistlib
import json
import hashlib
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import pycdlib

load_dotenv()

REQUIRED_FOLDERS = ["APPS", "ART", "CD", "CFG", "CHT", "DVD", "LNG", "POPS", "THM", "VMC"]
CD_THRESHOLD_BYTES = 700 * 1024 * 1024
SPACE_BUFFER_MIN_BYTES = 500 * 1024 * 1024
SPACE_BUFFER_RATIO = 0.05
ART_TYPES = ["COV", "COV2", "BG", "SCR", "SCR2", "LGO", "ICO", "LAB"]
ART_EXT_HINT = {
    "COV": ".jpg",
    "COV2": ".jpg",
    "BG": ".jpg",
    "SCR": ".jpg",
    "SCR2": ".jpg",
    "LGO": ".png",
    "ICO": ".png",
    "LAB": ".jpg",
}
ART_ALLOWED_EXT = {".jpg", ".jpeg", ".png"}
RAWG_SEARCH_ENDPOINT = "https://api.rawg.io/api/games"
ART_SEARCH_CACHE_TTL_SEC = int(os.getenv("ART_SEARCH_CACHE_TTL_SEC", "1800"))
ART_SEARCH_CACHE_MAX_SIZE = int(os.getenv("ART_SEARCH_CACHE_MAX_SIZE", "200"))
ART_SEARCH_RATE_LIMIT_PER_MIN = int(os.getenv("ART_SEARCH_RATE_LIMIT_PER_MIN", "30"))
ART_SEARCH_MIN_INTERVAL_SEC = float(os.getenv("ART_SEARCH_MIN_INTERVAL_SEC", "1.5"))
_ART_SEARCH_CACHE: dict[str, dict[str, Any]] = {}
_ART_SEARCH_CLIENT_LIMITS: dict[str, dict[str, Any]] = {}
_ART_SEARCH_LOCK = threading.Lock()


class ValidateTargetRequest(BaseModel):
    target_path: str = Field(min_length=1)
    ensure_folders: bool = True


class FormatTargetRequest(BaseModel):
    target_path: str = Field(min_length=1)
    confirm_phrase: str = Field(min_length=1)
    volume_label: str = "PS2USB"


class ArtSearchRequest(BaseModel):
    target_path: Optional[str] = None
    game_name: Optional[str] = None
    source_filename: Optional[str] = None
    max_results: int = Field(default=10, ge=1, le=10)


class ArtSelection(BaseModel):
    art_type: str = Field(min_length=1)
    image_url: str = Field(min_length=1)


class ArtSaveRequest(BaseModel):
    target_path: str = Field(min_length=1)
    game_name: Optional[str] = None
    source_filename: Optional[str] = None
    selections: list[ArtSelection]


app = FastAPI(title="PS2 ISO Importer")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def _step(state: str, status: str, message: str, details: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "state": state,
        "status": status,
        "message": message,
    }
    if details:
        payload["details"] = details
    return payload


def _response(
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


def _resolve_target(target_path: str) -> Path:
    return Path(target_path).expanduser().resolve()


def _validate_target_access(target: Path) -> tuple[bool, str]:
    if not target.exists():
        return False, "target path does not exist"
    if not target.is_dir():
        return False, "target path is not a directory"
    if not os.access(target, os.R_OK | os.W_OK | os.X_OK):
        return False, "target path is not writable"
    return True, "ok"


def _ensure_required_folders(target: Path) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    created: list[str] = []
    for folder in REQUIRED_FOLDERS:
        folder_path = target / folder
        if folder_path.exists() and not folder_path.is_dir():
            raise NotADirectoryError(f"required path exists but is not a directory: {folder_path}")
        if not folder_path.exists():
            missing.append(folder)
            folder_path.mkdir(parents=True, exist_ok=True)
            created.append(folder)
    return missing, created


def _compute_buffer(total_iso_bytes: int) -> int:
    return max(int(total_iso_bytes * SPACE_BUFFER_RATIO), SPACE_BUFFER_MIN_BYTES)


def _human_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{size} B"


def _sanitize_volume_label(label: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_-]", "", label).upper()
    if not sanitized:
        sanitized = "PS2USB"
    return sanitized[:11]


def _run_cmd(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=False, capture_output=True, text=True)


def _diskutil_info(path_or_device: str) -> dict[str, Any]:
    result = _run_cmd(["diskutil", "info", "-plist", path_or_device])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"diskutil info failed for {path_or_device}")
    return plistlib.loads(result.stdout.encode("utf-8"))


def _validate_format_target(path: Path) -> tuple[str, dict[str, Any], dict[str, Any]]:
    info = _diskutil_info(str(path))
    whole_disk = info.get("ParentWholeDisk") or info.get("DeviceIdentifier")
    if not whole_disk:
        raise RuntimeError("could not identify disk device from target path")

    whole_info = _diskutil_info(f"/dev/{whole_disk}")
    if whole_info.get("Internal", True):
        raise RuntimeError("refusing to format an internal disk")
    if not (whole_info.get("RemovableMedia", False) or info.get("RemovableMedia", False)):
        raise RuntimeError("target is not marked as removable media")

    return whole_disk, info, whole_info


def _wait_mount_point(device: str, retries: int = 12, delay_sec: float = 0.5) -> Path:
    for _ in range(retries):
        list_result = _run_cmd(["diskutil", "list", "-plist", f"/dev/{device}"])
        if list_result.returncode == 0:
            parsed = plistlib.loads(list_result.stdout.encode("utf-8"))
            partitions = parsed.get("Partitions", [])
            for partition in partitions:
                mount_point = partition.get("MountPoint")
                if mount_point:
                    return Path(mount_point)
        time.sleep(delay_sec)
    raise RuntimeError("formatted volume did not mount in time")


def _normalize_game_id(game_id: str) -> str:
    normalized = game_id.strip().upper()
    if not re.fullmatch(r"[A-Z]{4}_[0-9]{3}\.[0-9]{2}", normalized):
        raise ValueError("game_id must match pattern like SLUS_209.46")
    return normalized


def _generate_game_id(seed: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "", seed).upper()
    if len(cleaned) < 4:
        cleaned = (cleaned + "AUTO")[:4]
    prefix = cleaned[:4]
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    number = int(digest[:5], 16) % 100000
    return f"{prefix}_{number // 100:03d}.{number % 100:02d}"


def _resolve_game_id(game_id: Optional[str], seed: Optional[str]) -> tuple[str, bool]:
    if game_id and game_id.strip():
        return _normalize_game_id(game_id), False
    base = (seed or "").strip() or "AUTO_GAME"
    return _generate_game_id(base), True


def _extract_game_id_from_system_cnf(content: str) -> Optional[str]:
    match = re.search(r"([A-Z]{4}_[0-9]{3}\.[0-9]{2})", content.upper())
    if not match:
        return None
    return match.group(1)


def _extract_game_id_from_iso(iso_path: Path) -> Optional[str]:
    iso = pycdlib.PyCdlib()
    try:
        iso.open(str(iso_path))
        candidates = ["/SYSTEM.CNF;1", "/SYSTEM.CNF"]
        system_cnf_text: Optional[str] = None
        for candidate in candidates:
            try:
                import io

                buffer = io.BytesIO()
                iso.get_file_from_iso_fp(buffer, iso_path=candidate)
                system_cnf_text = buffer.getvalue().decode("utf-8", errors="ignore")
                if system_cnf_text.strip():
                    break
            except Exception:
                continue
        if not system_cnf_text:
            return None
        return _extract_game_id_from_system_cnf(system_cnf_text)
    except Exception:
        return None
    finally:
        try:
            iso.close()
        except Exception:
            pass


def _normalize_lookup_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _manifest_path(target: Path) -> Path:
    return target / "CFG" / "game_manifest.json"


def _load_manifest(target: Path) -> dict[str, Any]:
    manifest_file = _manifest_path(target)
    if not manifest_file.exists():
        return {"entries": []}
    try:
        with manifest_file.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception:
        return {"entries": []}
    if not isinstance(payload, dict):
        return {"entries": []}
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        return {"entries": []}
    return {"entries": entries}


def _save_manifest(target: Path, manifest: dict[str, Any]) -> None:
    manifest_file = _manifest_path(target)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    with manifest_file.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=True, indent=2)


def _upsert_manifest_entry(
    target: Path,
    source_filename: str,
    game_name: str,
    game_id: str,
    id_source: str,
    target_folder: str,
    destination_filename: str,
) -> None:
    manifest = _load_manifest(target)
    entries = manifest.get("entries", [])
    source_key = _normalize_lookup_key(Path(source_filename).stem)
    destination_key = _normalize_lookup_key(Path(destination_filename).stem)
    game_key = _normalize_lookup_key(game_name)
    updated = False
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if (
            entry.get("source_key") == source_key
            or entry.get("source_filename") == source_filename
            or entry.get("destination_key") == destination_key
            or entry.get("destination_filename") == destination_filename
        ):
            entry.update(
                {
                    "source_filename": source_filename,
                    "source_key": source_key,
                    "game_name": game_name,
                    "game_name_key": game_key,
                    "game_id": game_id,
                    "id_source": id_source,
                    "target_folder": target_folder,
                    "destination_filename": destination_filename,
                    "destination_key": destination_key,
                    "updated_at": int(time.time()),
                }
            )
            updated = True
            break
    if not updated:
        entries.append(
            {
                "source_filename": source_filename,
                "source_key": source_key,
                "game_name": game_name,
                "game_name_key": game_key,
                "game_id": game_id,
                "id_source": id_source,
                "target_folder": target_folder,
                "destination_filename": destination_filename,
                "destination_key": destination_key,
                "updated_at": int(time.time()),
            }
        )
    manifest["entries"] = entries
    _save_manifest(target, manifest)


def _lookup_game_id_from_manifest(target: Path, source_filename: Optional[str], game_name: Optional[str]) -> Optional[str]:
    manifest = _load_manifest(target)
    entries = manifest.get("entries", [])
    source_key = _normalize_lookup_key(Path(source_filename).stem) if source_filename else ""
    source_name = source_filename.strip() if source_filename else ""
    game_key = _normalize_lookup_key(game_name) if game_name else ""
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if source_key and (entry.get("source_key") == source_key or entry.get("destination_key") == source_key):
            game_id = entry.get("game_id")
            if isinstance(game_id, str) and game_id:
                return game_id
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if source_name and (entry.get("source_filename") == source_name or entry.get("destination_filename") == source_name):
            game_id = entry.get("game_id")
            if isinstance(game_id, str) and game_id:
                return game_id
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if game_key and entry.get("game_name_key") == game_key:
            game_id = entry.get("game_id")
            if isinstance(game_id, str) and game_id:
                return game_id
    return None


def _extract_game_id_from_filename(source_filename: Optional[str]) -> Optional[str]:
    if not source_filename:
        return None
    name = Path(source_filename).name
    match = re.match(r"^([A-Z]{4}_[0-9]{3}\.[0-9]{2})_", name.upper())
    if not match:
        return None
    return match.group(1)


def _resolve_game_id_for_target(target: Optional[Path], game_name: Optional[str], source_filename: Optional[str]) -> tuple[str, bool, str]:
    from_filename = _extract_game_id_from_filename(source_filename)
    if from_filename:
        return from_filename, False, "filename"
    if target:
        matched = _lookup_game_id_from_manifest(target, source_filename, game_name)
        if matched:
            return matched, False, "manifest"
    seed = (game_name or "").strip() or (source_filename or "").strip()
    game_id, generated = _resolve_game_id(None, seed)
    return game_id, generated, "generated"


def _derive_game_name(game_name: Optional[str], source_filename: Optional[str]) -> str:
    if game_name and game_name.strip():
        return game_name.strip()
    if not source_filename or not source_filename.strip():
        raise ValueError("game_name or source_filename is required")

    stem = Path(source_filename.strip()).stem
    stem = re.sub(r"^[A-Z]{4}_[0-9]{3}\.[0-9]{2}[_\-\s.]*", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"[_\-.]+", " ", stem).strip()
    if not stem:
        raise ValueError("could not derive game name from source filename")
    return stem


def _rawg_api_key() -> str:
    key = os.getenv("RAWG_API_KEY", "").strip()
    if not key:
        raise RuntimeError("missing RAWG_API_KEY")
    return key


def _art_search_cache_key(provider: str, game_id: str, query: str, max_results: int) -> str:
    return f"{provider}|{game_id}|{query.lower()}|{max_results}"


def _get_cached_art_search(cache_key: str, now_ts: float) -> Optional[list[dict[str, Any]]]:
    with _ART_SEARCH_LOCK:
        entry = _ART_SEARCH_CACHE.get(cache_key)
        if not entry:
            return None
        if now_ts - entry["ts"] > ART_SEARCH_CACHE_TTL_SEC:
            _ART_SEARCH_CACHE.pop(cache_key, None)
            return None
        return entry["candidates"]


def _store_cached_art_search(cache_key: str, candidates: list[dict[str, Any]], now_ts: float) -> None:
    with _ART_SEARCH_LOCK:
        _ART_SEARCH_CACHE[cache_key] = {"ts": now_ts, "candidates": candidates}
        if len(_ART_SEARCH_CACHE) > ART_SEARCH_CACHE_MAX_SIZE:
            oldest_key = min(_ART_SEARCH_CACHE.items(), key=lambda kv: kv[1]["ts"])[0]
            _ART_SEARCH_CACHE.pop(oldest_key, None)


def _enforce_art_search_rate_limit(client_id: str, now_ts: float) -> tuple[bool, str, int]:
    with _ART_SEARCH_LOCK:
        limiter = _ART_SEARCH_CLIENT_LIMITS.get(client_id)
        if not limiter:
            limiter = {"window_start": now_ts, "count": 0, "last_ts": 0.0}
            _ART_SEARCH_CLIENT_LIMITS[client_id] = limiter

        if now_ts - float(limiter["window_start"]) >= 60:
            limiter["window_start"] = now_ts
            limiter["count"] = 0

        since_last = now_ts - float(limiter["last_ts"])
        if since_last < ART_SEARCH_MIN_INTERVAL_SEC:
            retry_after = max(1, int(ART_SEARCH_MIN_INTERVAL_SEC - since_last + 0.999))
            return False, "too many requests; please slow down", retry_after

        if int(limiter["count"]) >= ART_SEARCH_RATE_LIMIT_PER_MIN:
            elapsed = now_ts - float(limiter["window_start"])
            retry_after = max(1, int(60 - elapsed + 0.999))
            return False, "rate limit reached for art search", retry_after

        limiter["count"] = int(limiter["count"]) + 1
        limiter["last_ts"] = now_ts
        return True, "", 0


def _search_rawg_images(query: str, max_results: int) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "key": _rawg_api_key(),
            "search": query,
            "page_size": max_results,
        }
    )
    req = urllib.request.Request(
        f"{RAWG_SEARCH_ENDPOINT}?{params}",
        headers={"User-Agent": "PS2-ISO-Importer/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"rawg api error: {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"rawg api connection error: {exc.reason}") from exc

    results = payload.get("results", [])
    candidates: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    idx = 1
    for game in results:
        name = str(game.get("name", "")).strip() or "RAWG Game"
        for image_url in [game.get("background_image"), game.get("background_image_additional")]:
            image = str(image_url or "").strip()
            if not image.startswith(("http://", "https://")):
                continue
            if image in seen_urls:
                continue
            seen_urls.add(image)
            candidates.append(
                {
                    "candidate_id": idx,
                    "title": f"{name} (RAWG)",
                    "image_url": image,
                    "thumbnail_url": image,
                    "source_page": game.get("website") or f"https://rawg.io/games/{game.get('slug', '')}",
                }
            )
            idx += 1
            if len(candidates) >= max_results:
                return candidates
    return candidates


def _search_art_candidates(query: str, max_results: int) -> tuple[str, list[dict[str, Any]]]:
    return "rawg", _search_rawg_images(query, max_results)


def _guess_ext(image_url: str, content_type: Optional[str], art_type: str) -> str:
    ctype = (content_type or "").lower()
    if "png" in ctype:
        return ".png"
    if "jpeg" in ctype or "jpg" in ctype:
        return ".jpg"

    parsed_path = Path(urllib.parse.urlparse(image_url).path)
    ext = parsed_path.suffix.lower()
    if ext in ART_ALLOWED_EXT:
        return ".jpg" if ext == ".jpeg" else ext
    return ART_EXT_HINT[art_type]


def _download_image(image_url: str, art_type: str) -> tuple[bytes, str]:
    if not image_url.startswith(("http://", "https://")):
        raise ValueError("image_url must start with http:// or https://")

    req = urllib.request.Request(image_url, headers={"User-Agent": "PS2-ISO-Importer/1.0"})
    with urllib.request.urlopen(req, timeout=25) as response:
        content = response.read()
        content_type = response.headers.get("Content-Type")

    if not content:
        raise ValueError("downloaded image is empty")
    if len(content) > 20 * 1024 * 1024:
        raise ValueError("downloaded image is too large")

    ext = _guess_ext(image_url, content_type, art_type)
    if ext not in {".jpg", ".png"}:
        raise ValueError("unsupported image extension")
    return content, ext


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/pick-target-folder")
async def pick_target_folder():
    steps: list[dict[str, Any]] = []
    try:
        if platform.system().lower() != "darwin":
            return _response(
                status="error",
                state="failed",
                message="folder picker is supported only on macOS",
                details={},
                next_action="enter_path_manually",
                steps=steps,
                status_code=400,
            )

        result = _run_cmd(
            [
                "osascript",
                "-e",
                'POSIX path of (choose folder with prompt "Select PS2 target parent folder")',
            ]
        )
        if result.returncode != 0:
            error_text = (result.stderr or result.stdout).strip()
            if "User canceled" in error_text:
                return _response(
                    status="error",
                    state="cancelled",
                    message="folder selection cancelled",
                    details={},
                    next_action="retry_or_enter_path_manually",
                    steps=steps,
                    status_code=400,
                )
            return _response(
                status="error",
                state="failed",
                message="failed to open folder picker",
                details={"error": error_text},
                next_action="retry_or_enter_path_manually",
                steps=steps,
                status_code=500,
            )

        selected = result.stdout.strip()
        return _response(
            status="success",
            state="completed",
            message="folder selected",
            details={"target": selected},
            next_action="ready_to_validate",
            steps=steps,
        )
    except Exception as exc:  # noqa: BLE001
        return _response(
            status="error",
            state="failed",
            message="unexpected error during folder pick",
            details={"error": str(exc)},
            next_action="retry_or_enter_path_manually",
            steps=steps,
            status_code=500,
        )


@app.post("/api/format-target")
async def format_target(payload: FormatTargetRequest):
    steps: list[dict[str, Any]] = []
    try:
        if platform.system().lower() != "darwin":
            steps.append(_step("formatting", "error", "format endpoint currently supports macOS only"))
            return _response(
                status="error",
                state="failed",
                message="formatting is supported only on macOS",
                details={},
                next_action="use_macos_or_format_manually",
                steps=steps,
                status_code=400,
            )

        if payload.confirm_phrase.strip().upper() != "FORMAT":
            steps.append(_step("formatting", "error", "invalid confirm phrase"))
            return _response(
                status="error",
                state="failed",
                message="confirmation phrase mismatch",
                details={"expected": "FORMAT"},
                next_action="confirm_with_format_phrase",
                steps=steps,
                status_code=400,
            )

        target = _resolve_target(payload.target_path)
        steps.append(_step("formatting", "info", "resolving target path", {"target": str(target)}))
        if not target.exists():
            steps.append(_step("formatting", "error", "target path does not exist"))
            return _response(
                status="error",
                state="failed",
                message="target path does not exist",
                details={"target": str(target)},
                next_action="provide_valid_target_path",
                steps=steps,
                status_code=400,
            )

        steps.append(_step("formatting", "info", "inspecting disk metadata"))
        disk_device, volume_info, whole_info = _validate_format_target(target)
        steps.append(
            _step(
                "formatting",
                "info",
                "target disk validated",
                {
                    "device": disk_device,
                    "volume_name": volume_info.get("VolumeName"),
                    "bus_protocol": whole_info.get("BusProtocol"),
                },
            )
        )

        label = _sanitize_volume_label(payload.volume_label)
        steps.append(
            _step(
                "formatting",
                "info",
                "erasing disk as FAT32 (MBR)",
                {"device": disk_device, "label": label},
            )
        )
        erase_result = _run_cmd(["diskutil", "eraseDisk", "MS-DOS", label, "MBRFormat", f"/dev/{disk_device}"])
        if erase_result.returncode != 0:
            steps.append(
                _step(
                    "formatting",
                    "error",
                    "diskutil erase failed",
                    {"stderr": erase_result.stderr.strip()},
                )
            )
            return _response(
                status="error",
                state="failed",
                message="format command failed",
                details={"error": erase_result.stderr.strip()},
                next_action="check_permissions_and_retry",
                steps=steps,
                status_code=500,
            )

        mounted_path = _wait_mount_point(disk_device)
        steps.append(
            _step(
                "formatting",
                "success",
                "disk formatted and mounted",
                {"mount_point": str(mounted_path), "device": disk_device, "label": label},
            )
        )

        try:
            missing, created = _ensure_required_folders(mounted_path)
        except NotADirectoryError as exc:
            steps.append(_step("ensuring_structure", "error", str(exc)))
            return _response(
                status="error",
                state="failed",
                message="formatted volume has invalid structure",
                details={"error": str(exc)},
                next_action="retry_format",
                steps=steps,
                status_code=500,
            )

        steps.append(
            _step(
                "ensuring_structure",
                "success",
                "required folders are ready after format",
                {"missing_before": missing, "created": created},
            )
        )

        return _response(
            status="success",
            state="completed",
            message="usb formatted and prepared successfully",
            details={"target": str(mounted_path), "label": label, "device": disk_device, "created": created},
            next_action="ready_to_import",
            steps=steps,
        )
    except Exception as exc:  # noqa: BLE001
        steps.append(_step("failed", "error", "unexpected error", {"error": str(exc)}))
        return _response(
            status="error",
            state="failed",
            message="unexpected error during format",
            details={"error": str(exc)},
            next_action="retry",
            steps=steps,
            status_code=500,
        )


@app.post("/api/validate-target")
async def validate_target(payload: ValidateTargetRequest):
    steps: list[dict[str, Any]] = []
    try:
        target = _resolve_target(payload.target_path)
        steps.append(_step("validating_target", "info", "checking target path", {"target": str(target)}))

        ok, reason = _validate_target_access(target)
        if not ok:
            steps.append(_step("validating_target", "error", reason))
            return _response(
                status="error",
                state="failed",
                message="target validation failed",
                details={"target": str(target), "reason": reason},
                next_action="fix_target_path_or_permissions",
                steps=steps,
                status_code=400,
            )

        missing: list[str] = []
        created: list[str] = []
        if payload.ensure_folders:
            steps.append(_step("ensuring_structure", "info", "ensuring required folders"))
            try:
                missing, created = _ensure_required_folders(target)
            except NotADirectoryError as exc:
                steps.append(_step("ensuring_structure", "error", str(exc)))
                return _response(
                    status="error",
                    state="failed",
                    message="invalid target structure",
                    details={"error": str(exc)},
                    next_action="fix_target_structure_then_retry",
                    steps=steps,
                    status_code=400,
                )
            steps.append(
                _step(
                    "ensuring_structure",
                    "success",
                    "required folders are ready",
                    {"missing_before": missing, "created": created},
                )
            )

        existing = sorted([f for f in REQUIRED_FOLDERS if (target / f).exists()])
        steps.append(_step("validated", "success", "target is ready"))
        return _response(
            status="success",
            state="validated",
            message="target path is valid and ready",
            details={
                "target": str(target),
                "required_folders": REQUIRED_FOLDERS,
                "existing": existing,
                "created": created,
            },
            next_action="ready_to_import",
            steps=steps,
        )
    except Exception as exc:  # noqa: BLE001
        steps.append(_step("failed", "error", "unexpected error", {"error": str(exc)}))
        return _response(
            status="error",
            state="failed",
            message="unexpected error during validation",
            details={"error": str(exc)},
            next_action="retry",
            steps=steps,
            status_code=500,
        )


@app.post("/api/art/search")
async def search_art(payload: ArtSearchRequest, request: Request):
    steps: list[dict[str, Any]] = []
    try:
        game_query = _derive_game_name(payload.game_name, payload.source_filename)
        target: Optional[Path] = None
        if payload.target_path and payload.target_path.strip():
            target = _resolve_target(payload.target_path)
        game_id, generated, id_source = _resolve_game_id_for_target(target, game_query, payload.source_filename)
        query = f"{game_query} PS2 cover art"
        now_ts = time.time()
        provider_name = "rawg"
        cache_key = _art_search_cache_key(provider_name, game_id, query, payload.max_results)
        cached = _get_cached_art_search(cache_key, now_ts)
        if cached is not None:
            steps.append(
                _step(
                    "searching_art",
                    "success",
                    "loaded art candidates from cache",
                    {"count": len(cached), "provider": provider_name},
                )
            )
            return _response(
                status="success",
                state="searching_art",
                message="art candidates ready for preview",
                details={
                    "game_id": game_id,
                    "generated_game_id": generated,
                    "id_source": id_source,
                    "game_query": game_query,
                    "art_types": ART_TYPES,
                    "candidates": cached,
                    "cache_hit": True,
                    "provider_used": provider_name,
                },
                next_action="preview_and_select_images",
                steps=steps,
            )

        client_id = request.client.host if request.client else "unknown"
        allowed, reason, retry_after = _enforce_art_search_rate_limit(client_id, now_ts)
        if not allowed:
            return _response(
                status="error",
                state="failed",
                message=reason,
                details={"retry_after_seconds": retry_after},
                next_action="wait_then_retry",
                steps=steps,
                status_code=429,
            )

        steps.append(_step("searching_art", "info", "searching images", {"query": query, "provider": provider_name}))
        provider_used, candidates = _search_art_candidates(query, payload.max_results)
        if not candidates:
            steps.append(_step("searching_art", "error", "no image candidates found"))
            return _response(
                status="error",
                state="failed",
                message="no art candidates found",
                details={"query": query},
                next_action="try_another_game_name",
                steps=steps,
                status_code=404,
            )

        cache_key = _art_search_cache_key(provider_used, game_id, query, payload.max_results)
        _store_cached_art_search(cache_key, candidates, now_ts)
        steps.append(_step("searching_art", "success", "art candidates found", {"count": len(candidates)}))
        return _response(
            status="success",
            state="searching_art",
            message="art candidates ready for preview",
            details={
                "game_id": game_id,
                "generated_game_id": generated,
                "id_source": id_source,
                "game_query": game_query,
                "art_types": ART_TYPES,
                "candidates": candidates,
                "cache_hit": False,
                "provider_used": provider_used,
            },
            next_action="preview_and_select_images",
            steps=steps,
        )
    except ValueError as exc:
        return _response(
            status="error",
            state="failed",
            message=str(exc),
            details={},
            next_action="fix_request_and_retry",
            steps=steps,
            status_code=400,
        )
    except RuntimeError as exc:
        return _response(
            status="error",
            state="failed",
            message=str(exc),
            details={},
            next_action="set_rawg_api_key_then_retry",
            steps=steps,
            status_code=400,
        )
    except Exception as exc:  # noqa: BLE001
        steps.append(_step("failed", "error", "unexpected error", {"error": str(exc)}))
        return _response(
            status="error",
            state="failed",
            message="unexpected error during art search",
            details={"error": str(exc)},
            next_action="check_api_config_or_retry",
            steps=steps,
            status_code=500,
        )


@app.post("/api/art/manual")
async def upload_art_manual(
    target_path: str = Form(...),
    game_name: str = Form(""),
    source_filename: str = Form(""),
    cov: Optional[UploadFile] = File(None),
    cov2: Optional[UploadFile] = File(None),
    bg: Optional[UploadFile] = File(None),
    scr: Optional[UploadFile] = File(None),
    scr2: Optional[UploadFile] = File(None),
    lgo: Optional[UploadFile] = File(None),
    ico: Optional[UploadFile] = File(None),
    lab: Optional[UploadFile] = File(None),
):
    steps: list[dict[str, Any]] = []
    try:
        target = _resolve_target(target_path)
        normalized_game_id, generated, id_source = _resolve_game_id_for_target(target, game_name.strip(), source_filename.strip())
        ok, reason = _validate_target_access(target)
        if not ok:
            return _response(
                status="error",
                state="failed",
                message="target validation failed",
                details={"target": str(target), "reason": reason},
                next_action="fix_target_path_or_permissions",
                steps=steps,
                status_code=400,
            )

        _ensure_required_folders(target)
        art_dir = target / "ART"

        uploads = {
            "COV": cov,
            "COV2": cov2,
            "BG": bg,
            "SCR": scr,
            "SCR2": scr2,
            "LGO": lgo,
            "ICO": ico,
            "LAB": lab,
        }

        saved: list[dict[str, str]] = []
        for art_type, upload in uploads.items():
            if not upload or not upload.filename:
                continue
            src_ext = Path(upload.filename).suffix.lower()
            if src_ext not in ART_ALLOWED_EXT:
                return _response(
                    status="error",
                    state="failed",
                    message=f"unsupported extension for {art_type}",
                    details={"file": upload.filename, "allowed": sorted(ART_ALLOWED_EXT)},
                    next_action="upload_png_or_jpg",
                    steps=steps,
                    status_code=400,
                )

            dst_ext = ".jpg" if src_ext == ".jpeg" else src_ext
            dst = art_dir / f"{normalized_game_id}_{art_type}{dst_ext}"
            with dst.open("wb") as fh:
                shutil.copyfileobj(upload.file, fh)
            await upload.close()
            saved.append({"art_type": art_type, "path": str(dst)})

        if not saved:
            return _response(
                status="error",
                state="failed",
                message="no art files provided",
                details={},
                next_action="upload_at_least_one_art_file",
                steps=steps,
                status_code=400,
            )

        return _response(
            status="success",
            state="completed",
            message="manual art upload completed",
            details={
                "game_id": normalized_game_id,
                "generated_game_id": generated,
                "id_source": id_source,
                "saved": saved,
            },
            next_action="done",
            steps=steps,
        )
    except ValueError as exc:
        return _response(
            status="error",
            state="failed",
            message=str(exc),
            details={},
            next_action="fix_request_and_retry",
            steps=steps,
            status_code=400,
        )
    except Exception as exc:  # noqa: BLE001
        return _response(
            status="error",
            state="failed",
            message="unexpected error during manual art upload",
            details={"error": str(exc)},
            next_action="retry",
            steps=steps,
            status_code=500,
        )


@app.post("/api/art/save-auto")
async def save_art_auto(payload: ArtSaveRequest):
    steps: list[dict[str, Any]] = []
    try:
        target = _resolve_target(payload.target_path)
        game_id, generated, id_source = _resolve_game_id_for_target(
            target,
            (payload.game_name or "").strip(),
            (payload.source_filename or "").strip(),
        )
        if not payload.selections:
            return _response(
                status="error",
                state="failed",
                message="no selected images",
                details={},
                next_action="select_images_from_preview",
                steps=steps,
                status_code=400,
            )

        ok, reason = _validate_target_access(target)
        if not ok:
            return _response(
                status="error",
                state="failed",
                message="target validation failed",
                details={"target": str(target), "reason": reason},
                next_action="fix_target_path_or_permissions",
                steps=steps,
                status_code=400,
            )
        _ensure_required_folders(target)
        art_dir = target / "ART"

        seen_types: set[str] = set()
        skipped_duplicates: list[dict[str, Any]] = []
        unique_selections: list[ArtSelection] = []
        for idx, selection in enumerate(payload.selections, start=1):
            art_type = selection.art_type.strip().upper()
            if art_type not in ART_TYPES:
                return _response(
                    status="error",
                    state="failed",
                    message=f"invalid art type: {art_type}",
                    details={"valid_types": ART_TYPES},
                    next_action="choose_valid_art_type",
                    steps=steps,
                    status_code=400,
                )
            if art_type in seen_types:
                skipped_duplicates.append({"art_type": art_type, "position": idx})
                continue
            seen_types.add(art_type)
            unique_selections.append(selection)

        if not unique_selections:
            return _response(
                status="error",
                state="failed",
                message="no unique art type selected",
                details={"valid_types": ART_TYPES},
                next_action="select_at_least_one_unique_art_type",
                steps=steps,
                status_code=400,
            )

        saved: list[dict[str, str]] = []
        for selection in unique_selections:
            art_type = selection.art_type.strip().upper()
            content, ext = _download_image(selection.image_url.strip(), art_type)
            destination = art_dir / f"{game_id}_{art_type}{ext}"
            with destination.open("wb") as fh:
                fh.write(content)
            saved.append({"art_type": art_type, "path": str(destination)})

        return _response(
            status="success",
            state="completed",
            message="selected auto art saved",
            details={
                "game_id": game_id,
                "generated_game_id": generated,
                "id_source": id_source,
                "saved": saved,
                "skipped_duplicates": skipped_duplicates,
            },
            next_action="done",
            steps=steps,
        )
    except ValueError as exc:
        return _response(
            status="error",
            state="failed",
            message=str(exc),
            details={},
            next_action="fix_request_and_retry",
            steps=steps,
            status_code=400,
        )
    except Exception as exc:  # noqa: BLE001
        return _response(
            status="error",
            state="failed",
            message="unexpected error during auto art save",
            details={"error": str(exc)},
            next_action="retry",
            steps=steps,
            status_code=500,
        )


@app.post("/api/import")
async def import_iso(
    target_path: str = Form(...),
    overwrite: bool = Form(False),
    files: list[UploadFile] = File(...),
):
    steps: list[dict[str, Any]] = []
    tmp_dir: Optional[str] = None
    prepared_files: list[dict[str, Any]] = []

    try:
        steps.append(_step("initializing", "info", "starting import job"))
        target = _resolve_target(target_path)

        steps.append(_step("validating_target", "info", "checking target path", {"target": str(target)}))
        ok, reason = _validate_target_access(target)
        if not ok:
            steps.append(_step("validating_target", "error", reason))
            return _response(
                status="error",
                state="failed",
                message="target validation failed",
                details={"target": str(target), "reason": reason},
                next_action="fix_target_path_or_permissions",
                steps=steps,
                status_code=400,
            )

        steps.append(_step("ensuring_structure", "info", "ensuring required folders"))
        try:
            missing, created = _ensure_required_folders(target)
        except NotADirectoryError as exc:
            steps.append(_step("ensuring_structure", "error", str(exc)))
            return _response(
                status="error",
                state="failed",
                message="invalid target structure",
                details={"error": str(exc)},
                next_action="fix_target_structure_then_retry",
                steps=steps,
                status_code=400,
            )
        steps.append(
            _step(
                "ensuring_structure",
                "success",
                "required folders are ready",
                {"missing_before": missing, "created": created},
            )
        )

        if not files:
            steps.append(_step("validating_files", "error", "no files uploaded"))
            return _response(
                status="error",
                state="failed",
                message="no files uploaded",
                details={},
                next_action="upload_iso_files",
                steps=steps,
                status_code=400,
            )

        steps.append(_step("validating_files", "info", "validating and staging uploads"))
        tmp_dir = tempfile.mkdtemp(prefix="ps2_iso_import_")

        for upload in files:
            original_name = Path(upload.filename or "").name
            if not original_name:
                steps.append(_step("validating_files", "error", "found file with empty filename"))
                return _response(
                    status="error",
                    state="failed",
                    message="invalid file name",
                    details={"file": upload.filename},
                    next_action="upload_valid_iso_files",
                    steps=steps,
                    status_code=400,
                )

            if Path(original_name).suffix.lower() != ".iso":
                steps.append(
                    _step("validating_files", "error", "non-iso file detected", {"file": original_name})
                )
                return _response(
                    status="error",
                    state="failed",
                    message="only .iso files are allowed",
                    details={"file": original_name},
                    next_action="remove_non_iso_files",
                    steps=steps,
                    status_code=400,
                )

            staged_path = Path(tmp_dir) / original_name
            # Handle duplicate names from upload set.
            if staged_path.exists():
                base = staged_path.stem
                suffix = staged_path.suffix
                counter = 1
                while True:
                    candidate = Path(tmp_dir) / f"{base}_{counter}{suffix}"
                    if not candidate.exists():
                        staged_path = candidate
                        break
                    counter += 1

            with staged_path.open("wb") as temp_file:
                shutil.copyfileobj(upload.file, temp_file)

            try:
                inferred_game_name = _derive_game_name(None, original_name)
            except ValueError:
                inferred_game_name = Path(original_name).stem
            iso_game_id = _extract_game_id_from_iso(staged_path)
            if iso_game_id:
                resolved_game_id = iso_game_id
                id_source = "iso"
            else:
                resolved_game_id, _ = _resolve_game_id(None, inferred_game_name)
                id_source = "generated"

            normalized_original_name = original_name
            if not normalized_original_name.upper().startswith(f"{resolved_game_id}_"):
                normalized_original_name = f"{resolved_game_id}_{original_name}"

            file_size = staged_path.stat().st_size
            prepared_files.append(
                {
                    "name": normalized_original_name,
                    "source_filename": original_name,
                    "game_name": inferred_game_name,
                    "game_id": resolved_game_id,
                    "id_source": id_source,
                    "size": file_size,
                    "staged_path": staged_path,
                    "target_folder": "CD" if file_size < CD_THRESHOLD_BYTES else "DVD",
                }
            )
            await upload.close()

        total_iso_bytes = sum(f["size"] for f in prepared_files)
        if total_iso_bytes == 0:
            steps.append(_step("validating_files", "error", "uploaded files are empty"))
            return _response(
                status="error",
                state="failed",
                message="uploaded files are empty",
                details={},
                next_action="upload_valid_iso_files",
                steps=steps,
                status_code=400,
            )

        steps.append(
            _step(
                "validating_files",
                "success",
                "files staged successfully",
                {
                    "file_count": len(prepared_files),
                    "total_iso_bytes": total_iso_bytes,
                    "total_iso_human": _human_bytes(total_iso_bytes),
                },
            )
        )

        steps.append(_step("checking_space", "info", "checking available disk space"))
        usage = shutil.disk_usage(target)
        buffer_bytes = _compute_buffer(total_iso_bytes)
        required_bytes = total_iso_bytes + buffer_bytes
        free_bytes = usage.free

        if free_bytes < required_bytes:
            deficit = required_bytes - free_bytes
            steps.append(
                _step(
                    "checking_space",
                    "error",
                    "not enough free space",
                    {
                        "required_bytes": required_bytes,
                        "free_bytes": free_bytes,
                        "deficit_bytes": deficit,
                    },
                )
            )
            return _response(
                status="error",
                state="failed",
                message="insufficient disk space",
                details={
                    "target": str(target),
                    "required": _human_bytes(required_bytes),
                    "free": _human_bytes(free_bytes),
                    "deficit": _human_bytes(deficit),
                    "buffer": _human_bytes(buffer_bytes),
                },
                next_action="free_up_space_then_retry",
                steps=steps,
                status_code=400,
            )

        steps.append(
            _step(
                "checking_space",
                "success",
                "disk space is sufficient",
                {
                    "required": _human_bytes(required_bytes),
                    "free": _human_bytes(free_bytes),
                    "buffer": _human_bytes(buffer_bytes),
                },
            )
        )

        steps.append(_step("importing", "info", "copying files to target"))
        imported: list[dict[str, Any]] = []

        for item in prepared_files:
            # Detect unplug/mount issues during long copy jobs.
            if not target.exists():
                steps.append(_step("importing", "error", "target path disappeared during import"))
                return _response(
                    status="error",
                    state="failed",
                    message="target path disappeared during import",
                    details={"target": str(target)},
                    next_action="reconnect_target_and_retry",
                    steps=steps,
                    status_code=400,
                )

            destination = target / item["target_folder"] / item["name"]
            if destination.exists() and not overwrite:
                steps.append(
                    _step(
                        "importing",
                        "error",
                        "destination file already exists",
                        {"file": item["name"], "destination": str(destination)},
                    )
                )
                return _response(
                    status="error",
                    state="failed",
                    message="destination file already exists",
                    details={"file": item["name"], "destination": str(destination), "overwrite": False},
                    next_action="enable_overwrite_or_rename_file",
                    steps=steps,
                    status_code=409,
                )

            remaining_bytes = sum(f["size"] for f in prepared_files if f["name"] not in {i["name"] for i in imported})
            usage = shutil.disk_usage(target)
            dynamic_required = remaining_bytes + _compute_buffer(remaining_bytes)
            if usage.free < dynamic_required:
                steps.append(
                    _step(
                        "importing",
                        "error",
                        "disk space dropped during import",
                        {
                            "file": item["name"],
                            "required": _human_bytes(dynamic_required),
                            "free": _human_bytes(usage.free),
                        },
                    )
                )
                return _response(
                    status="error",
                    state="failed",
                    message="disk space dropped during import",
                    details={"file": item["name"]},
                    next_action="free_up_space_then_retry",
                    steps=steps,
                    status_code=400,
                )

            shutil.copy2(item["staged_path"], destination)
            _upsert_manifest_entry(
                target=target,
                source_filename=item["source_filename"],
                game_name=item["game_name"],
                game_id=item["game_id"],
                id_source=item["id_source"],
                target_folder=item["target_folder"],
                destination_filename=item["name"],
            )
            imported.append(
                {
                    "file": item["name"],
                    "source_filename": item["source_filename"],
                    "game_name": item["game_name"],
                    "game_id": item["game_id"],
                    "id_source": item["id_source"],
                    "target_folder": item["target_folder"],
                    "destination": str(destination),
                    "size": _human_bytes(item["size"]),
                }
            )
            steps.append(
                _step(
                    "importing",
                    "success",
                    "file copied",
                    {"file": item["name"], "destination": str(destination)},
                )
            )

        steps.append(_step("completed", "success", "import completed"))
        return _response(
            status="success",
            state="completed",
            message="all files imported successfully",
            details={
                "target": str(target),
                "imported_count": len(imported),
                "imported": imported,
                "manifest_path": str(_manifest_path(target)),
            },
            next_action="done",
            steps=steps,
        )
    except Exception as exc:  # noqa: BLE001
        steps.append(_step("failed", "error", "unexpected error", {"error": str(exc)}))
        return _response(
            status="error",
            state="failed",
            message="unexpected error during import",
            details={"error": str(exc)},
            next_action="retry",
            steps=steps,
            status_code=500,
        )
    finally:
        if tmp_dir and Path(tmp_dir).exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    reload_enabled = os.getenv("RELOAD", "true").strip().lower() in {"1", "true", "yes", "on"}
    uvicorn.run("app.main:app", host=host, port=port, reload=reload_enabled)
