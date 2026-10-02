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

## Before a race

Hitting **Play** / **New Race** opens the name screen: type your name, then pick a flag
(`<` / `>` buttons or the arrow keys cycle through 255 country flags). Bots get random
names and flags automatically. Each race drops in 5–7 bots on a fresh random track.

## Files

- `main.py` — window, menus, input, game loop, hot reload.
- `sim.py` — everything else: track, scenery, physics, collisions, bots, camera, drawing.
  Edit + save it and the running game picks the change up live (state carries over).
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

- No game-over state when hearts hit 0.
- No sound.

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
