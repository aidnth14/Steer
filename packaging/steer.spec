# PyInstaller spec for the Steer desktop client (Linux / macOS / Windows).
#
#   pyinstaller packaging/steer.spec --noconfirm
#
# Builds a one-folder app under dist/Steer/ (and dist/Steer.app on macOS). Assets are bundled
# at the bundle root so sim.py's `os.path.dirname(__file__)/assets` resolves unchanged both
# frozen and from source. Run this on EACH target OS/arch you want to ship -- PyInstaller does
# not cross-compile. For macOS Intel vs Apple Silicon, run on an x86_64 and an arm64 machine
# (or the two macOS runners in .github/workflows/build.yml).

import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent          # repo root (packaging/ is one level down)
ICON = None
if (ROOT / "assets" / "UI" / "logo.png").exists():
    ICON = None                                 # swap in a .ico/.icns here once you have one

# Smallest build without dropping content: strip symbols, trim stdlib/3rd-party modules the game
# never imports, and (macOS) thin the universal2 binaries to ONE arch via STEER_ARCH so an Intel
# app isn't carrying arm64 code and vice-versa. STEER_ARCH = "x86_64" | "arm64" | unset(=native).
block_cipher = None
TARGET_ARCH = os.environ.get("STEER_ARCH") or None
STRIP = sys.platform != "win32"                 # strip is a no-op/harmful on Windows

EXCLUDES = [
    "tkinter", "redis", "numpy", "pytest", "_pytest", "setuptools", "pip", "wheel",
    "unittest", "pydoc", "doctest", "lib2to3", "distutils", "test", "xmlrpc",
    "plyer",                        # Android-only gyro backend; desktop uses SDL sensors / none
    "cffi", "_cffi_backend", "pycparser",   # not used by the game; arm64-only .so blocks x86_64
    "cryptography",                          # ditto: arm64-only _rust .so, game never imports it
    "websockets.speedups",                   # optional C accel; pure-Python fallback is fine
]

# Some asset subtrees (flags, sfx, music, button icons) are symlinks to an external store.
# os.walk(followlinks=True) resolves them to real files so the bundle is COMPLETE -- otherwise
# PyInstaller stores dangling symlinks and the app ships without flags/audio/icons.
def _collect_assets(root):
    root = str(root)
    parent = os.path.dirname(root)
    out = []
    for dirpath, _dirs, files in os.walk(root, followlinks=True):
        for fn in files:
            if fn == ".DS_Store":
                continue
            out.append((os.path.join(dirpath, fn), os.path.relpath(dirpath, parent)))
    return out

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=_collect_assets(ROOT / "assets"),     # real files behind every symlink -> <bundle>/assets/...
    hiddenimports=["pygame._sdl2", "pygame._sdl2.controller"],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Steer",
    debug=False,
    strip=STRIP,
    upx=False,                  # UPX breaks codesign on macOS arm64 and triggers AV on Windows
    console=False,              # windowed app (no terminal)
    icon=ICON,
    target_arch=TARGET_ARCH,
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=STRIP, upx=False, name="Steer",
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
