# Steer

2D top-down kart racing in pygame. The kart always drives forward: you steer, and you
fight. Bash rivals off the dirt road into the bushes before they do it to you.

## Run

```
cd ~/Desktop/steer
python3 main.py
```

## Controls

| Key | Does |
|---|---|
| `A` / `D` or `←` / `→` | steer |
| `Q` / `E` | side-bash left / right (a sideways lunge that shoves whoever you hit) |
| `Space` | ram (a forward lunge, for hitting someone from behind) |
| `Esc` | pause menu (Resume / New Race / Settings / Quit) |
| `R` | force a hot reload of `sim.py` |

Bashes share one cooldown (1.5 s); the bar under your hearts shows when it's ready.

**Controllers** (Xbox / PlayStation / Nintendo, via SDL's game-controller layer — one
mapping works for all three): left stick / d-pad steer, **LB / RB** side-bash, **A** ram,
**Start** pause. Menus: d-pad to move, **A** confirm, **B** back; in a lobby **A** toggles
ready. Hot-plug supported.

## Before a race

**Play** opens **Singleplayer / Multiplayer**. Either way you first hit the name screen:
type your name, then pick a flag (`<` / `>` buttons or the arrow keys cycle through 255
country flags).

- **Singleplayer** — 5–7 bots (random names + flags) on a fresh random track.
- **Multiplayer** — see below.

## Multiplayer (online co-op)

Real-time racing against friends over the internet. A small relay server (`server.py`)
holds the lobbies and forwards each player's car state; everyone runs the race locally and
stays in sync.

**Flow:** Play → Multiplayer → **Host** or **Join**.
- **Host:** choose max players (2–12) and create a lobby. You get a **6-character code**;
  the lobby is named after you.
- **Join:** type a friend's 6-character code.
- In the **lobby** everyone sees the player list (name + flag + ready state). Each player
  has a **Ready / Unready** button; the host can **kick** anyone (the red `x`). When every
  player is ready (min 2), the race **starts automatically** on the same track for all.

### Running the server

Locally:

```
PORT=8765 python server.py
# then point the game at it:
STEER_SERVER_URL=ws://localhost:8765 python main.py
```

On **Render** (free): push this repo to GitHub → Render → **New → Blueprint** → pick the
repo (`render.yaml` provisions a Web Service running `server.py`). Render gives you a URL
like `https://steer-server.onrender.com`; players then launch with:

```
STEER_SERVER_URL=wss://steer-server.onrender.com python main.py
```

(The client reads `STEER_SERVER_URL`; default is `ws://localhost:8765`.)

### How the netcode works

Each client simulates **only its own car** with full physics and broadcasts its state
~20×/s; the server relays those snapshots to the rest of the room, and remote cars are
smoothly interpolated toward them. No central physics, so the server stays cheap. Lobby,
ready-up, kick, auto-start, and host migration are all handled server-side.

## Files

- `main.py` — window, menus, input (keyboard + Xbox/PS/Nintendo controllers), game loop,
  multiplayer lobby UI, hot reload.
- `sim.py` — everything else: track, scenery, physics, collisions, bots, camera, drawing,
  sound, car state (de)serialization for multiplayer. Edit + save it and the running
  single-player game picks the change up live (state carries over).
- `net.py` — client networking: a background WebSocket thread the game polls each frame.
- `server.py` — the multiplayer relay/lobby server (deploy to Render; see Multiplayer).
- `assets/track_tiles/` — the dirt-on-grass road tiles (9-slice + 4 inner corners) plus
  `checktile.png`, the checkered start/finish line.
- `assets/bush_tiles/` — the square bush (9 pieces) and round bush (4 pieces).
- `assets/UI/` — HUD icons (the heart is drawn from `heart.png`).
- `assets/flags/` — 255 country flags, used for the player's and bots' flags.
- `assets/font/Jersey25-Regular.ttf` — the pixel font used for all UI text.
- `assets/*.png` — older single-image decorations; used too if present
  (`deco_*` are solid, `ground_*` are drive-over).

## What's built

- **Track**: a procedurally generated stadium loop (random seed per race), 15 tiles wide,
  drawn only from the road tiles. The same 16 px grid decides what's drawn and what counts
  as on/off the road.
