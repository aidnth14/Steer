# Shipping Steer

Packaging materials for the desktop client (Linux, macOS Intel + Apple Silicon, Windows) and
Android. The multiplayer **server** ships separately as a container — see the root `Dockerfile`
and `render.yaml`.

## How assets are found
`sim.py` resolves assets as `os.path.dirname(__file__)/assets`. Every builder here bundles the
`assets/` tree at the bundle root, so that path resolves identically whether you run from source
or from a frozen app — no code changes needed. The hot-reload / `os.execv` restart only fires
when `main.py`/`sim.py` change on disk, which never happens in a shipped build (the `getmtime`
check fails closed), so frozen apps are safe.

## Desktop (Linux / macOS)
PyInstaller can't cross-compile — build on each OS/arch you want to ship.

```bash
./packaging/build_desktop.sh
```

- Linux → `dist/Steer/` (run `dist/Steer/Steer`)
- macOS → `dist/Steer.app` — build **twice**: once on an Intel Mac (x86_64) and once on an
  Apple-Silicon Mac (arm64) for `macos-intel` and `macos-applesilicon` artifacts.

## Desktop (Windows)
```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```
→ `dist\Steer\Steer.exe`

## Android
```bash
pip install buildozer cython
buildozer -v android debug      # -> bin/steer-*-debug.apk
```
Config is the root `buildozer.spec`. First run downloads the Android SDK/NDK. **Android is
single-player only** today — multiplayer (websockets), gamepad `_sdl2.controller`, `webbrowser`
and the hot-reload are desktop-only and are excluded or unused on Android. In-race steering still
expects a keyboard/controller, so adding an on-screen touch control overlay is the main task
before putting it in front of phone players.

## CI
`.github/workflows/build.yml` builds all five targets (linux, macos-intel, macos-applesilicon,
windows, android) on tag pushes (`v*`) or manual dispatch, and uploads each as an artifact.

## Signing & stores (not automated here)
- **macOS**: codesign + notarize the `.app` (`codesign --deep --sign`, `notarytool`) or users
  hit Gatekeeper.
- **Windows**: an Authenticode cert avoids SmartScreen warnings.
- **Android**: `buildozer android release` produces an AAB; set up a keystore for the Play Store.
