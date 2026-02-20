# PS2 ISO Importer (Web)

Local web app for preparing a PS2 OPL folder structure and importing `.iso` files into `CD/` or `DVD/`.

## Features

- Vanilla JS + Tailwind CSS frontend
- FastAPI backend
- Target validation with required folder creation
- Disk space check before import
- USB format action (FAT32/MBR on macOS) with required folder bootstrap
- ART manager manual upload by art type
- ART manager auto fetch via RAWG API with preview-before-save
- `GAME ID` is extracted from ISO at import (fallback to generated if needed) and stored in `CFG/game_manifest.json`
- Imported game files are renamed to `${GAME_ID}_${original_filename}` for OPL-friendly matching
- ART uses the same imported `GAME ID` from manifest for matching
- Step/state-based API responses and UI logs

## Required Folder Structure

`APPS`, `ART`, `CD`, `CFG`, `CHT`, `DVD`, `LNG`, `POPS`, `THM`, `VMC`

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

## Auto ART Provider (RAWG)

Set values in `.env` before running:

```bash
RAWG_API_KEY="your_rawg_api_key"
```

- If `RAWG_API_KEY` is missing, auto-art search returns an error.

## Auto ART Cache + Rate Limit

You can tune these optional `.env` variables:

```bash
ART_SEARCH_CACHE_TTL_SEC=1800
ART_SEARCH_CACHE_MAX_SIZE=200
ART_SEARCH_RATE_LIMIT_PER_MIN=30
ART_SEARCH_MIN_INTERVAL_SEC=1.5
```

- Cache stores search results by `game_id + query + max_results`.
- Per-client request rate limiting protects from bursts.

## API

- `GET /api/health`
- `GET /api/pick-target-folder`
- `POST /api/validate-target`
- `POST /api/format-target`
- `POST /api/art/search`
- `POST /api/art/manual`
- `POST /api/art/save-auto`
- `POST /api/import`

## Format Notes

- Format action uses `diskutil` and currently supports macOS only.
- The UI requires typing `FORMAT` before running erase.
- The app refuses to format internal disks.
