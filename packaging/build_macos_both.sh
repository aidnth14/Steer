#!/usr/bin/env bash
# Build Steer.app for BOTH macOS architectures from one (universal2) machine, as small as
# possible without dropping content: each build is arch-thinned (not a fat universal binary),
# symbol-stripped, and zipped. Requires a universal2 Python + universal2 pygame (so the
# x86_64 slice exists to thin to). Output: dist/Steer-macos-arm64.zip and -intel.zip.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
rm -rf build dist
mkdir -p dist

build_one() {   # $1 = arch (arm64|x86_64)   $2 = label (applesilicon|intel)
  local arch="$1" label="$2"
  echo ">> building $label ($arch)"
  rm -rf "build" "dist/$arch"
  STEER_ARCH="$arch" "$PY" -m PyInstaller packaging/steer.spec \
      --noconfirm --clean --distpath "dist/$arch" --workpath "build/$arch" >/dev/null
  # verify the produced binary is actually single-arch
  local bin="dist/$arch/Steer.app/Contents/MacOS/Steer"
  echo "   arch(s): $(lipo -archs "$bin" 2>/dev/null)"
  ( cd "dist/$arch" && /usr/bin/ditto -c -k --sequesterRsrc --keepParent "Steer.app" "../Steer-macos-$label.zip" )
  echo "   zip: $(du -h "dist/Steer-macos-$label.zip" | cut -f1)  app: $(du -sh "dist/$arch/Steer.app" | cut -f1)"
}

build_one arm64  applesilicon
build_one x86_64 intel

echo ">> done:"
ls -lh dist/Steer-macos-*.zip
