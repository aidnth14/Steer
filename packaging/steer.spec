# PyInstaller spec for the Steer desktop client (Linux / macOS / Windows).
#
#   pyinstaller packaging/steer.spec --noconfirm
#
# Builds a one-folder app under dist/Steer/ (and dist/Steer.app on macOS). Assets are bundled
# at the bundle root so sim.py's `os.path.dirname(__file__)/assets` resolves unchanged both
# frozen and from source. Run this on EACH target OS/arch you want to ship -- PyInstaller does
# not cross-compile. For macOS Intel vs Apple Silicon, run on an x86_64 and an arm64 machine
# (or the two macOS runners in .github/workflows/build.yml).

import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent          # repo root (packaging/ is one level down)
ICON = None
if (ROOT / "assets" / "UI" / "logo.png").exists():
    ICON = None                                 # swap in a .ico/.icns here once you have one

block_cipher = None

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ROOT / "assets"), "assets")],   # whole asset tree -> <bundle>/assets
    hiddenimports=["pygame._sdl2", "pygame._sdl2.controller"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "redis", "numpy", "pytest"],   # server-only / test-only deps
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Steer",
    debug=False,
    strip=False,
    upx=False,
    console=False,              # windowed app (no terminal)
    icon=ICON,
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, name="Steer",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Steer.app",
        icon=ICON,
        bundle_identifier="io.steer.game",
        info_plist={
            "CFBundleName": "Steer",
            "CFBundleDisplayName": "Steer",
            "CFBundleShortVersionString": "1.2.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
