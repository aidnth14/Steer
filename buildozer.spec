# Buildozer config to package Steer as an Android APK/AAB via python-for-android.
#
#   pip install buildozer cython
#   buildozer -v android debug          # -> bin/steer-*-debug.apk
#   buildozer android release           # signed AAB for the Play Store (set up a keystore)
#
# Run on Linux (or WSL2 / the android job in .github/workflows/build.yml). The first run
# downloads the Android SDK/NDK and takes a while.
#
# CAVEATS (Android is single-player only):
#   * pygame._sdl2.controller, webbrowser, subprocess and the os.execv hot-reload are no-ops
#     or unavailable on Android -- the game guards or simply never hits them in a shipped build.
#   * The websockets multiplayer client is not packaged (no `websockets` requirement here); the
#     lobby UI is reachable but connecting is a desktop feature. Keep players on Singleplayer.
#   * Touch maps to mouse, so menus work; in-race steering expects a keyboard/controller, so an
#     on-screen touch control layer is the main follow-up before shipping to players.

[app]
title = Steer
package.name = steer
package.domain = io.steer
source.dir = .
source.include_exts = py,png,jpg,ttf,otf,mp3,ogg,wav,json
source.include_patterns = assets/*,assets/**/*
# server/test/tooling files don't belong in the APK
source.exclude_patterns = packaging/*,tests.py,server.py,net.py,Dockerfile,docker-compose.yml,render.yaml,.github/*,*.md,*.log
version = 1.2.0
# plyer drives the accelerometer for gyro/tilt steering on Android
requirements = python3,pygame,plyer
orientation = landscape
fullscreen = 1
android.allow_backup = True

# API / build targets (reasonable 2024/2025 defaults; bump as Play requires)
android.api = 34
android.minapi = 24
android.ndk_api = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
