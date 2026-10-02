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
