// Ported from steer/sim.py's Car class. v1 scope: driving physics, grass/off-road, hearts,
// stuck/rescue, drift, side-bash/ram impulses, skid trail. Not yet ported: projectiles, cone/oil
// sabotage items, mystery-box pickups, camera-shake impact vectors, slipstream draft tracking.
import {
  AXLE_FRONT,
  AXLE_REAR,
  WHEELBASE,
  CAR_MASS,
  CAR_INERTIA,
  MAX_SPEED,
  ENGINE_ACCEL,
  ENGINE_FALLOFF,
  ROLL_RESIST,
  AIR_DRAG,
  GRIP,
  TIRE_SHAPE,
  TIRE_B,
  DRIVE_GRIP_USE,
  STEER_MAX,
  STEER_GRIP_RATIO,
  STEER_RATE,
  V_FLOOR,
  YAW_DAMP,
  STABILITY,
  DRIFT_GRIP,
  GRASS_GRIP,
  GRASS_ENGINE_LOSS,
  GRASS_RESIST,
  MAX_SPIN,
  BASH_COOLDOWN,
  BASH_TIME,
  BASH_SIDE_SPEED,
  BASH_TIRE,
  RAM_TIME,
  RAM_SPEED,
  HEART_COUNT,
  HEART_PENALTY,
  HEART_COOLDOWN,
  BOOST_PACE,
  DRAFT_PACE,
  SLIPSTREAM_ASSIST,
  STUCK_SPEED,
  STUCK_TIME,
  REVERSE_TIME,
  REVERSE_ACCEL,
  REVERSE_SPEED,
  RESCUE_TIME,
  BRAKE_ACCEL,
  SKID_SLIP,
  TRAIL_LIFE,
  TRAIL_MAX_POINTS,
  WORLD,
  WHEEL_Y,
  ROAD_WIDTH,
  CAR_HW,
} from "./constants";
import type { Track } from "./track";

function tireCurve(alpha: number): number {
  return Math.sin(TIRE_SHAPE * Math.atan(TIRE_B * alpha));
}

function steerLimit(v: number): number {
  v = Math.max(v, 1.0);
  return Math.min(STEER_MAX, Math.atan((STEER_GRIP_RATIO * GRIP * WHEELBASE) / (v * v)));
}

export interface Controls {
  steer: number; // -1..1
  drift: boolean;
  brake: boolean;
  ram: boolean;
  bashLeft: boolean;
  bashRight: boolean;
}

export type TrailSeg = [number, number, number, number, number, number]; // x0,y0,x1,y1,life,width

let nextUid = 1;

export class Car {
  x: number;
  y: number;
  angle: number; // degrees, 0 = facing +x, + = clockwise
  vx = 0;
  vy = 0;
  omega = 0;
  steerAngle = 0;
  color: string;
  mass = CAR_MASS;
  pace = 1.0;
  uid = nextUid++;
  progress = 0;
  trackS: number | null = null;
  trackIdx: number | null = null;
  trail: TrailSeg[] = [];
  lastWheelPos: Record<string, [number, number] | null> = {};
  hearts = HEART_COUNT;
  dead = false;
  wasOnRoad = true;
  heartCooldown = 0;
  raceT = 0;
  curLap = 0;
  lastLapT = 0;
  lastLap = 0;
  bestLap = 0;
  offF = 0;
  offR = 0;
  slipF = 0;
  slipR = 0;
  boostTime = 0;
  drift = false;
  driftCharge = 0;
  team = -1;
  bashCd = 0;
  bashTime = 0;
  bashKind: "left" | "right" | "ram" | null = null;
  stagger = 0;
  flash = 0;
  hitFlash = 0;
  draft = 0;
  wrongWay = false;
  wrongWayTime = 0;
  slowTime = 0;
  reverseTime = 0;
  wedged = 0;
  rescues = 0;
  isBot = false;
  isRemote = false;
  isPlayer = true;
  name = "You";
  flag: string | null = null;

