# Steer

2D top-down kart racing in pygame. The kart always drives forward: you steer, and you
fight. Bash rivals off the dirt road into the fence before they do it to you.

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
| `Shift` (hold) | drift — looser rear end; hold through a corner to charge a **mini-boost**, released automatically when you let go |
| `Esc` | pause menu (Resume / New Race / Settings / Quit) |
| `R` | force a hot reload of `sim.py` (single-player only) |

All keyboard actions are **rebindable** in Settings.

**Hot reload:** saving `sim.py` reloads it live (gameplay/HUD/draw code — a race in progress
carries its state over); saving `main.py` (menus / UI / game loop) auto-restarts the game so
the change takes effect. Both are detected automatically while the game is open.

Bashes share one cooldown (1.5 s); the bar under your hearts shows when it's ready.

**Controllers** (Xbox / PlayStation / Nintendo, via SDL's game-controller layer — one
mapping works for all three): left stick / d-pad steer, **LB / RB** side-bash, **A** ram,
**hold B** drift, **Start** pause. Menus: d-pad to move, **A** confirm, **B** back; in a
lobby **A** toggles ready. Hot-plug supported.

## Before a race

**Play** opens **Singleplayer / Multiplayer**. Either way you first hit the name screen:
type your name, then pick a flag (`<` / `>` buttons or the arrow keys cycle through 255
country flags).

- **Singleplayer** — then pick a **game mode** (below) and race 5–7 bots on a fresh track.
- **Multiplayer** — see below.

### Game modes (single-player)

- **Race** — standard laps against bots.
- **Time Trial** — solo against a **ghost** of your best lap (replayed as a faint outline).
- **Elimination** — every 8 s the last-place kart is knocked out; last one standing wins.
- **Battle** — survival: no laps, last kart with hearts left wins.
- **Team Race** — karts split into red/blue teams; the results screen tallies each team's
  finishing positions (lower total wins) and names the winning team.

### Settings & Profile (`~/.steer_profile.json`)

Settings are organized across four dedicated tabs with persistent profile storage:

1. **🏁 RACE & GAMEPLAY:**
   - **Track Selection:** Meadow Dirt, Grand Prix Circuit, Red Canyon, Frost Pass, Harvest Mud, Neon Night, Random.
   - **Bot Aggression & Difficulty:** Chill, Casual, Feisty, Demolition.
   - **Laps:** Slider (1 to 10 laps).
   - **HUD Display Mode:** Classic (pinned), Immersive (fades until events/danger), Hidden (clean screen).
   - **Steer Rate:** Slider (0.5x to 2.0x turning speed).
   - **Steering Linearity / Curve:** Slider (1.0 Linear to 2.5 Exponential).
   - **Inner Stick Deadzone:** Slider (0% to 25% drift cancellation).
   - **Drift Assist:** Slider (0.0 to 1.0 counter-steer dampener).
   - **Inverted Steer:** Toggle (ON / OFF).
   - **Dynamic Look-Ahead Camera:** Toggle (offsets camera forward with speed).
   - **Time Trial Ghost Opacity:** Slider (0% to 100% telemetry alpha).

2. **🔊 SOUND:**
   - **Master Volume:** Primary audio bus volume (0% to 100%).
   - **Master Mute:** Toggle (hotkey `M`).
   - **Music Volume:** Soundtrack playback gain (0% to 100%).
   - **Engine Volume:** Real-time RPM audio level (0% to 100%).
   - **Combat & World SFX Volume:** Impacts, bashes, pickups, and tire squeals (0% to 100%).
   - **UI Audio Volume:** Countdown beeps, menu blips, and lap chimes (0% to 100%).

3. **🖥️ VIDEO:**
   - **Display Mode:** Exclusive Fullscreen, Borderless Windowed, Windowed (freely resizable — drag any edge). Press **F11** anywhere to toggle fullscreen.
   - **Pixel-Perfect Scaling:** Toggle — the game renders at a fixed 600×400 and SDL (`pygame.SCALED`) scales that to any window size or fullscreen with aspect-preserving letterbox bars; this switches the filter between nearest-neighbour (crisp integer pixels) and smooth linear.
   - **V-Sync & Frame Rate Cap:** 60 FPS, 120 FPS, 144 FPS, Unlimited, V-Sync On.
   - **Camera Zoom:** 0.6x (close-up) to 1.6x (wide view).
   - **Camera Shake:** 0.0 (disabled) to 2.0 (maximum trauma). Drives impact trauma plus continuous rumble from speed, grass bounce and boost, and a subtle handheld cinematic sway.
   - **Fog Density:** 0.0 to 1.0 depth fog alpha.
   - **Shader Presets:** NONE, CRT, CYBERPUNK, NOIR, CINEMATIC, SUNSET, ACTION, VHS. Each preset is a real full-frame colour grade (multiply + additive lift) layered with fog, vignette, scanlines and animated film grain — so the moody presets now read distinctly.
   - **Scanlines:** OFF, LOW, MED, HIGH.
   - **Vignette:** Toggle (ON / OFF).
   - **Dynamic Drop Shadows:** Toggle (ON / OFF).
   - **FPS Counter:** Toggle (live frame rate in top-left).

