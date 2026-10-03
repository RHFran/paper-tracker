# All arguments are passed unchanged to the launcher. Never enables --send.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw 'Run .\scripts\setup.ps1 first (Python 3.11+ required).'
}
& $Python (Join-Path $Root 'scripts/launch.py') @args
exit $LASTEXITCODE