  constructor(x: number, y: number, angle: number, color: string) {
    this.x = x;
    this.y = y;
    this.angle = angle;
    this.color = color;
  }

  prepare(track: Track) {
    const rad = (this.angle * Math.PI) / 180;
    const c = Math.cos(rad);
    const s = Math.sin(rad);
    this.offF = track.offroadFactor(this.x + c * AXLE_FRONT, this.y + s * AXLE_FRONT, this.trackIdx);
    this.offR = track.offroadFactor(this.x - c * AXLE_REAR, this.y - s * AXLE_REAR, this.trackIdx);
  }

  startBash(kind: "left" | "right" | "ram"): boolean {
    if (this.bashCd > 0 || this.reverseTime > 0) return false;
    const rad = (this.angle * Math.PI) / 180;
    const c = Math.cos(rad);
    const s = Math.sin(rad);
    if (kind === "ram") {
      this.vx += c * RAM_SPEED;
      this.vy += s * RAM_SPEED;
      this.bashTime = RAM_TIME;
    } else {
      const side = kind === "right" ? 1 : -1;
      this.vx += -s * side * BASH_SIDE_SPEED;
      this.vy += c * side * BASH_SIDE_SPEED;
      this.bashTime = BASH_TIME;
    }
    this.bashKind = kind;
    this.bashCd = BASH_COOLDOWN;
    return true;
  }

  integrate(h: number, steerIn: number, braking: boolean) {
    const rad = (this.angle * Math.PI) / 180;
    const c = Math.cos(rad);
    const s = Math.sin(rad);
    const vx = this.vx;
    const vy = this.vy;
    const vLong = vx * c + vy * s;
    const vLat = -vx * s + vy * c;

    const target = Math.max(-1, Math.min(1, steerIn)) * steerLimit(Math.abs(vLong));
    const step = STEER_RATE * h;
    this.steerAngle += Math.max(-step, Math.min(step, target - this.steerAngle));
    const cd = Math.cos(this.steerAngle);
    const sd = Math.sin(this.steerAngle);

    const m = this.mass;
    let loose = this.stagger > 0 ? 0.55 : 1.0; // STAGGER_GRIP
    if (this.bashTime > 0) loose *= BASH_TIRE;
    const rearGripMult = this.drift ? DRIFT_GRIP : 1.0;
    const rear = loose * rearGripMult;
    const capF = GRIP * (1 - this.offF * (1 - GRASS_GRIP)) * loose * m * (AXLE_REAR / WHEELBASE);
    const capR = GRIP * (1 - this.offR * (1 - GRASS_GRIP)) * rear * m * (AXLE_FRONT / WHEELBASE);

    let drive: number;
    if (this.reverseTime > 0) {
      drive = vLong > -REVERSE_SPEED ? -REVERSE_ACCEL * m : 0;
    } else if (braking) {
      drive = vLong > 15 ? -BRAKE_ACCEL * m : vLong > -REVERSE_SPEED ? -REVERSE_ACCEL * m : 0;
    } else {
      const frac = Math.min(Math.max(vLong, 0) / MAX_SPEED, 1);
      const boost =
        this.boostTime > 0 ? 1 + BOOST_PACE : 1 + (SLIPSTREAM_ASSIST ? DRAFT_PACE : 0) * this.draft;
      drive = ENGINE_ACCEL * m * this.pace * boost * (1 - frac * ENGINE_FALLOFF) * (1 - this.offR * GRASS_ENGINE_LOSS);
    }
    if (this.dead) drive = 0;

    const latF = vLat + this.omega * AXLE_FRONT;
    const uF = -vLong * sd + latF * cd;
    const wF = vLong * cd + latF * sd;
    let fF = -tireCurve(Math.atan2(uF, Math.max(Math.abs(wF), V_FLOOR))) * capF;

    const uR = vLat - this.omega * AXLE_REAR;
    let use = capR > 0 ? Math.min((Math.abs(drive) * DRIVE_GRIP_USE) / capR, 0.95) : 0.95;
    if (this.bashTime > 0) use = 0;
    let fR = -tireCurve(Math.atan2(uR, Math.max(Math.abs(vLong), V_FLOOR))) * capR * Math.sqrt(1 - use * use);

    const lim = (0.5 * m) / h;
    fF = Math.max(-lim * Math.abs(uF), Math.min(lim * Math.abs(uF), fF));
    fR = Math.max(-lim * Math.abs(uR), Math.min(lim * Math.abs(uR), fR));

    const fx = drive - fF * sd;
    const fy = fF * cd + fR;
    let torque = AXLE_FRONT * fF * cd - AXLE_REAR * fR;
    if (this.stagger <= 0) {
      const omegaKin = (vLong * Math.tan(this.steerAngle)) / WHEELBASE;
      torque -= STABILITY * (this.omega - omegaKin) * CAR_INERTIA * m;
    }

    let wx = fx * c - fy * s;
    let wy = fx * s + fy * c;
    const speed = Math.hypot(vx, vy);
    if (speed > 1e-6) {
      const off = 0.5 * (this.offF + this.offR);
      let res = (ROLL_RESIST + AIR_DRAG * speed * speed) * (1 + off * GRASS_RESIST) * m;
      res = Math.min(res, (speed * m) / h);
      wx -= (vx / speed) * res;
      wy -= (vy / speed) * res;
    }

    this.vx += (wx / m) * h;
    this.vy += (wy / m) * h;
    this.omega += (torque / (CAR_INERTIA * m)) * h;
    this.omega *= Math.max(0, 1 - YAW_DAMP * h);
    this.omega = Math.max(-MAX_SPIN, Math.min(MAX_SPIN, this.omega));
    this.x = (((this.x + this.vx * h) % WORLD) + WORLD) % WORLD;
    this.y = (((this.y + this.vy * h) % WORLD) + WORLD) % WORLD;
    this.angle += (this.omega * h * 180) / Math.PI;
    this.slipF = Math.abs(uF);
    this.slipR = Math.abs(uR);
  }

