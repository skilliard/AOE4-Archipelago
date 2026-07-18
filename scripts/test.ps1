param([string]$Python = "python")

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Vendor = Join-Path $Root ".vendor\archipelago"
if (-not (Test-Path (Join-Path $Vendor ".git"))) {
    throw "Run scripts/build_apworld.ps1 once to provision Archipelago 0.6.7."
}

$PythonVersion = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([version]$PythonVersion -lt [version]"3.11") {
    throw "Archipelago 0.6.7 requires Python 3.11 or newer for source tests; '$Python' is Python $PythonVersion."
}

$Worlds = (Resolve-Path (Join-Path $Vendor "worlds")).Path
$Target = Join-Path $Worlds "aoe4"
$ExpectedTarget = Join-Path $Worlds "aoe4"
if ([System.IO.Path]::GetFullPath($Target) -ne [System.IO.Path]::GetFullPath($ExpectedTarget)) {
    throw "Refusing to replace an unexpected test overlay path: $Target"
}
if (Test-Path $Target) {
    Remove-Item -LiteralPath $Target -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $Root "aoe4") -Destination $Target -Recurse

$env:PYTHONPATH = "$Root;$Vendor"
$env:SKIP_REQUIREMENTS_UPDATE = "1"
& $Python -m pytest (Join-Path $Root "tests") -v
if ($LASTEXITCODE -ne 0) { throw "Tests failed." }