- **Scenery**: square bushes in many sizes (stretched from the 9 pieces) and round bushes,
  packed as densely as fits (~1,500 per map) with a clear run-off strip beside the road and
  a bush wall around the map. All bushes are solid. Everything is baked into one image per
  map, so it costs nothing per frame.
- **Physics**: a tyre model (bicycle model with slip angles and a grip curve that falls
  off past its peak), so karts grip, slide, drift and can be caught; the always-on engine
  loosens the rear tyres (power oversteer); a stability assist stops slides snapping into
  spins; grass has less grip and much more drag. Karts are solid boxes with mass and spin:
  hits bounce, push and spin them depending on where they land. 4 physics steps per frame.
- **Bashing**: side-bash and ram lunges. While bashing you count as a heavier kart, and
  whoever you hit gets an extra shove, loose tyres for a moment and some spin.
- **Bots**: 5–7 per race (random), each with a personality (aggression, how they use the
  road, pace, weight) plus an auto-assigned name and flag. They race their own lanes, lean
  on rivals to push them, side-bash anyone alongside (more eagerly when it would knock them
  off the road), ram anyone just ahead, hold grudges against whoever hit them last, and one
  of them hunts you. Pack pacing keeps them around you, so the fighting doesn't drift away.
- **Cars**: drawn with sprite stacking (slices stacked for a pseudo-3D block) and a white
  roof outline; each car floats its name + flag above it.
- **Mystery boxes**: floating `?` boxes around the loop in three colours — yellow (speed
  boost), blue (+1 heart), red (instant bash recharge). Taken boxes respawn after 6 s.
- **Laps & leaderboard**: 3 laps per race. A live leaderboard under the bash meter shows the
  running order with each racer's flag and lap; finishing all laps shows a results screen.
- **Hearts**: 3; lose half a heart each time you leave the road.
- **Recovery**: a kart stuck against bushes backs up on its own; if it's still wedged
  after 3 s it's put back on the road.
- **Effects**: skid marks from real tyre slip, grass/dirt dust, impact sparks, screen shake.

## Not built yet

- No game-over state when hearts hit 0 (a `death` sound plays, but the car keeps going).
- Multiplayer has no player-vs-player physics authority — remote cars are interpolated
  from their own snapshots, so collisions between players are approximate.

## Tuning (all constants at the top of `sim.py`)

- Track: `ROAD_WIDTH`, `OFFROAD_RANGE`, `EDGE_GRACE`
- Scenery: `BUSH_BLOCK_SIZES`, `ROUND_BUSH_WEIGHT`, `OLD_DECOS`, `RUNOFF`, `DECO_GAP`,
  `ARENA_MARGIN`, `DECO_ATTEMPTS`, `DECO_GROW_TRIES`
- Engine: `MAX_SPEED`, `ENGINE_ACCEL`, `ENGINE_FALLOFF`, `ROLL_RESIST`, `AIR_DRAG`
- Tyres: `GRIP`, `TIRE_PEAK_SLIP`, `TIRE_SHAPE`, `DRIVE_GRIP_USE`, `STEER_MAX`,
  `STEER_GRIP_RATIO`, `STEER_RATE`, `STABILITY`
- Grass: `GRASS_GRIP`, `GRASS_ENGINE_LOSS`, `GRASS_RESIST`
- Collisions: `CAR_RESTITUTION`, `CAR_FRICTION`, `WALL_RESTITUTION`, `WALL_FRICTION`, `MAX_SPIN`
- Bashing: `BASH_COOLDOWN`, `BASH_SIDE_SPEED`, `RAM_SPEED`, `BASH_MASS`, `BASH_KNOCK`,
  `BASH_SPIN`, `STAGGER_TIME`, `STAGGER_GRIP`
- Bots: `BOT_PROFILES`, `BOT_NAMES`, `AI_BASH_RATE`, `AI_RAM_RATE`, `AI_PACK_RANGE`,
  `AI_CATCHUP`, `AI_EASE`
- Hearts: `HEART_COUNT`, `HEART_PENALTY`, `HEART_COOLDOWN`
- Mystery boxes: `BOX_COUNT`, `BOX_TYPES`, `BOX_COLORS`, `BOX_RESPAWN`, `BOOST_TIME`,
  `BOOST_PACE`, `BOOST_KICK`
- Laps / cars: `TOTAL_LAPS`, `STACK_LAYERS`
