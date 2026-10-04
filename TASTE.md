# Steer: taste

This is how Steer looks and sounds, written down from what's already in the game: your track
tiles, the fences, trees, bushes and breakables, the 2.5D props, ramps and karts, the mystery
box, the 62 sound effects and the 7 music tracks. Use it to check new work against. When
something new disagrees with this file, either the new thing is wrong or this file needs a line.

The palette is in `palette/` (`steer_palette.png`, `.gpl` for Aseprite/GIMP, `.hex` for Lospec,
`.json` with notes on where each colour is used).

---

## 1. The one-line version

**Chunky, flat-coloured pixel art seen from above with a little tilt, lit from the upper left,
with cool, hue-shifted shadows; calm ground, louder props, loudest karts. It sounds like an NES
with a 16-bit soundcard: square-wave hooks, crunchy hits, nothing smooth or orchestral.**

---

## 2. Scale and grid

| Thing | Size | Notes |
|---|---|---|
| Track tile | 16 x 16 px | 1 art px = 1 world px. The whole map is a 16 px grid. |
| Oil slick sheet | 48 x 48 px | a 3x3 of 16 px slices (top, left, center, right, bottom) |
| Props (tyres, crates, barrels, vases, cones, ramps, mystery box) | 12-24 px footprint | drawn at **2x** (1 art px = 2 world px) |
| Trees | 48 px footprint | drawn at **1x**, so their leaves are finer than the props |
| Karts | 20-56 px slice canvas, 6-8 slices | sprite stacks, nose pointing +x; the low-detail F1 is 20 x 13 from above |
| Camera | ZOOM 1.68 | the world is always scaled by nearest neighbour, never smoothed |

- Every pixel is either fully opaque or fully clear (alpha 0 or 255). The only exceptions are
  shadows, which the game draws semi-transparent at run time.
- No anti-aliasing, no sub-pixel lines, no blur. Scale only by whole numbers, nearest neighbour.

## 3. Light

- **One sun, from the upper left.** Light travels toward 55° (down and to the right on screen),
  so every shadow falls to the **lower right**.
- On tiles, that's the `road_shadow` row: it sits on the road just below a top lip and just to
  the right of a left lip, and never on the bottom or right edges.
- 2.5D props and karts have the light baked into each slice: faces turned toward the upper left
  are lit, faces turned away are shaded. That's why trees and breakables must be drawn at angle 0.
- Cast shadows are a flat dark navy (`(10, 12, 22)` at alpha 110-175), never black, never
  blurred.

## 4. Colour

### Ramps, not loose colours
Colours come in ramps from dark to light (meadow, earth, timber, sand, steel, racing red, fire,
sky, night). A sprite uses 2-3 ramps and only steps one or two places along each ramp between
neighbouring pixels.

### Shadows shift hue; highlights shift warm
- Grass shades go **teal** (`#3e9b48` → `#265c42` → `#193c3e`), not darker green.
- Dirt shadow goes **red-purple** (`#b86f50` → `#733e39`).
- Metal and asphalt shadows go **blue** (`#464a55` → `#292e3a` → `#10121c`).
- Oil is **navy-violet** (`#171524`, `#222034`), not grey.
- Highlights lean **yellow** (foliage `#8ae741`, gold `#f6cd48`, pale `#f7f3b7`).
- Pure black `#000000` is only for the finish-line checker and the flat trees' outline.
  Everything else bottoms out at `#10121c` or a ramp's own darkest tone.

### Loudness hierarchy (what pops)
1. **Karts**: the most saturated colours (racing red, crimson, gold).
2. **Pickups**: the mystery box is the brightest blue in the game, with a white outline.
3. **Hazards**: cone orange and oil dark. They must read against every road colour.
4. **Props**: wood, steel and khaki, mid saturation.
5. **Road**: one flat calm colour.
6. **Off-road**: the calmest big area. The game fills everything past the tiles with it.

