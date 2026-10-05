# Steer — Web (TypeScript + Django)

Full rewrite of [Steer](../README.md) for the browser: a TypeScript game engine (Canvas 2D) talking
to a Django + Channels backend over WebSockets. Independent codebase from the Python game — no
shared code, just the same design (and the same tuned physics numbers, ported by hand).

This supersedes the earlier pygbag/WASM port (deleted, branch and all) per owner's request to
rebuild natively instead of compiling the Python build to WASM.

## Status

**Working now:**
- Procedural track generation (all 6 shapes: stadium, peanut, teardrop, tri-oval, chicane, kidney),
  ported from `sim.py`'s Catmull-Rom/parametric curve generator.
- Full tyre physics (slip-angle grip curve, power oversteer, drift, grass penalty, stability
  assist, wrong-way correction, stuck/rescue) — same constants as `sim.py`, verified with a
  headless Node smoke test (no NaNs, reaches ~MAX_SPEED, makes track progress, drift leaves a
  skid trail).
- Hearts / off-road / elimination.
- Camera follow (position + velocity-weighted rotation, matching `sim.py`'s `Camera`).
- Canvas 2D renderer: road, car, skid trail, HUD (hearts, lap, wrong-way, game over).
- Keyboard input (A/D steer, Shift drift, S brake, Q/E bash-impulse plumbing — not yet wired to
  gameplay payoff, see below).
- Django + Channels multiplayer backend: a `LobbyConsumer` ported from `server.py`'s
  host/join/ready/settings/kick/ban/auto-start/state-relay protocol, **same wire format** as the
  Python server. Verified end-to-end (host, join, ready, auto-start, state relay) against a
  running dev server.
- `accounts.Profile` model (data layer) mirroring `~/.steer_profile.json`'s fields.
- Django serves the built frontend (`frontend/dist`) directly.

**Not yet ported** (next milestones, in rough priority order):
1. Bots/AI (`make_bot`, personality-driven steering/bashing in `sim.py`).
2. Car-car and car-wall collisions (karts currently pass through each other and the fence).
3. Wiring bashing into the gameplay loop (the physics impulse exists on `Car`, but there's
   nothing to bash yet without #1/#2).
4. Game modes beyond free driving (Time Trial, Elimination, Battle, Team Race).
5. Menus/settings UI (`ui.py`'s pixel-art kit — title screen, pause, settings tabs, lobby UI).
6. `net.ts`: a WebSocket client wiring the frontend to the Channels lobby (the backend protocol
   is ready and tested; nothing in the frontend speaks it yet).
7. Touch/gyro mobile controls (the old pygbag port had these; not started here).
8. Sprite art + sound (current renderer is flat-shaded placeholder shapes, silent).
9. Accounts auth views/forms (the `Profile` model exists; no signup/login/settings-sync views yet).

## Run it

Backend:
```
cd steerweb/backend
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 8000   # daphne (in INSTALLED_APPS) serves ASGI, incl. the /ws/lobby/ websocket
```

Frontend (dev, hot reload):
```
cd steerweb/frontend
npm install
npm run dev
```

Frontend (production build, served by Django):
```
cd steerweb/frontend && npm run build
cd ../backend && python manage.py runserver 8000   # now serves the built game at /
```