  postFrame(dt: number, track: Track) {
    this.raceT += dt;
    this.bashCd = Math.max(0, this.bashCd - dt);
    this.bashTime = Math.max(0, this.bashTime - dt);
    this.boostTime = Math.max(0, this.boostTime - dt);
    this.stagger = Math.max(0, this.stagger - dt);
    this.flash = Math.max(0, this.flash - dt);
    this.hitFlash = Math.max(0, this.hitFlash - dt);

    const onRoad = track.offroadFactor(this.x, this.y, this.trackIdx) <= 0;
    this.heartCooldown = Math.max(0, this.heartCooldown - dt);
    if (this.wasOnRoad && !onRoad && this.heartCooldown <= 0) {
      this.hearts = Math.max(0, this.hearts - HEART_PENALTY);
      this.heartCooldown = HEART_COOLDOWN;
    }
    if (this.hearts <= 0 && !this.dead) {
      this.dead = true;
    }
    this.wasOnRoad = onRoad;

    // wrong-way: heading > 100deg off track direction while actually moving backward along it
    if (!this.dead && !this.isBot) {
      const [, , tidx] = track.trackCoords(this.x, this.y, this.trackIdx);
      const [tx, ty] = track.roadT[tidx];
      const trackDeg = (Math.atan2(ty, tx) * 180) / Math.PI;
      let angDiff = ((this.angle - trackDeg + 180) % 360) - 180;
      if (angDiff < -180) angDiff += 360;
      const vForward = this.vx * tx + this.vy * ty;
      const isWrong = Math.abs(angDiff) > 100 && vForward < -30;
      if (isWrong) {
        this.wrongWay = true;
        this.wrongWayTime += dt;
        const brakeFactor = Math.max(0.15, 1 - 5 * dt);
        this.vx *= brakeFactor;
        this.vy *= brakeFactor;
      } else {
        this.wrongWay = false;
        this.wrongWayTime = Math.max(0, this.wrongWayTime - dt * 2);
      }
    }

    // stuck / rescue
    const speed = Math.hypot(this.vx, this.vy);
    if (this.dead) {
      this.wedged = this.slowTime = this.reverseTime = 0;
    } else if (speed < STUCK_SPEED) {
      this.wedged += dt;
    } else if (speed > 2 * STUCK_SPEED) {
      this.wedged = 0;
    }
    if (this.dead) {
      // coast
    } else if (this.wedged > RESCUE_TIME) {
      this.rescue(track);
    } else if (this.reverseTime > 0) {
      this.reverseTime = Math.max(0, this.reverseTime - dt);
    } else if (speed < STUCK_SPEED) {
      this.slowTime += dt;
      if (this.slowTime > STUCK_TIME) {
        this.reverseTime = REVERSE_TIME;
        this.slowTime = 0;
      }
    } else {
      this.slowTime = 0;
    }

    // skid trail
    this.trail = this.trail.filter((seg) => {
      seg[4] -= dt;
      return seg[4] > 0;
    });
    const rad = (this.angle * Math.PI) / 180;
    const c = Math.cos(rad);
    const s = Math.sin(rad);
    const specs: [string, number, number, boolean][] = [
      ["rl", -AXLE_REAR, -1, this.slipR > SKID_SLIP || this.drift],
      ["rr", -AXLE_REAR, 1, this.slipR > SKID_SLIP || this.drift],
      ["fl", AXLE_FRONT, -1, this.slipF > SKID_SLIP * 1.35],
      ["fr", AXLE_FRONT, 1, this.slipF > SKID_SLIP * 1.35],
    ];
    for (const [wname, ax, side, skidding] of specs) {
      const wx = this.x + c * ax - s * side * WHEEL_Y;
      const wy = this.y + s * ax + c * side * WHEEL_Y;
      if (skidding && !this.dead) {
        const prev = this.lastWheelPos[wname];
        if (prev) {
          const [pwx, pwy] = prev;
          const dx = wx - pwx;
          const dy = wy - pwy;
          const distSq = dx * dx + dy * dy;
          if (distSq >= 0.04 && distSq < 1225) {
            const w = this.drift ? 8 : 6;
            this.trail.push([pwx, pwy, wx, wy, TRAIL_LIFE, w]);
          }
        }
        this.lastWheelPos[wname] = [wx, wy];
      } else {
        this.lastWheelPos[wname] = null;
      }
    }
    if (this.trail.length > TRAIL_MAX_POINTS) this.trail = this.trail.slice(-TRAIL_MAX_POINTS);
  }

  rescue(track: Track) {
    this.rescues++;
    const [s, lat, tidx] = track.trackCoords(this.x, this.y, this.trackIdx);
    this.trackIdx = tidx;
    const half = ROAD_WIDTH / 2 - 2 * CAR_HW;
    const [rx, ry, heading] = track.roadPose(s, Math.max(-half, Math.min(half, lat * 0.5)));
    this.x = rx;
    this.y = ry;
    this.angle = heading;
    this.vx = this.vy = this.omega = this.steerAngle = 0;
    this.trackS = s;
    this.wedged = this.slowTime = this.reverseTime = 0;
    this.flash = 0.6;
    this.lastWheelPos = {};
  }

  corners(): [number, number][] {
    const rad = (this.angle * Math.PI) / 180;
    const c = Math.cos(rad);
    const s = Math.sin(rad);
    const hl = 14.0;
    const hw = CAR_HW;
    const local: [number, number][] = [
      [hl * c - hw * s, hl * s + hw * c],
      [hl * c + hw * s, hl * s - hw * c],
      [-hl * c + hw * s, -hl * s - hw * c],
      [-hl * c - hw * s, -hl * s + hw * c],
    ];
    return local.map(([px, py]) => [this.x + px, this.y + py]);
  }
}
