param(
    [switch]$Uninstall,
    [string]$PluginRoot = "$env:ProgramData\Blackmagic Design\DaVinci Resolve\Support\Workflow Integration Plugins"
)

$ErrorActionPreference = "Stop"
$sourceRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$resolvedRoot = [System.IO.Path]::GetFullPath($PluginRoot)
$destScript = Join-Path $resolvedRoot "ColorFlow.py"
$destLib = Join-Path $resolvedRoot "ColorFlowLib"
$destAssets = Join-Path $resolvedRoot "assets"
$destVersion = Join-Path $resolvedRoot "ColorFlow.VERSION"
$resolvedLib = [System.IO.Path]::GetFullPath($destLib)
$backupRoot = Join-Path $env:TEMP "ColorFlowBackups"
$version = (Get-Content -LiteralPath (Join-Path $sourceRoot "VERSION") -Raw).Trim()

if (-not $resolvedLib.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to operate outside the plugin root: $resolvedLib"
}

if ($Uninstall) {
    if (Test-Path -LiteralPath $destScript) {
        Remove-Item -LiteralPath $destScript -Force
        Write-Host "Removed $destScript"
    }
    if (Test-Path -LiteralPath $destLib) {
        Remove-Item -LiteralPath $destLib -Recurse -Force
        Write-Host "Removed $destLib"
    }
    if (Test-Path -LiteralPath $destVersion) {
        Remove-Item -LiteralPath $destVersion -Force
        Write-Host "Removed $destVersion"
    }
    foreach ($asset in @("lut_reference_480x270.rgb", "lut_reference.png")) {
        $assetPath = Join-Path $destAssets $asset
        if (Test-Path -LiteralPath $assetPath) {
            Remove-Item -LiteralPath $assetPath -Force
            Write-Host "Removed $assetPath"
        }
    }
    Write-Host "Restart DaVinci Resolve to unregister ColorFlow."
    return
}

if (-not (Test-Path -LiteralPath $resolvedRoot)) {
    New-Item -ItemType Directory -Path $resolvedRoot | Out-Null
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
if (Test-Path -LiteralPath $destScript) {
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    $backup = Join-Path $backupRoot "ColorFlow.py.$stamp.bak"
    Copy-Item -LiteralPath $destScript -Destination $backup -Force
    Write-Host "Backed up script to $backup"
}
if (Test-Path -LiteralPath $destLib) {
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    $backupLib = Join-Path $backupRoot "ColorFlowLib.$stamp.bak"
    Copy-Item -LiteralPath $destLib -Destination $backupLib -Recurse -Force
    Write-Host "Backed up library to $backupLib"
    Remove-Item -LiteralPath $destLib -Recurse -Force
}

Copy-Item -LiteralPath (Join-Path $sourceRoot "ColorFlow.py") -Destination $destScript -Force
Copy-Item -LiteralPath (Join-Path $sourceRoot "VERSION") -Destination $destVersion -Force
New-Item -ItemType Directory -Path $destLib -Force | Out-Null
New-Item -ItemType Directory -Path $destAssets -Force | Out-Null
Get-ChildItem -LiteralPath (Join-Path $sourceRoot "ColorFlowLib") -File -Filter "*.py" |
    ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $destLib -Force
    }
foreach ($asset in @("lut_reference_480x270.rgb", "lut_reference.png")) {
    $assetSource = Join-Path (Join-Path $sourceRoot "assets") $asset
    if (Test-Path -LiteralPath $assetSource) {
        Copy-Item -LiteralPath $assetSource -Destination $destAssets -Force
    }
}

Write-Host ""
Write-Host "ColorFlow v$version installed to:"
Write-Host "  $destScript"
Write-Host "  $destLib"
Write-Host "  $destAssets"
Write-Host "  $destVersion"
Write-Host ""
Write-Host "Next:"
Write-Host "  1. Restart DaVinci Resolve Studio."
Write-Host "  2. Open Workspace > Workflow Integrations > ColorFlow."
Write-Host "  3. In the Color page, prepare a blank serial node for DCTL/CDL writes."

