$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Targets = @(
    (Join-Path $ProjectRoot "build"),
    (Join-Path $ProjectRoot "dist"),
    (Join-Path $ProjectRoot "PS2 Toolkit 2000X.spec")
)
foreach ($Target in $Targets) {
    $ResolvedRoot = [IO.Path]::GetFullPath($ProjectRoot)
    $ResolvedTarget = [IO.Path]::GetFullPath($Target)
    if (-not $ResolvedTarget.StartsWith($ResolvedRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean path outside project: $ResolvedTarget"
    }
    if (Test-Path -LiteralPath $ResolvedTarget) {
        Remove-Item -LiteralPath $ResolvedTarget -Recurse -Force
    }
}
Write-Host "Build artifacts cleaned."
