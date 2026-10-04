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

Write-Host ">> Smoke test (headless launch must survive 150 frames without crashing)"
$env:SDL_VIDEODRIVER = "dummy"; $env:SDL_AUDIODRIVER = "dummy"
$env:STEER_SMOKE = "150"; $env:STEER_SERVER_URL = "ws://127.0.0.1:1"
& "dist\Steer\Steer.exe"
if ($LASTEXITCODE -ne 0) { throw "Smoke test failed (exit $LASTEXITCODE)" }
Write-Host ">> Smoke test passed."

Write-Host ">> Done. Artifacts in dist\"
Get-ChildItem dist
