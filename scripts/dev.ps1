$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Virtual environment not found. Run: python -m venv .venv"
}

Write-Host "Starting PS2 TOOLKIT 2000X..."
& $PythonExe -m app.main
if ($LASTEXITCODE -ne 0) { throw "Application exited with code $LASTEXITCODE" }
