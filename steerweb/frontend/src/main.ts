// v1 milestone: single car, procedurally generated track, full tyre-physics driving feel,
// hearts/off-road, wrong-way correction, camera follow, HUD. Next milestones (not yet ported):
// bots + car-car/wall collisions + bashing payoff, game modes, menus/settings, multiplayer.
import { W, H, TOTAL_LAPS } from "./constants";
import { Track } from "./track";
import { Car } from "./car";
import { Camera } from "./camera";
import { Keyboard } from "./input";
import { drawWorld, drawHud } from "./render";

const canvas = document.getElementById("game") as HTMLCanvasElement;
const ctx = canvas.getContext("2d")!;

const PHYS_SUBSTEPS = 4;

function fitCanvas() {
  const scale = Math.min(window.innerWidth / W, window.innerHeight / H);
  canvas.style.width = `${W * scale}px`;
  canvas.style.height = `${H * scale}px`;
}
window.addEventListener("resize", fitCanvas);
fitCanvas();

const seed = Math.floor(Math.random() * 1_000_000);
const track = new Track(seed);

const [sx, sy, sAngle] = track.roadPose(0, 0);
const player = new Car(sx, sy, sAngle, "#e64646");
player.isPlayer = true;
player.trackS = 0;
const [, , startIdx] = track.trackCoords(player.x, player.y, null);
player.trackIdx = startIdx;

const camera = new Camera(player);
const keyboard = new Keyboard();

function lapOf(car: Car): number {
  if (track.roadLen <= 1) return 0;
  return Math.max(0, Math.floor(car.progress / track.roadLen));
}

let last = performance.now();
function frame(now: number) {
  const dt = Math.min((now - last) / 1000, 1 / 30);
  last = now;

  if (!player.dead) {
    const steer = keyboard.steer();
    player.drift = keyboard.drift();
    const braking = keyboard.brake();
    if (keyboard.bashLeftEdge()) player.startBash("left");
    if (keyboard.bashRightEdge()) player.startBash("right");

    player.prepare(track);
    const h = dt / PHYS_SUBSTEPS;
    for (let i = 0; i < PHYS_SUBSTEPS; i++) {
      player.integrate(h, steer, braking);
    }
    player.postFrame(dt, track);

    const [s, , idx] = track.trackCoords(player.x, player.y, player.trackIdx);
    player.trackIdx = idx;
    if (player.trackS !== null) {
      const delta = (((s - player.trackS + track.roadLen / 2) % track.roadLen) + track.roadLen) % track.roadLen - track.roadLen / 2;
      player.progress += delta;
    }
    player.trackS = s;
  } else {
    player.postFrame(dt, track);
  }

  camera.update(dt, player);

  ctx.clearRect(0, 0, W, H);
  drawWorld(ctx, camera, track, [player]);
  drawHud(ctx, player, lapOf(player), TOTAL_LAPS);

  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