If a new prop is louder than a kart, or a road is louder than a pickup, it's wrong.

### Budgets
- Terrain tile: **5 colours** (ground, ground shade, lip outline, road, road shadow), plus at
  most 4 for an edge detail (kerb stripes, glow, debris).
- Prop: 8-12 colours. Kart: up to about 30 for a hero car (the F1 used 29), 10-15 for a simple one.
- New colours go into a ramp in the palette first, then into art.

## 5. Track tiles: the anatomy

Every terrain tile is built from 7 roles. The 5 new tilesets are your tiles with these roles
recoloured, so the shapes always match:

| Role | Original | What it is |
|---|---|---|
| `ground` | `#3e9b48` | off-road fill. The game reads it from `dirt_corner_tl` at (0,0) as `GRASS_COLOR`. |
| `ground_shade` | `#265c42` | the 1-2 px darker band along the lip |
| `lip_outline` | `#193c3e` | the 1 px line where off-road meets road |
| `road` | `#b86f50` | road fill. The game reads it from `dirt_center` at (8,8) as `DIRT_COLOR`. |
| `road_shadow` | `#733e39` | the lip's shadow on the road (top and left lips only) |
| `check_dark` / `check_light` | `#000000` / `#ffffff` | the finish line, 4 px squares |

Rules that keep the set seamless:
- **The road is flat.** No texture in `dirt_center`. Repeated texture becomes a visible 16 px
  grid. Detail lives at the edges (kerbs, glow, pebbles), 0-4 px from the lip.
- **The lip is organic**: a 1-3 px lumpy edge, never a straight line. Lumps line up across tile
  borders, so change a lip only together with the tile it meets.
- **The off-road is flat** past the lip, because the game draws plain `GRASS_COLOR` beyond the tiles.
- `oil_track.png` must keep `#b86f50` (184, 111, 80) as its background. The game keys out that
  exact colour, so it's never drawn, whatever the road colour.
- Names: `<surface>_<part>_<corner/side>`: `dirt_corner_tl`, `dirt_edge_top`, `dirt_inner_br`,
  `checktile` (+ `1`-`4` = left, right, top, bottom). Variants keep the `dirt_` names so they
  drop in, and their folder name says what they are.

### The tilesets

| id | Title | Ground / road | Edge detail | Pairs with |
|---|---|---|---|---|
| `meadow_dirt` | Meadow Dirt (your original) | grass / red dirt | none | Full Throttle, Pit Stop |
| `asphalt_circuit` | Grand Prix Circuit | grass / asphalt `#464a55` | red + white kerbs, 4 px stripes | Grand Prix, Final Lap |
| `canyon_sand` | Red Canyon | red rock `#94493a` / sand `#dab163` | pebbles | Final Lap, Sunset Coast |
| `frost_pass` | Frost Pass | snow `#f0f8ff` / packed snow `#7e8f9a` | blown snow | Pursuit, Neon Night |
| `harvest_mud` | Harvest Mud | gold field `#ce9248` / mud `#6e4c30` | clods and straw | Pit Stop, Full Throttle |
| `neon_night` | Neon Night | night `#171524` / slate `#3e3b65` | cyan neon lip `#36c5f4` + glow `#3388de` | Neon Night, Pursuit |

Each tileset's JSON also has grip and skid-mark colour hints and a fence suggestion. The game
doesn't read these yet; they're notes for when per-tileset physics gets wired up.

## 6. Outlines and edges

- **Props** (trees, crates, barrels, vases, cones) get a 1 px dark outline, `(20, 22, 26)` in
  game and `#2f2f2e` baked into some stacks. They're objects you can hit, so they get a hard edge.
- **Pickups** get a **white** outline (the mystery box). White means "drive into me".
- **Flat trees** get a white stroke as well, so the old sprites read on any ground.
- **Karts** don't get the prop outline. Their saturated colours and cast shadow separate them.
- **Tiles** have no outline round the tile itself, only the lip outline between surfaces.

