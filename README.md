# PS2 TOOLKIT 2000X

PS2 TOOLKIT 2000X is a Windows desktop utility for importing and managing PS2 games on external USB storage used with Open PS2 Loader (OPL). It is built with Python and Flet and is distributed as a self-contained Windows installer.

## External-storage-only safety

The application only accepts a destination when Windows can map its logical volume to a physical disk whose bus type is explicitly `USB`. This supports:

- USB flash drives
- External USB HDDs
- External USB SSDs

Internal SATA/NVMe disks, the Windows/application drive, boot/system/pagefile disks, recovery/hidden volumes, network drives, disconnected devices, and devices with unknown classification are rejected. Safety validation runs again before every storage operation; UI filtering is not treated as authorization.

Formatting remains destructive. Always verify the model, drive letter, capacity and filesystem shown in the confirmation dialog.

## Features

- Beginner-friendly Home, Import Games, combined Games & Artwork, USB/Storage and Settings pages.
- Guided multi-ISO import with destination and space review.
- Automatic OPL-compatible splitting for ISO files that exceed the FAT32 single-file limit.
- Clear import errors and suggested fixes directly on the Import page; no log reading is required.
- PS2 game ID extraction and OPL-compatible CD/DVD filenames.
- Background copying with byte progress, cancellation and atomic `.part` files.
- Game scanning, artwork thumbnails, storage summary and confirmed deletion.
- Revalidates the physical USB device whenever a page opens and clears stale game/artwork data after disconnect, device replacement or formatting.
- Manual PNG, JPG, JPEG and WEBP cover upload with preview, conversion, replacement and removal.
- Idempotent creation/repair of OPL folders.
- English/Thai UI switch: the toggle displays the language it will switch to.
- Settings and rotating logs under `%LOCALAPPDATA%\PS2 Toolkit 2000X`.
- Fully offline operation.
- Requests Windows Administrator permission when launched so storage operations use one consistent permission context.

## Development requirements

- Windows 10 or Windows 11 x64
- Python 3.11 recommended; Python 3.9+ supported by the source
- Inno Setup 6 for installer builds

## Development setup and run

```powershell
git clone <repository-url>
cd Open-PS2-Loader-OPL-POPStarter
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
.\scripts\dev.ps1
```

Manual equivalent:

```powershell
.\.venv\Scripts\python.exe -m app.main
```

## Testing

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Tests use mocked device data and temporary folders. Automated tests never format a physical disk.

## Build and release

```powershell
.\scripts\build.ps1
.\scripts\package.ps1
```

Or run the complete pipeline:

```powershell
.\scripts\release.ps1
```

If local PowerShell policy blocks scripts:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\release.ps1
```

Outputs:

```text
build\windows\PS2 Toolkit 2000X\PS2 Toolkit 2000X.exe
dist\PS2-Toolkit-2000X-Setup-1.0.0.exe
```

The release version has one source of truth: `APP_VERSION` in `app/core/constants.py`.

## Project structure

```text
app/core/          configuration, version, paths, logging and errors
app/models/        normalized game, drive and import models
app/services/      drive classification, ISO/OPL, artwork and formatting logic
app/controllers/   UI-independent workflows and safety gates
app/ui/            responsive Flet pages and dialogs
docs/              end-user and Windows release guides
installer/         Inno Setup source
scripts/           development, test/build and release scripts
tests/             storage safety and business-logic tests
```

This is a native packaged Flet desktop application. It does not run an API or web server.

## Troubleshooting

- **No external storage detected:** reconnect the USB device, wait for Windows to mount it, then click Refresh Devices. Unknown or non-USB devices are intentionally hidden.
- **Device changed/disconnected:** refresh and select the device again. The app will not reuse an old drive-letter identity.
- **Game ID cannot be read:** use a valid PS2 ISO or a filename beginning with an ID such as `SLUS_209.46`.
- **Not enough free space:** remove files or choose a larger external USB device.
- **Build tools missing:** activate `.venv` and reinstall `requirements-dev.txt`.
- **Installer compiler missing:** install Inno Setup 6.
- **PowerShell scripts blocked:** use the `-ExecutionPolicy Bypass` command shown above.
- **Administrator prompt at startup:** expected behavior. Click **Yes** to allow storage management; choosing **No** cancels application startup.

See [docs/HOW_TO_USE.md](docs/HOW_TO_USE.md) and [docs/windows-release.md](docs/windows-release.md).

## Windows CI and tag releases

`.github/workflows/windows.yml` runs the regression suite on Windows Server
2022 and 2025 runners, then builds the Windows x64 application and Inno Setup
installer. It silently installs the installer and opens the installed app to
capture `windows-home.png`. A missing window or blank capture fails the build.
Pushes and pull requests provide the installer and screenshot as Actions artifacts.
These runners do not replace testing Windows 10/11 with physical USB hardware.

To publish a release, update `APP_VERSION` in `app/core/constants.py`, commit the
changes, and push a matching tag yourself, for example:

```powershell
git tag v1.0.0
git push origin v1.0.0
```

Only `v*` tags publish GitHub Releases, and the tag must equal `v` + `APP_VERSION`.
The release includes the downloadable setup `.exe`, full-size screenshot and
SHA-256 checksums. Its notes show the screenshot at **150 pixels wide**, linked
to the original. The installer bundles the application runtime; do not distribute
only the inner application executable without its accompanying files.
No code-signing certificate is configured, so Windows may show SmartScreen warnings.

### Testing the Liberty City Stories ISO locally

CI generates a small ISO containing `SYSTEM.CNF` with boot ID `SLUS_214.23`.
To run the same integration scenarios against your own full game image on Windows:

```powershell
$env:PS2_TEST_ISO = (Resolve-Path '.\Grand Theft Auto - Liberty City Stories (USA).iso').Path
.\.venv\Scripts\python.exe -m pytest -v --junitxml=test-results.xml
Remove-Item Env:PS2_TEST_ISO
```

The integration tests use temporary destinations and mock **only USB device
validation/filesystem classification**; they never format or write to a real USB.
They check ISO ID extraction, FAT32/exFAT/NTFS direct import, FAT16 splitting when
needed, SHA-256 integrity, duplicate skipping, scan/manifest/delete, successful
overwrite, cancellation during copying, disk-full overwrite recovery and invalid
input. Existing tests also exercise forced FAT32 splitting, low-space preflight,
disconnection cleanup, artwork and Windows storage safety. Filesystem labels in
these tests are simulated, not actual mounted filesystems. The supplied ISO is
4,010,016,768 bytes, below FAT32's 4,294,967,295-byte single-file limit.

Allow at least 5 GB free temporary disk space for the real-image run. Game images
are ignored by Git and are never uploaded by this workflow.
