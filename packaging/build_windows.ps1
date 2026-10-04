# Build the Steer desktop client on Windows (PowerShell).
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
# Produces dist\Steer\ containing Steer.exe. Run on Windows x64.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$py = if ($env:PYTHON) { $env:PYTHON } else { "python" }
Write-Host ">> Using Python: $py"

& $py -m pip install --upgrade pip
& $py -m pip install "pygame-ce>=2.5" "websockets>=14" "pyinstaller>=6.0"

if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist)  { Remove-Item -Recurse -Force dist }

& $py -m PyInstaller packaging\steer.spec --noconfirm --clean

Write-Host ">> Done. Artifacts in dist\"
Get-ChildItem dist