## 7. Shapes

- Nature is **lumpy and rounded**: blobby canopies, uneven grass lips, irregular oil.
- Man-made things are **crisp and boxy**: crates, ramps, kerbs, the checker, fences.
- 2.5D stacks: square slices in a horizontal strip, bottom slice first, nose toward +x. The
  game lifts each slice 1.15 x ZOOM px. Keep them chunky: karts 6-8 slices, props 7-21, trees
  36-48 (trees are drawn at 1x, so their slices are thinner). They should read as toys, not towers.
- Glyphs and logos are **original**. No real brands (the F1's sponsor logos were replaced with
  made-up decals); a "?" or a number is fine.

## 8. Things that don't belong

Gradients and dithering on terrain; textured road fills; more than one light direction; pure
black shadows; pillow shading (lighting from the middle outward); soft or blurred edges;
semi-transparent pixels in sprites; photo textures; real brand logos; text baked into sprites
(the game draws text itself); prop colours brighter than the karts.

---

## 9. Sound effects

Made by `tools/make_sfx.py`. Everything is synthesized, with no samples.

- **Format**: 44.1 kHz, mono, 16-bit WAV, peaks at -1 dBFS (0.89), 6 ms fade-out.
- **Character**: punchy arcade. Hits are filtered noise, a low pitch-dropping thump and a
  material resonance (wood, metal or plastic). Chip-style tones are **bit-crushed** (7-8 bits,
  sample hold 2) and then **low-passed at 6.5 kHz**, so they crunch without fizzing.
- **Short**: most effects last under 0.6 s. Loops (engine x4, skid, gravel, boost) are 1.0 s and
  seamless.
- **Variety**: anything that repeats has 2-3 versions picked at random (bump1-3, bash_hit1-3,
  crash1-2...), plus per-event cooldowns so scraping a wall doesn't machine-gun.
- **Space**: sounds out on the track fade to nothing at 650 world px and pan by screen position.
  Your own kart's sounds are centred.
- **Meaning in pitch**: good things **rise**, in major arpeggios (pickups, lap, finish, position
  up). Bad things **fall**, in minor or diminished shapes (heart lost, death, position down,
  eliminated). UI sounds are soft, short square blips.

## 10. Music

Made by `tools/make_music.py`: 7 tracks, each about 3:00, all from scratch.

- **Voices**: NES pulse leads (12.5 / 25 / 50% duty) with **delayed vibrato**, a 4-bit stepped
  triangle bass with a sine under it, and noise drums. On top of that, 16-bit polish: FM
  electric piano, brassy saw lead, a soft pad, a 3/16 **ping-pong echo** on the lead, and a
  stereo mix.
- **Tempo**: 112 (menu) to 176 (final lap). Racing tracks are 144-176.
- **Form**: intro, verse, build (with a snare roll), chorus, breakdown, second verse, chorus,
  solo or bridge, final chorus (usually **up a step**), then an ending that resolves. No fade-outs.
- **Melody**: hooks built on rhythm (the 3-3-2 "tresillo", stutters, syncopation), mostly 8th
  notes, chord tones on strong beats, passing notes on weak ones.
- **Level**: -11 to -12 LUFS integrated, peaks at -1 dBFS, so the shuffled playlist never jumps
  in volume.

| # | Track | Feel |
|---|---|---|
| 1 | Full Throttle | main theme, minor verse into a major chorus |
| 2 | Neon Night | synthwave, rolling bass, gated snare |
| 3 | Final Lap | fastest, gallop bass, brassy chorus |
| 4 | Pit Stop | swung, jazzy 7th chords, FM keys (menus) |
| 5 | Pursuit | spy-style chromatic chase riff |
| 6 | Sunset Coast | breezy, offbeat skank, FM build-ups |
| 7 | Grand Prix | fanfare, "royal road" chorus (podium / credits) |
