$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "build.ps1")
& (Join-Path $PSScriptRoot "package.ps1")
Write-Host "Release completed successfully."
