$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Constants = Get-Content (Join-Path $ProjectRoot "app\core\constants.py") -Raw
$Match = [regex]::Match($Constants, 'APP_VERSION\s*=\s*"([^"]+)"')
if (-not $Match.Success) { throw "APP_VERSION was not found." }
$Version = $Match.Groups[1].Value

$Executable = Join-Path $ProjectRoot "build\windows\PS2 Toolkit 2000X\PS2 Toolkit 2000X.exe"
if (-not (Test-Path -LiteralPath $Executable)) { throw "Build the Windows app first with .\scripts\build.ps1" }

$Candidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
)
$Compiler = $Candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $Compiler) { throw "Inno Setup 6 was not found. Install it from https://jrsoftware.org/isinfo.php" }

New-Item -ItemType Directory -Path (Join-Path $ProjectRoot "dist") -Force | Out-Null
& $Compiler "/DMyAppVersion=$Version" (Join-Path $ProjectRoot "installer\ps2-toolkit-2000x.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed." }

$Installer = Join-Path $ProjectRoot "dist\PS2-Toolkit-2000X-Setup-$Version.exe"
if (-not (Test-Path -LiteralPath $Installer)) { throw "Expected installer was not created: $Installer" }
Write-Host "Installer created: $Installer"
