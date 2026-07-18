param(
    [string]$Python = "python",
    [switch]$InstallDependencies
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Vendor = Join-Path $Root ".vendor\archipelago"
$Target = Join-Path $Vendor "worlds\aoe4"
$Source = Join-Path $Root "aoe4"
$Dist = Join-Path $Root "dist"

$PythonVersion = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([version]$PythonVersion -lt [version]"3.11") {
    throw "Archipelago 0.6.7 requires Python 3.11 or newer for source builds; '$Python' is Python $PythonVersion."
}

if (-not (Test-Path (Join-Path $Vendor ".git"))) {
    New-Item -ItemType Directory -Force (Split-Path $Vendor) | Out-Null
    git clone --branch 0.6.7 --depth 1 https://github.com/ArchipelagoMW/Archipelago.git $Vendor
}

$SafeVendor = $Vendor.Replace("\", "/")
$Version = (git -c "safe.directory=$SafeVendor" -C $Vendor describe --tags --exact-match 2>$null)
if ($Version -ne "0.6.7") {
    throw "Expected the upstream checkout at $Vendor to be Archipelago tag 0.6.7; found '$Version'."
}

if ($InstallDependencies) {
    & $Python -m pip install -r (Join-Path $Vendor "requirements.txt") -r (Join-Path $Root "requirements-dev.txt")
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
}

$ResolvedWorlds = (Resolve-Path (Join-Path $Vendor "worlds")).Path
$ExpectedTarget = Join-Path $ResolvedWorlds "aoe4"
if ([System.IO.Path]::GetFullPath($Target) -ne [System.IO.Path]::GetFullPath($ExpectedTarget)) {
    throw "Refusing to replace an unexpected overlay path: $Target"
}
if (Test-Path $Target) {
    Remove-Item -LiteralPath $Target -Recurse -Force
}
Copy-Item -LiteralPath $Source -Destination $Target -Recurse

Push-Location $Vendor
try {
    & $Python (Join-Path $Root "scripts\invoke_upstream_build.py")
    if ($LASTEXITCODE -ne 0) { throw "Archipelago APWorld builder failed." }
}
finally {
    Pop-Location
}

New-Item -ItemType Directory -Force $Dist | Out-Null
Copy-Item -LiteralPath (Join-Path $Vendor "build\apworlds\aoe4.apworld") -Destination (Join-Path $Dist "aoe4.apworld") -Force

$TemplateSource = Join-Path $Vendor "build\aoe4_templates\Age of Empires IV.yaml"
if (-not (Test-Path $TemplateSource)) {
    throw "Archipelago did not generate the Age of Empires IV YAML template."
}
Copy-Item -LiteralPath $TemplateSource -Destination (Join-Path $Dist "Age of Empires IV.yaml") -Force

Write-Output "Built $Dist\aoe4.apworld"
Write-Output "Generated $Dist\Age of Empires IV.yaml"
