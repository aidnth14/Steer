#!/usr/bin/env bash
# Build the Steer desktop client on Linux or macOS.
#   ./packaging/build_desktop.sh
# Produces dist/Steer/ (Linux) or dist/Steer.app + dist/Steer/ (macOS), for THIS machine's
# OS and CPU arch only. For macOS Intel + Apple Silicon you must run this once on each.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
echo ">> Using $($PY --version) on $(uname -s)/$(uname -m)"

$PY -m pip install --upgrade pip
$PY -m pip install "pygame-ce>=2.5" "websockets>=14" "pyinstaller>=6.0"

rm -rf build dist
$PY -m PyInstaller packaging/steer.spec --noconfirm --clean

echo ">> Smoke test (headless launch must survive 150 frames without crashing)"
if [[ "$(uname)" == "Darwin" ]]; then BIN="dist/Steer.app/Contents/MacOS/Steer"; else BIN="dist/Steer/Steer"; fi
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy STEER_SMOKE=150 STEER_SERVER_URL=ws://127.0.0.1:1 "$BIN"
echo ">> Smoke test passed."

echo ">> Done. Artifacts in dist/"
ls -la dist
