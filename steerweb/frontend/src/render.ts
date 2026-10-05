// v1 renderer: flat-shaded canvas 2D draw of the road + cars + skid trail + HUD. Not yet ported:
// sprite-stacked pseudo-3D cars, tile-based ground art, particles/fx, shaders, minimap.
import { W, H, ROAD_WIDTH, HEART_COUNT } from "./constants";
import type { Track } from "./track";
import type { Car } from "./car";
import type { Camera } from "./camera";

const GRASS = "#2b4a2b";
const ROAD = "#8a6f4a";
const ROAD_EDGE = "#6e5638";

export function drawWorld(ctx: CanvasRenderingContext2D, cam: Camera, track: Track, cars: Car[]) {
  ctx.fillStyle = GRASS;
  ctx.fillRect(0, 0, W, H);

  // road: stroke the centreline polyline with a wide line (round joins approximate the tile loop)
  ctx.save();
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.strokeStyle = ROAD_EDGE;
  ctx.lineWidth = (ROAD_WIDTH + 10) * cam.zoom;
  strokeRoadPath(ctx, cam, track);
  ctx.strokeStyle = ROAD;
  ctx.lineWidth = ROAD_WIDTH * cam.zoom;
  strokeRoadPath(ctx, cam, track);
  ctx.restore();

  // skid trails
  for (const car of cars) {
    for (const [x0, y0, x1, y1, life, w] of car.trail) {
      const [sx0, sy0] = cam.toScreen(x0, y0);
      const [sx1, sy1] = cam.toScreen(x1, y1);
      ctx.strokeStyle = `rgba(30,24,20,${Math.min(0.55, life / 13)})`;
      ctx.lineWidth = Math.max(1, w * cam.zoom * 0.5);
      ctx.beginPath();
      ctx.moveTo(sx0, sy0);
      ctx.lineTo(sx1, sy1);
      ctx.stroke();
    }
  }

  for (const car of cars) drawCar(ctx, cam, car);
}

function strokeRoadPath(ctx: CanvasRenderingContext2D, cam: Camera, track: Track) {
  ctx.beginPath();
  const n = track.road.length;
  for (let i = 0; i <= n; i++) {
    const [wx, wy] = track.road[i % n];
    const [sx, sy] = cam.toScreen(wx, wy);
    if (i === 0) ctx.moveTo(sx, sy);
    else ctx.lineTo(sx, sy);
  }
  ctx.closePath();
  ctx.stroke();
}

function drawCar(ctx: CanvasRenderingContext2D, cam: Camera, car: Car) {
  const corners = car.corners().map(([x, y]) => cam.toScreen(x, y));
  ctx.save();
  ctx.fillStyle = car.dead ? "#555555" : car.hitFlash > 0 ? "#ff4040" : car.flash > 0 ? "#ffffff" : car.color;
  ctx.beginPath();
  corners.forEach(([sx, sy], i) => (i === 0 ? ctx.moveTo(sx, sy) : ctx.lineTo(sx, sy)));
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = "rgba(0,0,0,0.5)";
  ctx.lineWidth = 1;
  ctx.stroke();

  // nose marker so heading reads clearly
  const rad = (car.angle * Math.PI) / 180;
  const [nx, ny] = cam.toScreen(car.x + Math.cos(rad) * 16, car.y + Math.sin(rad) * 16);
  const [cx, cy] = cam.toScreen(car.x, car.y);
  ctx.strokeStyle = "rgba(255,255,255,0.8)";
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(nx, ny);
  ctx.stroke();
  ctx.restore();
}

export function drawHud(ctx: CanvasRenderingContext2D, car: Car, lap: number, totalLaps: number) {
  ctx.save();
  ctx.font = "bold 16px monospace";
  ctx.fillStyle = "#ffffff";
  ctx.strokeStyle = "rgba(0,0,0,0.6)";
  ctx.lineWidth = 3;
  const heartsStr = "♥".repeat(Math.ceil(car.hearts)) + "♡".repeat(HEART_COUNT - Math.ceil(car.hearts));
  ctx.strokeText(heartsStr, 10, 24);
  ctx.fillText(heartsStr, 10, 24);
  const lapStr = `LAP ${Math.min(lap + 1, totalLaps)}/${totalLaps}`;
  const w = ctx.measureText(lapStr).width;
  ctx.strokeText(lapStr, W - w - 10, 24);
  ctx.fillText(lapStr, W - w - 10, 24);
  if (car.wrongWay) {
    ctx.fillStyle = "#ff5050";
    const msg = "WRONG WAY";
    const mw = ctx.measureText(msg).width;
    ctx.strokeText(msg, W / 2 - mw / 2, 50);
    ctx.fillText(msg, W / 2 - mw / 2, 50);
  }
  if (car.dead) {
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 28px monospace";
    const msg = "GAME OVER";
    const mw = ctx.measureText(msg).width;
    ctx.strokeText(msg, W / 2 - mw / 2, H / 2);
    ctx.fillText(msg, W / 2 - mw / 2, H / 2);
  }
  ctx.restore();
}
