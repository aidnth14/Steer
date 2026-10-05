// Ported from steer/sim.py's Camera class. v1 keeps position/rotation follow and zoom but skips
// the cinematic extras (impact trauma shake, boost/drift zoom dilation, handheld sway).
import { W, H, ZOOM } from "./constants";
import { wrapDelta } from "./track";
import type { Car } from "./car";

const CAM_ROT_SMOOTH = 4.0;
const CAM_VEL_FOLLOW = 0.7;

function lerpAngle(a: number, b: number, t: number): number {
  let diff = ((b - a + 180) % 360) - 180;
  if (diff < -180) diff += 360;
  return a + diff * t;
}

export class Camera {
  x: number;
  y: number;
  angle: number;
  zoom = ZOOM;
  cosC: number;
  sinC: number;

  constructor(car: Car) {
    this.x = car.x;
    this.y = car.y;
    this.angle = car.angle;
    const rad = (-(this.angle + 90) * Math.PI) / 180;
    this.cosC = Math.cos(rad);
    this.sinC = Math.sin(rad);
  }

  update(dt: number, car: Car) {
    this.x = car.x;
    this.y = car.y;
    const speed = Math.hypot(car.vx, car.vy);
    const tRot = Math.min(CAM_ROT_SMOOTH * dt, 1);
    let target = car.angle;
    if (speed > 60) {
      const w = Math.min(1, (speed - 60) / 120) * CAM_VEL_FOLLOW;
      target = lerpAngle(car.angle, (Math.atan2(car.vy, car.vx) * 180) / Math.PI, w);
    }
    this.angle = lerpAngle(this.angle, target, tRot);
    const rad = (-(this.angle + 90) * Math.PI) / 180;
    this.cosC = Math.cos(rad);
    this.sinC = Math.sin(rad);
  }

  toScreen(wx: number, wy: number): [number, number] {
    const dx = wrapDelta(this.x, wx);
    const dy = wrapDelta(this.y, wy);
    return [W / 2 + (dx * this.cosC - dy * this.sinC) * this.zoom, H / 2 + (dx * this.sinC + dy * this.cosC) * this.zoom];
  }
}
