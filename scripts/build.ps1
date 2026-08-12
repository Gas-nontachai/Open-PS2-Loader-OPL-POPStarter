$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not [Environment]::Is64BitOperatingSystem) { throw "A 64-bit Windows host is required." }
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) { throw "Create .venv and install requirements-dev.txt first." }
$FletExe = Join-Path $ProjectRoot ".venv\Scripts\flet.exe"
if (-not (Test-Path -LiteralPath $FletExe)) { throw "Flet CLI is missing. Install requirements-dev.txt." }

& (Join-Path $PSScriptRoot "clean.ps1")
& $PythonExe -m pytest
if ($LASTEXITCODE -ne 0) { throw "Tests failed." }

$OutputDir = Join-Path $ProjectRoot "build\windows"
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$Constants = Get-Content (Join-Path $ProjectRoot "app\core\constants.py") -Raw
$Match = [regex]::Match($Constants, 'APP_VERSION\s*=\s*"([^"]+)"')
if (-not $Match.Success) { throw "APP_VERSION was not found." }
$Version = $Match.Groups[1].Value
& $FletExe pack "app\main.py" -D --name "PS2 Toolkit 2000X" --distpath $OutputDir --product-name "PS2 TOOLKIT 2000X" --file-description "PS2 Game Importer and OPL USB Manager" --product-version $Version --file-version "$Version.0" --uac-admin -y
if ($LASTEXITCODE -ne 0) { throw "Flet/PyInstaller build failed." }

$Executable = Join-Path $OutputDir "PS2 Toolkit 2000X\PS2 Toolkit 2000X.exe"
if (-not (Test-Path -LiteralPath $Executable)) { throw "Expected executable was not created: $Executable" }
Write-Host "Windows application created: $Executable"