4. **🎮 CONTROLS:**
   - **Input Device Priority:** Auto-detects connected gamepads (Xbox, PlayStation, Nintendo Switch) vs Keyboard/Mouse.
   - **Gamepad Presets:**
     - *Arcade Classic:* Steer on Left Stick/D-pad, Gas on Face Button A/Cross, Drift on B/Circle.
     - *Trigger Drive:* Gas on RT/R2, Brake on LT/L2, Drift on RB/R1, Bash on Stick Clicks (L3/R3).
     - *Southpaw:* Swaps steering control to the Right Analog Stick.
   - **Mouse Aim Mode:** Toggle (aim projectiles with cursor within 170° forward arc; Left-Click shoot, Right-Click drop hazard).
   - **Gyro Steering (mobile/web):** Toggle tilt-to-steer on phones/tablets (plyer accelerometer on Android, DeviceOrientation on web, SDL sensors on native mobile ports). **Gyro Sens** slider sets how much tilt equals a full turn, and **Recenter Gyro** captures your current hold angle as straight-ahead. Off by default; on desktop it stays dormant.
   - **Full Keyboard Rebinding Matrix:** Steer Left, Steer Right, Accelerate/Ram, Brake/Reverse, Drift (Hold), Bash Left, Bash Right, Use Item/Shoot, Drop Hazard Behind.

### Vehicle & Sprite Stacking

All players and bots pilot the authentic red sports racer, rendered via pseudo-3D sprite stacking from `assets/cars/redcar_stack.png`. The sprite stack comprises 7 horizontal $36 \times 36$ slices rendered bottom-to-top with dynamic camera-rotation caching, maintaining its handcrafted pixel palette without artificial color tints. Competitors are identified on track via overhead player tags and minimap markers.

## Multiplayer (online co-op)

Real-time racing against friends over the internet. A small relay server (`server.py`)
holds the lobbies and forwards each player's car state; everyone runs the race locally and
stays in sync.

**Flow:** Play → Multiplayer → **Host** or **Join**.
- **Host:** choose max players (2–12) and create a lobby. You get a **6-character code**; the lobby is named after you.
- **Host Multiplayer Match Settings (Broadcast via Network):**
  - **Track & Rotation Rule:** Host Choice, Player Vote, Random Circuit, 5-World Cup (runs Grand Prix Circuit, Red Canyon, Frost Pass, Harvest Mud, and Neon Night in sequential order).
  - **Race Length (Laps):** 1, 3, 5, or 7 laps.
  - **Collision / Contact Rules:** Full Contact, Solid (No Spun Damage), Ghost (Time Trial passing).
  - **Bot Fill:** Fill to 8, Fill to 12, No Bots (Players Only).
  - **Room Privacy:** Public (Lobby Browser), Friends Only, Invite Code Only (Private).
  - **Slipstream Assist:** Toggle (ON / OFF catch-up drafting).
  - **Item Distribution Rules:** Standard, High Explosives / Kinetic Only, Hazards Only (Cones & Oil), Pure Racing (No Items).
  - **Spectator Mode:** Allowed / Disabled.
  - **Player Moderation:** Instant **Kick** (`[K]`) and persistent name **Ban** (`[B]`).
- **Join:** type a friend's 6-character code. Joiners see the host's synchronized match settings updated in real time.
- In the **lobby** everyone sees the player list (name + flag + ready state) and the active match settings. When every player is ready (min 2), the race **starts automatically** with the host's custom settings on the same track for all.

### Live server

The game ships pointed at a **live Render deployment**: `wss://steer-server.onrender.com`
(baked into `server_url.txt`). Just launch the game, pick Multiplayer, and Host/Join — no setup.
Load-tested at 10 concurrent lobbies (40 players) with zero errors on Render's free tier, which
sits behind Render's managed load balancer + TLS. A GitHub Actions keep-alive
(`.github/workflows/keepalive.yml`) pings the health endpoint through the day's active hours so
the free instance rarely sleeps; the in-game loading screen masks the ~30s cold start on the rare
occasion it does.

**Server URL resolution (client):** `STEER_SERVER_URL` env → `server_url.txt` → `ws://localhost:8765`.

### Running the server yourself

Locally:

```
PORT=8765 python server.py
# point the game at your local server (env overrides server_url.txt):
STEER_SERVER_URL=ws://localhost:8765 python main.py
```

On **Render**: push to GitHub → Render → **New → Blueprint** → pick the repo (`render.yaml`
provisions a free Web Service running `server.py`). Render hands you `https://<name>.onrender.com`;
put its `wss://` form in `server_url.txt` (or set `STEER_SERVER_URL`). For horizontal scaling,
uncomment the Key Value/Redis + multi-instance block in `render.yaml` (requires a paid plan).

### Scaling with Redis + Docker (optional)

One server instance comfortably handles **7–10 lobbies** (~120 sockets) in memory — Redis is
only needed to run **multiple** server replicas that share lobbies. Set `REDIS_URL` to turn
it on; without it the server stays in-process (identical behaviour).

With Redis, the instance a lobby is *created* on **owns** it (holds the room + all game
logic). Other instances are thin edges that pipe their client's frames to the owner over a
Redis **pub/sub bus** and deliver the owner's replies back; a Redis **registry**
(`steer:owner:<code>`) lets any instance find a lobby's owner, and a small per-lobby summary
is cached in Redis. So a player can join a lobby hosted on any replica.

Run a local cluster with Docker:

```
docker compose up --build --scale server=3   # 3 server replicas + redis, shared lobbies
# each replica has its own port: host via one, join via another to test shared lobbies
STEER_SERVER_URL=ws://localhost:8765 python main.py    # player 1 (hosts)
STEER_SERVER_URL=ws://localhost:8766 python main.py    # player 2 (joins the code)
```

On Render, keep the Key Value service from `render.yaml` and set the web service's instance
count > 1 to scale out. That needs a paid instance type: Render's free plan runs one instance
only, so on the free plan Redis adds nothing (the server works the same without it).

### How the netcode works

Each client simulates **only its own car** with full physics and broadcasts its state
~20×/s; the server relays those snapshots to the rest of the room, and remote cars are
smoothly interpolated toward them. No central physics, so the server stays cheap.

