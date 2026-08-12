from __future__ import annotations

import json
import logging
import re
import socket
from dataclasses import dataclass
from typing import Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.services import game_service

logger = logging.getLogger("ps2_toolkit.artwork.providers")
Fetch = Callable[[str], bytes]


class ArtworkNetworkError(RuntimeError):
    pass


class GameIdNormalizer:
    @staticmethod
    def opl(value: str) -> str:
        return game_service.normalize_game_id(value)

    @staticmethod
    def hyphen(value: str) -> str:
        opl_id = GameIdNormalizer.opl(value)
        prefix, number = opl_id.split("_", 1)
        return f"{prefix}-{number.replace('.', '')}"


@dataclass(frozen=True)
class ArtworkCandidate:
    game_id: str
    art_type: str
    provider: str
    url: str
    source_name: str
    index: int = 0
    suffix: str = ""


class ArtworkProvider(Protocol):
    name: str

    def find(self, game_id: str) -> list[ArtworkCandidate]: ...


def fetch_url(url: str, timeout: int = 15) -> bytes:
    request = Request(url, headers={"User-Agent": "PS2-Toolkit-2000X/1.0", "Accept": "application/vnd.github+json"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - trusted provider URLs only
            return response.read(25 * 1024 * 1024 + 1)
    except HTTPError:
        raise
    except (URLError, TimeoutError, socket.timeout) as exc:
        raise ArtworkNetworkError("Artwork source unavailable.") from exc


class OplArtworkProvider:
    name = "OPL Artwork Database"
    api_root = "https://api.github.com/repos/Luden02/psx-ps2-opl-art-database/contents/PS2"

    def __init__(self, fetch: Fetch = fetch_url) -> None:
        self.fetch = fetch

    def find(self, game_id: str) -> list[ArtworkCandidate]:
        normalized = GameIdNormalizer.opl(game_id)
        url = f"{self.api_root}/{quote(normalized)}"
        try:
            payload = json.loads(self.fetch(url).decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 404:
                return []
            raise ArtworkNetworkError("Artwork source unavailable.") from exc
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            raise ArtworkNetworkError("Artwork source returned an invalid response.") from exc
        if not isinstance(payload, list):
            return []
        pattern = re.compile(
            rf"^{re.escape(normalized)}_(COV2|COV|LAB|LGO|ICO|BG|SCR)(?:_(\d+))?\.(png|jpe?g)$",
            re.IGNORECASE,
        )
        found: list[ArtworkCandidate] = []
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "")
            match = pattern.match(name)
            download_url = str(entry.get("download_url") or "")
            if not match or not download_url:
                continue
            art_type = match.group(1).upper()
            index = int(match.group(2) or 0)
            suffix = art_type if match.group(2) is None else f"{art_type}_{index:02d}"
            found.append(ArtworkCandidate(normalized, art_type, self.name, download_url, name, index, suffix))
        return sorted(found, key=lambda item: (item.art_type, item.index, item.source_name))


class Ps2CoversProvider:
    name = "PS2 Covers"
    raw_root = "https://raw.githubusercontent.com/xlenore/ps2-covers/main/covers/default"

    def __init__(self, fetch: Fetch = fetch_url) -> None:
        self.fetch = fetch

    def find(self, game_id: str) -> list[ArtworkCandidate]:
        normalized = GameIdNormalizer.opl(game_id)
        serial = GameIdNormalizer.hyphen(normalized)
        url = f"{self.raw_root}/{serial}.jpg"
        # This repository has no index. Existence is checked when the image is
        # downloaded, avoiding two network requests for the same cover.
        return [ArtworkCandidate(normalized, "COV", self.name, url, f"{serial}.jpg", 0, "COV")]
