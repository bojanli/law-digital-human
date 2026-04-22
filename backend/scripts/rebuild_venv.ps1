param(
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".venv"
$requirements = Join-Path $root "requirements.txt"

Write-Host "[1/4] Removing broken virtual environment metadata if present..."
if (Test-Path $venv) {
    try {
        Remove-Item -Recurse -Force $venv
    }
    catch {
        $staleName = ".venv_stale_{0}" -f (Get-Date -Format "yyyyMMdd_HHmmss")
        $stalePath = Join-Path $root $staleName
        Write-Host "Could not delete locked .venv, trying to rename it to $staleName ..."
        try {
            Rename-Item -Path $venv -NewName $staleName -Force
        }
        catch {
            throw "Failed to remove or rename locked .venv. Close terminals/IDEs using backend\.venv, then rerun."
        }
        Write-Host "Renamed old environment to: $stalePath"
    }
}

Write-Host "[2/4] Creating fresh virtual environment with $PythonExe ..."
& $PythonExe -m venv $venv

$venvPython = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Virtual environment creation failed: $venvPython not found"
}

Write-Host "[3/4] Upgrading pip ..."
& $venvPython -m pip install --upgrade pip

Write-Host "[4/4] Installing backend requirements ..."
& $venvPython -m pip install -r $requirements

Write-Host ""
Write-Host "Done. Test command:"
Write-Host "  $venvPython -m pytest"
