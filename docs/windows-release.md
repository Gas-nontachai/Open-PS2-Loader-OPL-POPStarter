# Windows development and release

## Development

Requirements: Windows 10/11 x64, Python 3.9+ (3.11 recommended), Git and Inno Setup 6.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

## Run Dev

```powershell
.\scripts\dev.ps1
```

Manual command:

```powershell
.\.venv\Scripts\python.exe -m app.main
```

## Testing

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Device safety tests use synthetic Windows storage records. Import and artwork tests use temporary directories. Formatting is never executed by tests.

## Build EXE

```powershell
.\scripts\build.ps1
```

The script cleans stale artifacts, runs tests and builds an onedir application at:

```text
build\windows\PS2 Toolkit 2000X\PS2 Toolkit 2000X.exe
```

The executable contains a `requireAdministrator` UAC manifest. Windows prompts for elevation whenever the installed application starts.

## Build Installer

Install Inno Setup 6, then run:

```powershell
.\scripts\package.ps1
```

## Release

```powershell
.\scripts\release.ps1
```

Final artifact:

```text
dist\PS2-Toolkit-2000X-Setup-<APP_VERSION>.exe
```

Do not distribute `.venv`, `.env`, source caches, logs, build intermediates, `.part` files or signing credentials.

## Troubleshooting

- If PowerShell blocks scripts, run `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\release.ps1`.
- If Flet or PyInstaller is missing, reinstall `requirements-dev.txt` in the active environment.
- If Inno Setup is not detected, install version 6 in its default per-user or Program Files location.
- If no destination appears, confirm Windows reports the physical disk bus as USB. Unknown classification is rejected intentionally.
- Code-sign the final installer in a trusted release environment before public distribution.