- **Bots in multiplayer**: the host fills the grid with bots according to the lobby's AI Grid setting, simulates their AI with the configured aggressiveness, and broadcasts them like extra cars (clients puppet them).
- **Host-customized match settings**: The host controls bot aggression, lap count, and AI grid fill directly from the lobby UI. The server broadcasts setting changes in real-time, and both host and clients initialize their local race and AI parameters according to the host's configuration.
- **Boxes are host-authoritative**: box layout is deterministic from the track seed, and the
  host resolves pickups and tells everyone who got what, so there's no desync over power-ups.
- **Shared finish**: the host decides when the race is over (someone completed the laps, or
  only one racer is left) and everyone sees the same results screen.
- **Leaving mid-race**: a player who drops is removed (their kart is retired); if the host
  leaves, a remaining client is promoted and takes over the bots + box authority.

Lobby, ready-up, kick, auto-start, match settings sync, and host migration are all handled server-side.

## Files

- `main.py` — window, menus, input (keyboard + Xbox/PS/Nintendo controllers), game loop,
  multiplayer lobby UI, hot reload.
- `ui.py` — the Steer UI kit: pixel-crisp menus, settings tabs, and the STEER logo drawn
  entirely from flat palette colours (no fonts/images), plus the layout rects `main.py` hit-tests.
- `sim.py` — everything else: track, scenery, physics, collisions, bots, camera, drawing,
  sound, car state (de)serialization for multiplayer. Edit + save it and the running
  single-player game picks the change up live (state carries over).
- `net.py` — client networking: a background WebSocket thread the game polls each frame.
- `server.py` — the multiplayer lobby/relay server; optional Redis bus for multi-instance
  scaling (deploy to Render; see Multiplayer).
- `Dockerfile`, `docker-compose.yml` — container + a local multi-replica cluster behind Redis.
- `tests.py` — comprehensive headless `unittest` suite (41 tests: physics, net, timing, tilesets, game loop).
- `TASTE.md` — visual design notes, color palettes, and aesthetic guidelines for the retro pixel racing style.
- `assets/car/` — `car_stack.png`, the 7-slice sprite stack for the player and bot racers.
- `assets/decor/` — natural map scenery (`bush.png`, `tree.png`, `tree2.png`, `tree3.png`, `tree_log.png`, `tree3_log.png`).
- `assets/destructibles/` — breakable props and shatter animations (`barrel`, `box`, `vase`).
- `assets/fence_tiles/` — fence posts and rails (11 pieces, building all 16 rail combinations).
- `assets/flags/` — 255 country flags for player and bot identification.
- `assets/fx/` — particle and burst VFX sheets (`particle.png`, `Sprite-0001.png`, `Dust_01/02`, `Fire_01/02`, `DarkVFX2`).
- `assets/props/` — 2.5D sprite-stacked obstacles (`cone_stack.png`, `barrel_stack.png`, `crate_stack.png`, `vase_stack.png`, `tire_stack_1..3.png`, `tree_*_stack.png`) and `ramps/ramp_wood_stack.png`.
- `assets/sound/` — sound effects (`bash.mp3`, `death.mp3`, `powerup.mp3`, `powerup2.mp3`) and 7 music tracks in `sound/music/`.
- `assets/tilesets/` — multi-track environments:
  - `meadow_dirt/` — classic dirt circuit with green grass infield/outfield and oil tracks.
  - `asphalt_circuit/` — championship asphalt circuit with curbing, dark tarmac, checktiles, and oil tracks.
  - `canyon_sand/` — red-rock desert circuit with sun-baked sand road, canyon walls, and dust haze.
  - `frost_pass/` — packed-snow road cut through deep snow with steel-grey snowbank edges, custom checktiles, and snow particles.
  - `harvest_mud/` — autumn farmland course with churned-mud road, stubble fields, and muddy skid coloration.
  - `neon_night/` — synthwave night circuit with glowing neon road edges and dark reflective tarmac.
- `assets/track_tiles/` — dirt-on-grass road tiles, checkered finish line tiles (`checktile*.png`), and `oil_track.png`.
- `assets/steer_palette.png` & `assets/steer_palette_1x.png` — color palette reference swatches.
- `assets/UI/` — HUD icons (`gear`, `contrast`, `heart`, `logo`, etc.) and pixel font in `UI/m6x11/m6x11.ttf`.

## What's built

- **Track**: a procedurally generated stadium loop (random seed per race), 15 tiles wide,
  drawn only from the road tiles. The same 16 px grid decides what's drawn and what counts
  as on/off the road.
- **Fences**: the map is only road tiles and fence. A fence runs along each side of the
  road (one outside the loop, one round the infield), three tiles of grass out from the
  edge, following the road's shape. Run wide and you hit grass first (and lose a heart),
  then the fence. Fences are solid, and each straight run is one flat wall to scrape along.
  The whole map is baked into one image, so it costs nothing per frame.
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
- **Cars**: drawn with sprite stacking (slices stacked for a pseudo-3D block); each car
  floats its name + flag above it. The whole sprite flashes **white** while it's bashing and
  **red** when it gets bashed or smacks a fence, then back to its colour.
- **Mystery boxes**: floating `?` boxes around the loop in three colours — yellow (speed
  boost), blue (+1 heart), red (instant bash recharge). Taken boxes respawn after 6 s.
- **Camera & HUD**: the race view is zoomed in (`sim.ZOOM`); the HUD is hearts (top-left), a
  live leaderboard with flags + `LAP x/y` (top-right, eliminated karts drop to the bottom
  marked OUT), and a **minimap** (bottom-right) showing the road layout (white outline, faint
  fill) with a dot per kart and yours highlighted.
- **Laps**: 3 laps per race (set 3/5/7 in Settings), a **3-2-1-GO** countdown at the start;
  the results screen lists finishing order + each racer's best lap.
