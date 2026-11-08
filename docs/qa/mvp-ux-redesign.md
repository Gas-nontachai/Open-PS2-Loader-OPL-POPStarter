# MVP UX redesign: implementation and QA

Date: 8 November 2026 (Asia/Bangkok).
Source of truth: the supplied PS2 TOOLKIT 2000X Windows MVP PRD.
Status: implementation tested locally; Windows hardware acceptance remains open.

## Design references

Read the requested [doctrine](https://github.com/plugin87/ux-ui-agent-skills/blob/main/CLAUDE.md),
[redesign workflow](https://github.com/plugin87/ux-ui-agent-skills/blob/main/workflows/redesign-audit.md),
[prototype workflow](https://github.com/plugin87/ux-ui-agent-skills/blob/main/workflows/prototyping.md),
[component rules](https://github.com/plugin87/ux-ui-agent-skills/blob/main/.claude/rules/components.md),
and [accessibility rules](https://github.com/plugin87/ux-ui-agent-skills/blob/main/.claude/rules/accessibility.md).
These informed the implementation; the external repository was not installed.
UI/UX Pro Max returned a marketing-oriented Hero/CTA pattern, which was rejected
because this is a desktop utility. The PRD's dark, compact, device-first direction
and Flet's Material controls take precedence.

## Audit and behavior mapping

| Requirement | Finding and implementation | Main files |
| --- | --- | --- |
| FR-01 Home | Removed decorative hero text. Added explicit USB selection on Home, synchronized with Import. Refresh never selects the first device or restores a drive letter without its physical identity. Removed targets clear destination, storage summary, library and artwork. | `app/ui/home_page.py`, `app/ui/device_selection.py`, `app/ui/app_layout.py` |
| FR-02 Safety | Retain a selected device only when path and identity match. Existing controller validation remains authoritative. Artwork status reads now validate identity too; format carries identity into the final Windows service lookup. Concurrent operations and device changes are blocked while work runs. Failed operations recheck the device and clear stale views if unavailable. | `app/controllers/art_controller.py`, `app/services/format_service.py`, `app/ui/app_layout.py` |
| FR-03 Structure | Folder states use Present/Missing/Not checked words. Compact wrapping folder list. Repair explanation says it only adds folders. Existing idempotent creation and file-name collision errors are retained. | `app/ui/storage_page.py`, existing target service |
| FR-04 Format | Dialog identifies model, drive, capacity and physical identity; states whole-disk/all-partition loss and DiskPart FAT32 limitations. Confirmation stays disabled until exact `FORMAT`; backend also rejects lowercase or surrounding whitespace. | `app/ui/dialogs.py`, import controller, format service |
| FR-05 Import | Review includes the same safety buffer as backend and disables Start for insufficient space. Structured callbacks expose file validation, copy percentage, job position, imported/skipped/failed/cancelled states. Overwrite has a destructive confirmation explaining USBExtreme loss risk. Results retain completed count on cancellation. Existing temporary-copy cleanup and FAT splitting are reused. | `app/ui/import_tab.py`, `app/controllers/import_controller.py`, shell |
| FR-06 Games | Game Files is the first tab. Manage Artwork selects Artwork explicitly. Removed unverified Ready claim. Delete explains permanent loss and retention of ART/CFG. Empty summary does not fabricate free space. | `app/ui/library_tab.py`, dialogs, shell |
| FR-07 Artwork | Empty actions disabled. Manual preview rejects unreadable or over-20-MiB input, with a backend size guard before reading bytes. Search clears stale selection/preview. Type dropdown is the keyboard route instead of mouse-only cards. Cancel is exposed for single and batch downloads; selection is locked during work. Existing providers, image processing and seven artwork types are retained. | `app/ui/art_tab.py`, artwork controller |
| FR-08 Settings | Retains language switch, persisted auto-artwork preference and version. Explains offline/online boundaries and partial Thai translation. Settings does not trigger a storage refresh. | `app/ui/app_layout.py`, existing config |
| FR-09 Updates | Existing startup stable-release check, timeout and browser release link remain unchanged. Existing update tests were rerun. | existing update service and dialogs |

## Shared presentation

`app/ui/theme.py` supplies semantic background, surface, text, muted, border,
primary, danger, warning and success colors, spacing/radius, headings, panels and
a destructive button style. Existing Material icons and controls are reused.
Root columns stretch within their available width; page bodies remain scrollable.
Window defaults remain 1240 x 820, minimum 820 x 620.

Native preview exposed an existing Flet 0.25.2 incompatibility on Python 3.9:
`Tab.before_update` uses `isinstance` against `typing.Union` and raises a TypeError.
`app/ui/workspace_tab.py` is a small local tab compatibility override, covered by
actual Flet command serialization. Remove it after upgrading to a fixed Flet version.
No dependency was added or changed.

## Evidence

Commands run with bytecode redirected to a writable temporary directory:

```sh
PYTHONPYCACHEPREFIX=/private/tmp/ps2-pycache .venv/bin/python -m pytest -q
PYTHONPYCACHEPREFIX=/private/tmp/ps2-pycache .venv/bin/python -m compileall -q app
git diff --check
```

Final suite: **119 passed**. Compilation and diff whitespace checks succeeded.
Tests use temporary directories and mocked physical-device validation; no real
disk was formatted, imported onto or deleted from.

Added checks cover explicit selection, same-letter/different-identity replacement,
space buffer and disabled Start, removed-target clearing, real progress counters,
exact format confirmation in UI/backend, artwork identity validation and invalid
preview rejection, format-service identity forwarding, five-page Flet command
serialization, tab compatibility and actual ISO copy/duplicate progress events.
Existing safety, filesystem, artwork, release and ISO integration tests also ran.

A native Flet preview on macOS was inspected via screenshots and accessibility
state for Home, Import, Game Files, Artwork, Storage and Settings at the configured
initial size. Navigation and artwork-tab activation were exercised. Inspection
caught the tab exception and width overflow; both were corrected. This is a local
smoke check, not Windows or complete interaction/accessibility certification.

## Open acceptance checks and retained limitations

- Windows 10/11: both specified window sizes, DPI scaling, scroll, keyboard traversal,
  focus visibility, screen reader and high-contrast behavior need manual acceptance.
- No WCAG pass, measured contrast pass, XIAS 52-gate pass, `/gate` or `/critique` pass
  is claimed. Those external HTML/browser gate tools were not installed or run.
- Real USB detach/replacement during copy, UAC, DiskPart failure/success, actual online
  artwork availability and physical PS2/OPL playback were not tested here.
- ISO preflight retains the existing batch-abort behavior for a missing Game ID;
  the offending file is identified, and users must select valid files and retry.
- Overall import progress is based on file position plus current-file percentage,
  not byte-weighted throughput or a remaining-time estimate.
- USBExtreme overwrite still removes old parts before replacement completes.
  Cancellation/failure can lose that old game; completed imports are not rolled back.
- Device detach is detected on refresh/operation validation; there is no new hotplug
  watcher. Partial Thai translation and external artwork-provider limitations remain.

No new unsupported formats, demo devices/games, analytics, online account features,
settings, installer changes or dependency upgrades were added.
