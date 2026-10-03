# No elevation or execution-policy changes. See docs/platform-setup.md.
param(
    [string]$Config,
    [switch]$Demo,
    [switch]$SkipInstall,
    [switch]$SkipModel,
    [string]$Python
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$PythonArgs = @()
if ($Python) {
    $Executable = $Python
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $Executable = 'py'
    $PythonArgs = @('-3')
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Executable = 'python'
} else {
    throw 'Python 3.11+ is required. Install Python from python.org, reopen PowerShell, and retry.'
}
$SetupArgs = @((Join-Path $Root 'scripts/setup.py'))
if ($Config) { $SetupArgs += @('--config', $Config) }
if ($Demo) { $SetupArgs += '--demo' }
if ($SkipInstall) { $SetupArgs += '--skip-install' }
if ($SkipModel) { $SetupArgs += '--skip-model' }
& $Executable @PythonArgs @SetupArgs
exit $LASTEXITCODE
