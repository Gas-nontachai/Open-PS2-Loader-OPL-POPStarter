# Validation report — 2026-11-08

Host: macOS arm64, Python 3.9.6. Windows execution is pending the first CI run.

## Executed

- `python -m pytest -q`: **54 passed** with synthetic fixtures.
- `PS2_TEST_ISO=".../Grand Theft Auto - Liberty City Stories (USA).iso" python -m pytest tests/test_iso_integration.py -v`: **9 passed** before the overwrite test was added.
- The added successful overwrite test was then run separately against the same real ISO: **1 passed**.
- Python compilation passed with a writable temporary bytecode cache.
- Workflow YAML parsed successfully; release image markup specifies `width="150"`.
- `git diff --check` passed.

## Real ISO results

Source size: **4,010,016,768 bytes**. Extracted boot ID: **SLUS_214.23**.
No extraction mock was used. The original source was only read.

FAT32, exFAT and NTFS paths imported the entire ISO as a DVD image. FAT16
classification selected USBExtreme splitting into four parts. For every path,
the SHA-256 of the destination bytes (concatenated in order for split files)
matched the original. Duplicate imports skipped successfully; scanning reported
the correct size and ID; deletion removed the imported game and manifest entry.
Cancellation during copying removed the incomplete destination. A simulated
Windows disk-full error (`winerror=112`) preserved the existing game during
normal ISO overwrite. Successful normal ISO overwrite matched the source hash.

## Coverage and limits

The regression suite additionally checks media size boundaries, forced FAT32
splitting, split-byte integrity, cancellation between split parts, corrupt
`ul.cfg` rejection, insufficient-space preflight, disconnect cleanup, invalid
inputs, artwork, drive identity changes, unsafe disk rejection and mocked
Windows formatting commands.

USB validation is mocked only for temporary-directory integration tests, and
filesystem labels are simulated. These are not physical FAT/exFAT/NTFS volumes.
No physical disk was formatted. Physical USB disconnects, power loss, PS2/OPL
playback, Windows 10/11 hardware, installer execution, UAC/SmartScreen behavior
and release screenshots have not been tested on this host. This is bounded
scenario coverage, not a claim that every possible failure is covered.

The Windows CI matrix runs tests on Server 2022 and 2025. The build job packages
and silently installs the app on Server 2022, launches the installed executable,
and captures its real window. It rejects a missing/small/blank window; it does
not assert every control or interaction. CI must pass before release publication.
