from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Optional

import pycdlib


def normalize_game_id(game_id: str) -> str:
    normalized = game_id.strip().upper()
    if not re.fullmatch(r"[A-Z]{4}_[0-9]{3}\.[0-9]{2}", normalized):
        raise ValueError("game_id must match pattern like SLUS_209.46")
    return normalized


def generate_game_id(seed: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "", seed).upper()
    if len(cleaned) < 4:
        cleaned = (cleaned + "AUTO")[:4]
    prefix = cleaned[:4]
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    number = int(digest[:5], 16) % 100000
    return f"{prefix}_{number // 100:03d}.{number % 100:02d}"


def resolve_game_id(game_id: Optional[str], seed: Optional[str]) -> tuple[str, bool]:
    if game_id and game_id.strip():
        return normalize_game_id(game_id), False
    base = (seed or "").strip() or "AUTO_GAME"
    return generate_game_id(base), True


def extract_game_id_from_system_cnf(content: str) -> Optional[str]:
    match = re.search(r"([A-Z]{4}_[0-9]{3}\.[0-9]{2})", content.upper())
    if not match:
        return None
    return match.group(1)


def extract_game_id_from_iso(iso_path: Path) -> Optional[str]:
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
        return extract_game_id_from_system_cnf(system_cnf_text)
    except Exception:
        return None
    finally:
        try:
            iso.close()
        except Exception:
            pass


def normalize_lookup_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def manifest_path(target: Path) -> Path:
    return target / "CFG" / "game_manifest.json"


def load_manifest(target: Path) -> dict[str, Any]:
    manifest_file = manifest_path(target)
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


def save_manifest(target: Path, manifest: dict[str, Any]) -> None:
    manifest_file = manifest_path(target)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    with manifest_file.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=True, indent=2)


def upsert_manifest_entry(
    target: Path,
    source_filename: str,
    game_name: str,
    game_id: str,
    id_source: str,
    target_folder: str,
    destination_filename: str,
) -> None:
    manifest = load_manifest(target)
    entries = manifest.get("entries", [])
    source_key = normalize_lookup_key(Path(source_filename).stem)
    destination_key = normalize_lookup_key(Path(destination_filename).stem)
    game_key = normalize_lookup_key(game_name)
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
    save_manifest(target, manifest)


def lookup_game_id_from_manifest(target: Path, source_filename: Optional[str], game_name: Optional[str]) -> Optional[str]:
    manifest = load_manifest(target)
    entries = manifest.get("entries", [])
    source_key = normalize_lookup_key(Path(source_filename).stem) if source_filename else ""
    source_name = source_filename.strip() if source_filename else ""
    game_key = normalize_lookup_key(game_name) if game_name else ""
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


def extract_game_id_from_filename(source_filename: Optional[str]) -> Optional[str]:
    if not source_filename:
        return None
    name = Path(source_filename).name
    match = re.match(r"^([A-Z]{4}_[0-9]{3}\.[0-9]{2})[._\-\s]", name.upper())
    if not match:
        return None
    return match.group(1)


def build_opl_iso_filename(game_id: str, source_filename: str, game_name: Optional[str] = None) -> str:
    original = Path(source_filename).name
    ext = Path(original).suffix.lower() or ".iso"
    if ext != ".iso":
        ext = ".iso"

    resolved_name = (game_name or "").strip()
    if not resolved_name:
        try:
            resolved_name = derive_game_name(None, original)
        except ValueError:
            resolved_name = Path(original).stem

    # OPL-safe filename: keep only common characters and collapse separators.
    cleaned = re.sub(r"[^A-Za-z0-9\-\s\.\(\)\[\]]+", " ", resolved_name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        cleaned = "GAME"
    return f"{game_id}.{cleaned}{ext}"


def resolve_game_id_for_target(target: Optional[Path], game_name: Optional[str], source_filename: Optional[str]) -> tuple[str, bool, str]:
    from_filename = extract_game_id_from_filename(source_filename)
    if from_filename:
        return from_filename, False, "filename"
    if target:
        matched = lookup_game_id_from_manifest(target, source_filename, game_name)
        if matched:
            return matched, False, "manifest"
    seed = (game_name or "").strip() or (source_filename or "").strip()
    game_id, generated = resolve_game_id(None, seed)
    return game_id, generated, "generated"


def derive_game_name(game_name: Optional[str], source_filename: Optional[str]) -> str:
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
