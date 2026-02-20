# PS2 ISO Importer (Web)

Local web app for preparing a PS2 OPL folder structure and importing `.iso` files into `CD/` or `DVD/`.

## Features

- Vanilla JS + Tailwind CSS frontend
- FastAPI backend
- Target validation with required folder creation
- Disk space check before import
- USB format action (FAT32/MBR on macOS) with required folder bootstrap
- Step/state-based API responses and UI logs

## Required Folder Structure

`APPS`, `ART`, `CD`, `CFG`, `CHT`, `DVD`, `LNG`, `POPS`, `THM`, `VMC`

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

## API

- `GET /api/health`
- `GET /api/pick-target-folder`
- `POST /api/validate-target`
- `POST /api/format-target`
- `POST /api/import`

## Format Notes

- Format action uses `diskutil` and currently supports macOS only.
- The UI requires typing `FORMAT` before running erase.
- The app refuses to format internal disks.