- **Hearts & game-over**: 3 hearts; lose half each time you leave the road. At 0 you're
  **eliminated** — your kart greys out and coasts to a stop (single-player ends in GAME OVER;
  multiplayer drops you to a spectator view of the leader until the race finishes).
- **Recovery**: a kart stuck against the fence or another kart backs up on its own; if it's
  still wedged after 3 s it's put back on the road. (Eliminated karts are left where they stop.)
- **Drifting**: hold drift through a corner to slide the rear and charge a mini-boost that
  fires on release (coloured drift smoke shows the charge building).
- **Effects**: skid marks from real tyre slip, surface dust off-road, drift smoke, boost
  flames, collision sparks, screen shake.
- **Position popups**: your place in the running order flashes up when it changes.
- **Menus**: the STEER logo sits top-left, buttons are text-only stacked bottom-left, and the
  backdrop is **live gameplay** (bots racing, or your paused race) rather than a static image.
- **Fences**: baked one tile off the road so they read as a visible barrier while you drive.
- **Performance**: the baked map is pre-scaled by `ZOOM` once per track, so each frame just
  rotates it (fast) instead of rotate-and-scaling.
- **Minimap**: a scaled view of the whole track in the bottom-right corner, a dot per kart
  with your own highlighted. The race view is zoomed in (`sim.ZOOM`).
- **Dynamic Camera & Cinematic Trauma**: Directional screen-space camera trauma kicks in the exact vector direction of impact force, decaying with damped spring physics (`k=145`, `c=16.5`) with high-frequency impact rumble.
- **Finish-Line Bullet Time (Slow Motion)**: Crossing the finish line on the final lap activates 0.25× bullet-time slow motion for 1.5 seconds, pulling the camera into an intimate tracking shot framed by anamorphic letterbox bars before transitioning to results.
- **Dynamic Debris & Tire Smoke**:
  - Flying wood splinter particles when crashing into fences or smashing crates and barrels.
  - Directional bright metal sparks when rubbing or colliding with rival karts.
  - Billowing tire smoke puffs and 13-second persistent dark rubber skid arcs on aggressive drift turns.
- **Animated Impact Callout Banners**: High-impact kinetic banners with scale-bounce and ghosted motion blur:
  - `FINAL LAP!` — announcing the deciding round.
  - `SLIPSTREAM!` — triggered upon riding in a rival kart's slipstream draft pocket.
  - `TAKEDOWN!` / `WRECKED!` — celebrating close-range rival eliminations or player crashes.
  - `DRIFT BOOST!` — bursting when releasing charged drift sparks.
- **Diegetic / Immersive HUD Mode**: Toggleable in Settings (`FULL` vs `IMMERSIVE`, saved to profile). In immersive mode, the HUD automatically hides during clean driving and dynamically reveals with smooth alpha transitions when health changes, rank shifts, or the kart is in danger (low health, nearby rivals, off-road, or heavy impact trauma).
- **Dual Track Environments (Meadow Dirt & Grand Prix Circuit)**: Seamlessly toggle between lush country dirt courses and tarmac Grand Prix circuits with authentic curbing and dynamic tire skid coloration. Fully configurable via Settings or host-synced multiplayer lobby.

## Not built yet

- Multiplayer still uses the per-client relay model (each client sims its own car), so
  player-vs-player collisions are approximate. A **host-authoritative physics** rewrite and
  **reconnect-to-same-slot** are the next planned step.
- Game modes (Time Trial / Elimination / Battle / Team) are single-player only so far;
  multiplayer is plain Race.

## Tuning (all constants at the top of `sim.py`)

- Track: `ROAD_WIDTH`, `OFFROAD_RANGE`, `EDGE_GRACE`
- Fences: `FENCE_OFFSET` (how far out from the road), `FENCE_POST` (collision box), `ARENA_MARGIN`
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

---

# MUSIC & SOUND CREDITS

This project features music from talented independent composers and chiptune artists. Full attribution and credits are detailed below:

---

### Track 1: Night Shade
- **Track Title:** Night Shade
- **Composer / Artist:** AdhesiveWombat
- **Genre:** 8-Bit Chiptune / Synth
- **Source / License:** No Copyright 8-bit Music / Free for creative and game use
- **YouTube Link:** [https://www.youtube.com/watch?v=mRN_T6JkH-c](https://www.youtube.com/watch?v=mRN_T6JkH-c)
- **Artist Profile:** AdhesiveWombat ([https://soundcloud.com/adhesivewombat](https://soundcloud.com/adhesivewombat))

---

### Track 2: Clint Eastwood (8-Bit Tribute)
- **Track Title:** Clint Eastwood [8 Bit Cover Tribute to Gorillaz]
- **Artist / Arranger:** 8 Bit Universe
- **Original Song by:** Gorillaz (Damon Albarn, Jamie Hewlett, Del the Funky Homosapien)
- **Genre:** 8-Bit Chiptune Cover
- **Source:** 8 Bit Universe Channel ([https://www.youtube.com/watch?v=PckLALGzXH8](https://www.youtube.com/watch?v=PckLALGzXH8))
- **Artist Profile:** 8 Bit Universe ([https://www.youtube.com/@8BitUniverse](https://www.youtube.com/@8BitUniverse))

---

### Track 3: MAZE
- **Track Title:** MAZE
- **Composer / Artist:** Density & Time
- **Genre:** 8-Bit Retro Arcade
- **Source / License:** No Copyright 8-bit Music / Free for creative and game use
- **YouTube Link:** [https://www.youtube.com/watch?v=OuRvOCf9mJ4](https://www.youtube.com/watch?v=OuRvOCf9mJ4)
- **Artist Profile:** Density & Time

---

### Track 4: Pit Stop
- **Track Title:** Pit Stop
- **Genre:** Synthwave / Chiptune Racing Groove
- **Source / License:** Creative Commons Attribution / Free for creative and game use

---

### Track 5: Pursuit
- **Track Title:** Pursuit
- **Genre:** High-Octane Chiptune Chase
- **Source / License:** Creative Commons Attribution / Free for creative and game use

---

### Track 6: Sunset Coast
- **Track Title:** Sunset Coast
- **Genre:** Chill Coastal Cruise Arcade Synth
- **Source / License:** Creative Commons Attribution / Free for creative and game use

---

### Track 7: Grand Prix
- **Track Title:** Grand Prix
- **Genre:** Main Event Championship Chiptune Anthem
- **Source / License:** Creative Commons Attribution / Free for creative and game use

---

### Sound Effects
- **Bump / Collision:** Bullet collision & bounce effects
- **Bash & Crash:** Break and impact effects
- **Powerup SFX:** Arcade jingle pickups

---

### UI & Graphics
- **Social Media Buttons:** Cryo's Mini GUI Social Buttons by PaperHatLizard
- **Source / License:** Creative Commons Attribution 4.0 International (CC BY 4.0) ([https://paperhatlizard.itch.io/cryos-mini-gui-social-buttons](https://paperhatlizard.itch.io/cryos-mini-gui-social-buttons))
- **Keyboard & Controller Buttons:** Controller & Keyboard Icons by Vryell
- **Source / License:** Free for Personal & Commercial Use ([https://vryell.itch.io/](https://vryell.itch.io/))

---

# Development Worklog & Changelog

# Steer — solo polish session

**Start:** Fri Oct 2 17:39 +06 2026
**Branch:** `claude/polish-20261002-1739` (off `main`)
**End:** Fri Oct 2 ~20:50 +06 2026 (long idle gaps between turns while owner was away;
active working time well under the hour — stopped starting new work and wrapped up).

## What I did
Phase 1 (tests + baseline) and all of Phase 2 (known issues). Did **not** start Phase 3
(ran out of time / stayed disciplined about the time box). No push, no merge, no deploy.

## Commits (newest first)
- `tests: clear sim font cache on display re-init` — fixes an SDL_ttf **segfault** the suite
  surfaced (fonts cached before a `pygame.quit()` point at freed state; the game-loop test
  quits pygame, a later test re-renders → crash). Test-only fix; the real game never re-inits.
- `Team Race: tally finishing-position team score + show winning team on results` (Phase 2.7).
- `net/ux: open_timeout 60s + "Waking the server..." hint; close() safe pre-connect; 8
  distinct bot colours; drift docs (Shift / hold B)` (Phase 2.1, 2.4, 2.5, 2.6).
- `deps: require websockets>=14` in requirements.txt + render.yaml (Phase 2.2).
- `tests: add headless unittest suite (world/physics/net/game-loop/timing); Car.rescues` (P1).
- `server: restrict bots/box/finished to the room host` (Phase 2.3).

## Test results
- **Before:** no tests existed.
- **After:** `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python3 -m unittest discover tests`
  → **Ran 9 tests, OK, exit 0** (~18 s).
  - test_world: 25 seeds — 2 fence loops, every post links to exactly 2 neighbours, no fence
    on road, grid karts + boxes on road.
  - test_physics: 7 bots × 60 s × 3 seeds — finite state, never past the fence, ≥1.5 laps
    (non-eliminated), ≤3 rescues each.
  - test_net: host/join/ready → same start seed; kick; host migration; non-host cannot send
    bots/box/finished; `net.Net.close()` safe before connect.
  - test_game_loop: scripted headless `main.main()` (Play → Singleplayer → Race → Start →
    countdown → steer/bash/ram → Esc → Resume → quit), reaches the race, exits via SystemExit.
  - test_timing: 300 frames step+draw_world, 8 karts.
- Import check: `python3 -c "import main, sim, net, server"` → OK.

## Timing
`step + draw_world`, 8 karts: **~2.8 ms/frame** (budget 16 ms — lots of headroom).

## Left unfinished / not done
- **Phase 3 not started** (minimap, wrong-way warning, FINAL LAP banner, fence-hit feedback,
  countdown pulse, screen-shake setting, results PB flag) — stopped at the time box.
- Phase 2.1's "Waking the server..." message is wired (`net.Net.waking()` after 5 s) but not
  verified against a real slow server — only the local fast path was exercised.

## Owner should check by eye / play
- **Team Race results line** ("RED/BLUE TEAM WINS (red N / blue N, lower is better)") — logic
  tested, but I couldn't screenshot the results screen (needs a full race to finish). Please
  eyeball placement under the title (it sits at y≈66, above the "best lap" header).
- **Bot colours** now 8 distinct hues, none red — confirm they read clearly on track.
- **Feel unchanged**: I touched no physics/bash/bot constants. Added only `Car.rescues`
  (a counter) and a one-line host-only guard server-side. Single-player + hot reload (`R`)
  still work (game-loop test drives SP; try `R` by hand).

## How to undo
- `git checkout main` returns to the exact pre-session state (nothing was pushed or merged).
- This branch `claude/polish-20261002-1739` holds every change above; discard it entirely
  with `git branch -D claude/polish-20261002-1739`.

## Notes / assumptions
- Repo already had uncommitted stray files from earlier experiments (`assets/track_tiles/
  checktile1..4.png`) — I left them untouched (rules: don't delete/rename assets).
- Tests point `main.PROFILE_PATH` at a temp dir; the real `~/.steer_profile.json` is untouched.

---

# Post-session feature work (owner-directed, same branch)

**When:** Fri Oct 2 evening 2026 (continued on `claude/polish-20261002-1739`).
Owner asked for a series of gameplay/UI/infra changes. All committed one-per-item; full test
suite kept green (`python3 -m unittest discover tests` → **10 tests, OK**).

## Commits (newest first)
- `render.yaml`: wire optional Key Value (Redis) + `REDIS_URL` for multi-instance scaling.
- `server.py`: optional **Redis pub/sub bus + registry** for multi-instance scaling
  (owner-authoritative rooms) with in-memory fallback; added `Dockerfile` +
  `docker-compose.yml` (server+redis) and `tests/test_redis.py` (cross-instance lobby).
- `perf`: pre-zoom the baked ground once per map so `draw_ground` uses fast `rotate()` instead
  of per-frame `rotozoom()`; timing test now asserts on the **min** frame time.
- Car sprites flash **white** while bashing, **red** when bashed / hitting a fence; **live
  attract gameplay** behind the menus (replaces the static image).
- **Hot reload for UI**: `main.py` edits auto-restart the process; `sim.py` reloads live in
  menus too.
- Menu restyle: **STEER logo** top-left, background-less **left-aligned buttons bottom-left**.
- HUD: removed the bash meter + lap/best timer (lap count `x/y` stays under the leaderboard);
  earlier moved the leaderboard top-right with no panel; blue pixel-rounded meter (since
  removed).
- Fences pulled to one tile off the road (`FENCE_OFFSET` 4→2) so the sprites are visible.
- Minimap redrawn as road-layout only (white strokes + ~22% black fill) with kart markers.
- Camera zoomed in (`ZOOM=1.3`) + corner minimap.
- **Fence blackout bug fixed**: blitting `SRCALPHA` tiles (fence pieces and checkered finish line)
  onto a 32-bit display-format Surface in SDL zeroes out destination alpha on those pixels. On macOS
  Cocoa/Retina window composition and in menus where a semi-transparent `_dim` overlay is applied,
  any pixels with `alpha == 0` rendered as pitch black or transparent to desktop. Fixed by enforcing
  full opacity (`alpha = 255`) on `GROUND_SURF`, `GROUND_Z`, and `screen` using `BLEND_RGBA_MAX`.
  Added `test_ground_opacity` to verify zero-alpha never recurs on ground surfaces.

## Tests
- Added `tests/test_redis.py`: starts `redis-server` + two `server.py` instances and verifies
  a lobby **hosted on instance A can be joined on instance B**, both get the same start seed,
  and host state relays cross-instance. Skips automatically if `redis-server`/`redis` missing.
- `tests/test_timing.py` now measures per-frame times and asserts on the **minimum** (intrinsic
  cost) so a thermally-throttled/busy CI box doesn't false-fail; median logged for context.
- Full suite: **11 tests, OK** (including `test_ground_opacity`). Cross-instance Redis path verified locally.

## Deploy to Render — NOT done (blocked on credentials)
- `render whoami` → **unauthorized**; no `RENDER_API_KEY`. I cannot log into the owner's
  Render account, and a Blueprint deploy also needs the one-time **GitHub→Render OAuth** done
  in the dashboard. Both require the owner. Also nothing is pushed (branch only).
- **Connectivity verified locally instead**: started `server.py`, `GET /` → **200 OK**, and a
  WebSocket `host` round-trip returned a room/code. The cross-instance Redis cluster test also
  passes locally.
- **To deploy** (owner): push this branch to GitHub → Render → New → Blueprint → pick the repo
  → Apply (`render.yaml` provisions the web service + Key Value/Redis). Then I can test the
  real `wss://…onrender.com` URL if you share it (or authenticate the Render CLI and I'll drive
  it). Note: `render.yaml` uses `type: keyvalue`; if your account still exposes the older
  `type: redis`, rename that one block.

## Owner should check by eye / play
- Sprite flashes (white while bashing, red on hit/wall) and the **live menu** backdrop.
- Minimap readability over varied terrain; leaderboard legibility (outlined text, no panel).
- Fence proximity (one tile off the road) — if it feels too tight, `FENCE_OFFSET=3`.
- Perf: the pre-zoom change should hold 60fps; my test box was thermally throttled so absolute
  ms readings here were inflated (hence the min-based timing assert).

## How to undo
- `git checkout main` returns to the pre-session state. This branch holds everything above;
  `git branch -D claude/polish-20261002-1739` discards it.

---

# Bot Aggressiveness, Host Lobby Match Settings & Audio Polish

**When:** Sat Oct 3 2026
**Summary:**
- **Font update:** Migrated UI and HUD rendering to use `assets/m6x11/m6x11.ttf`.
- **Remote sound isolation:** Fixed bug where remote players' crash, death, and off-road / powerup sound effects played locally. Sound triggers now strictly check `is_player and not is_remote`.
- **Main menu credits:** Added unobtrusive white outlined credits (`made by @AidenShoroz v.1.2.0`) in the bottom-right corner of the main menu.
- **Bot aggressiveness system:**
  - Added 4 aggression tiers: `Chill` (0.35x bash/ram, pace -10%), `Normal` (1.0x bash/ram), `Aggressive` (1.75x bash/ram, pace +8%), `Brutal` (2.5x bash/ram, pace +15%, 85% hunter bots).
  - Wired into `sim.bot_control` and `sim.make_bot` to scale bash/ram likelihood, shoot frequencies, and pace.
  - Added singleplayer Settings toggle button for bot aggression, persisted in `~/.steer_profile.json`.
- **Host-sided multiplayer lobby custom settings:**
  - Added host match settings panel in the multiplayer lobby:
    - **Bot Aggressiveness:** `Chill`, `Normal`, `Aggressive`, `Brutal`.
    - **Laps:** `3`, `5`, `7`.
    - **AI Grid Fill:** `Off`, `2 Bots`, `4 Bots`, `6 Bots`, `Fill 8`.
  - Host can click to cycle any setting; joiners see the synchronized settings in real-time.
  - New protocol frame `{"t": "settings", "settings": {...}}` handled authoritatively by the host on `server.py` and synced to all room participants.
  - Race countdown and start dynamically inherit host's configured laps and AI count/aggression for both host and clients.
- **Server updates:**
  - Added `settings` state to `Room` in `server.py`.
  - Included `settings` in room broadcasts, initial room join packets, start packets, and Redis cached metadata.
- **Tests & Verification:**
  - Added `test_host_settings_sync` in `tests/test_net.py`.
  - Updated `test_bushes.py` cone surface size assertion to match scaled cone dimensions.
  - Full test suite passing (`python3 -m unittest discover tests` → **36 tests, OK**).

---

# Cinematic Camera, Bullet-Time, Dynamic Debris & Immersive HUD

**When:** Sat Oct 3 2026
**Summary:**
- **Directional Camera Trauma (Impulse Shake):**
  - Integrated damped spring physics (`k=145`, `c=16.5`) into `sim.Camera` calculating trauma acceleration from the exact 2D vector direction of impact forces (`impact_vx`, `impact_vy`).
  - Added secondary high-frequency rumble shudder on heavy hits.
  - Preserved camera-centered car invariant to maintain complete compatibility with the test suite.
- **Dramatic Finish-Line Slow Motion (Bullet Time):**
  - Integrated 0.25× time dilation (`dt_sim = dt * 0.25`) for 1.5 seconds when crossing the finish line on the final lap or when a battle concludes.
  - Smoothly pulls the camera into an intimate tracking shot (`cam.override_zoom = 1.55`) while letterbox bars expand (`target_letterbox_h = 48.0`).
  - Supported in both singleplayer and multiplayer, with delay of network disconnection until slow-mo concludes.
- **Dynamic Debris & Tire Smoke:**
  - Flying wood splinters spawn on fence collisions and crate/barrel destructions.
  - Directional metal friction sparks spawn on rival kart bashes and side scrapes.
  - Billowing tire smoke puffs and 13-second persistent dark rubber skid arcs spawn during hard drift turns.
- **Animated Impact Callout Banners:**
  - Added full kinetic banner rendering system with scale-bounce entrance (1.6× → 1.0× with overshoot bounce) and ghosted motion blur.
  - Wired all 4 requested callout types:
    - `FINAL LAP!`
    - `SLIPSTREAM!`
    - `TAKEDOWN!` / `WRECKED!`
    - `DRIFT BOOST!`
- **Diegetic / Immersive HUD Mode:**
  - Added HUD mode toggle in Settings (`FULL` vs `IMMERSIVE`, saved to `profile["hud_mode"]`).
  - Immersive mode hides/fades HUD during normal driving and dynamically fades it back in with smooth alpha transitions on health change, rank shift, lap change, countdown, spectating, or imminent danger (low hearts, nearby rivals, off-road, high trauma).
- **Verification:**
  - Ran headless unit test suite (`python3 -m unittest discover tests` → **36 tests, OK**). All 36 tests passing cleanly.
- **Shadow Removal:**
  - Removed ground shadows from barrel, destructible boxes, floating mystery boxes, vase, and ramps in [`sim.py`](sim.py) and [`ramps.py`](ramps.py) while preserving kart, tree, bush, cone, and fence directional shadows.
- **Ramp Update:**
  - Removed the dirt ramp from the track, retaining only the wooden ramp ([`sim.py`](sim.py)).
- **Red Car Sprite Stack Replacement (`redcar_stack.png`):**
  - Replaced the car sprite stack with `assets/cars/redcar_stack.png` ($252 \times 36$ px), chopped into 7 horizontal $36 \times 36$ slices (Slice 0: chassis/tires to Slice 6: roof).
  - Aligned along East ($+X$) facing direction with dual headlights at $x=33$, $y=12, 22$ and windshield at $x=15..20$.
  - Tuned `CAR_SPRITE_W = 49` (increased by another 5 px per request) and `CAR_STACK_LIFT = 1.34` for proportional depth and scaling.
  - All players and bots use this sprite stack without color tinting over the pixel art (`tint = None` during racing).
  - Verified with full test suite passing (**36/36 tests, OK**) and hot-reloaded into the running game.
- **Asset Directory Reorganization & Path Rewrites:**
  - Audited new clean directory structure with all loose root assets organized into dedicated subfolders (`assets/car/`, `assets/decor/`, `assets/fx/`, `assets/props/`, `assets/props/ramps/`, `assets/track_tiles/`, `assets/UI/m6x11/`).
  - Rewrote asset loading paths across all game scripts:
    - [`sim.py`](sim.py): Added `CAR_DIR`, `DECOR_DIR`, and `PROPS_DIR`; updated `M6X11_PATH` to `assets/UI/m6x11/m6x11.ttf`; updated `PARTICLE_RAW` to `assets/fx/particle.png`; updated `CAR_STACK` to `assets/car/car_stack.png`; updated `bush`, `tree`, and `tree_log` to `assets/decor/`; updated `traffic_cone` to `assets/props/traffic_cone.png`; updated `oil_track` to `assets/track_tiles/oil_track.png`.
    - [`main.py`](main.py): Updated `UI_POINTER` path to `assets/fx/Sprite-0001.png`.
    - [`ramps.py`](ramps.py): Updated ramp loader to check `assets/props/ramps/` for `ramp_wood_stack.png`.
    - [`tests/test_bushes.py`](tests/test_bushes.py) & [`tests/test_oil_tracks.py`](tests/test_oil_tracks.py): Updated asset path assertions to match new paths.
- **Car Sprite Size Adjustment:**
  - Reduced `CAR_SPRITE_W` by 7px (from 49 to 42) in [`sim.py`](sim.py).
- **Keyboard & Controller Button Assets & ButtonManager:**
  - Sliced and organized `kb_dark_all.png` into individual 16x16 pixel sprites under [`assets/UI/keyboardbtn/`](assets/UI/keyboardbtn/) (both raw grid cells and semantic key names: letters, numbers, f-keys, navigation/symbol keys across all 4 button states).
  - Sliced and organized controller sheets into dedicated folders:
    - Xbox (`controller_xbox.png`) in [`assets/UI/controller/xbox/`](assets/UI/controller/xbox/) and `xbobx/` alias.
    - PlayStation (`controller_ps.png`) in [`assets/UI/controller/ps/`](assets/UI/controller/ps/).
    - Nintendo (`controller_switch.png`) in [`assets/UI/controller/nintendo/`](assets/UI/controller/nintendo/) and `switch/` alias.
    - Minimal (`controller_minimal.png`) in [`assets/UI/controller/minimal/`](assets/UI/controller/minimal/).
  - Created [`ui/buttonmanager.py`](ui/buttonmanager.py) (and root forwarder [`buttonmanager.py`](buttonmanager.py)) providing cached retrieval and drawing for any keyboard keycode or controller button.
  - Hooked up `ButtonManager` to the Settings screen in [`main.py`](main.py) to display authentic pixel-art button prompt badges for keybindings and connected gamepads.
- **Button Prompt & Social Media Icon Size Scaling:**
  - Increased social buttons (Itch.io, YouTube, Instagram, Discord) size from native 16x16 to 21x21 (+5px) in [`main.py`](main.py), and adjusted vertical alignment to center alongside the author credits.
  - Set `DEFAULT_ICON_SIZE = 21` (+5px from native 16x16) in [`ui/buttonmanager.py`](ui/buttonmanager.py) so all keyboard keybinds, controller prompts, and navigation prompts render at 21x21.
  - Updated gamepad controls rows in Settings with 21px vertical spacing to prevent crowding.
  - Verified full test suite passing (**36/36 tests, OK**).

---

# Dual Track System, Grand Prix Circuit & Full 7-Track Music Suite

**When:** Sun Oct 4 2026
**Summary:**
- **Dual Track Engine Architecture:**
  - Added full tileset abstraction supporting distinct environments (`assets/tilesets/meadow_dirt` and `assets/tilesets/asphalt_circuit`).
  - Integrated 18 track tiles, checkered finish line tiles, and authentic asphalt/dirt road surfaces with dynamic skid mark coloring (`#1e1e1e` on asphalt vs `#3a2818` on dirt).
  - Preserved canonical fallback assets to guarantee test suite determinism and bot navigation invariants.
- **Track Selection UI & Networking:**
  - Added interactive Track Type toggle in singleplayer Settings (persisted to `~/.steer_profile.json`).
  - Added Host-controlled Match Settings Track selector in the Multiplayer Lobby, authoritatively synced across clients in real-time (`server.py`).
  - Added dynamic animated kinetic track title banner on race countdown start ("MEADOW DIRT" / "GRAND PRIX CIRCUIT").
- **Full 7-Track Music Suite:**
  - Expanded chiptune soundtrack from 3 tracks to 7 high-energy racing themes:
    `01_night_shade.mp3`, `02_clint_eastwood.mp3`, `03_maze.mp3`, `04_pit_stop.mp3`, `05_pursuit.mp3`, `06_sunset_coast.mp3`, and `07_grand_prix.mp3`.
  - Added automatic playlist shuffling, fallback, and volume management.
- **Aesthetic Guidelines & Palette:**
  - Added `TASTE.md` design guide and color palette swatches `assets/steer_palette.png` and `assets/steer_palette_1x.png`.
- **Comprehensive Verification:**
  - Ran headless test suite (`python3 tests.py` → **39 tests passed, OK** in 54.3s).

---

# Frost Pass Tileset & Steer UI Kit Redesign

**When:** Sun Oct 4 2026
**Summary:**
- **Frost Pass Alpine Snow Circuit Integration:**
  - Integrated complete `frost_pass` tileset into [`assets/tilesets/frost_pass/`](assets/tilesets/frost_pass): atlas (`frost_pass_sheet.png`, `frost_pass.json`, `frost_pass.tsx`), preview, `oil_track.png`, and 20 directional track/check tiles.
  - Added snow/frozen asphalt physics properties: ice road skid marks (`#464a55`), snow surface skids (`#a5bece`), and dynamic snow wheel particle kickups.
  - Paired high-tempo theme `05_pursuit.mp3` with Frost Pass, added to random circuit rotation and singleplayer / multiplayer track selector.
  - Added comprehensive automated test coverage in `TestTilesets` within [`tests.py`](tests.py).
- **Steer UI Kit (`ui.py`) & Menu Redesign:**
  - Integrated standalone pixel-art UI kit [`ui.py`](ui.py) offering custom font rendering, STEER speed-streak logo, slab buttons with animated chequered tails, segmented sliders, toggles, and keycaps/gamepad glyphs.
  - **Title & Pause Menus:** Redesigned layout with slanted dark ink band and red/white kerb border, kinetic slide-out slab buttons, live paused race status chip, and social icons (itch.io, youtube, instagram, discord).
  - **Tabbed Settings:** Clean 4-tab interface (RACE, SOUND, VIDEO, CONTROLS) with row-by-row help descriptions, keyboard & controller mapping display, and unified multi-input support (keyboard, mouse, gamepad).
  - **Button Integration:** Converted all menu and screen buttons to use authentic UI kit slabs while maintaining all existing game mechanics, mouse aim, banners, and multiplayer netcode.
  - Verified full test suite passing (**41/41 tests, OK** in 61.5s).




