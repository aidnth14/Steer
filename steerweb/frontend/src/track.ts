// Ported from steer/sim.py's track generation + centreline math. The tile-grid rendering system
// is NOT ported -- the browser build draws the road as a filled path instead of a tile grid, so
// off-road detection here is the geometric equivalent (lateral distance from centreline) rather
// than sim.py's dist_to_dirt() grid lookup. Same result, simpler without the pygame tile assets.
import { WORLD, ROAD_WIDTH, OFFROAD_RANGE, EDGE_GRACE } from "./constants";

export type Pt = [number, number];

export function wrapDelta(a: number, b: number): number {
  return (((b - a + WORLD / 2) % WORLD) + WORLD) % WORLD - WORLD / 2;
}

const TRACK_SHAPES = ["stadium", "peanut", "teardrop", "tri_oval", "chicane", "kidney"] as const;

// mulberry32: small deterministic PRNG so a seed reproduces the same track (mirrors
// Python's random.Random(seed) role here, not bit-identical but same statistical behaviour)
function makeRng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function catmullRom(pts: Pt[], totalSamples = 280): Pt[] {
  const n = pts.length;
  const res: Pt[] = [];
  const numPerSeg = Math.floor(totalSamples / n);
  const rem = totalSamples - numPerSeg * n;
  for (let i = 0; i < n; i++) {
    const p0 = pts[(i - 1 + n) % n];
    const p1 = pts[i];
    const p2 = pts[(i + 1) % n];
    const p3 = pts[(i + 2) % n];
    const steps = numPerSeg + (i < rem ? 1 : 0);
    for (let s = 0; s < steps; s++) {
      const t = s / steps;
      const t2 = t * t;
      const t3 = t2 * t;
      const x =
        0.5 *
        (2 * p1[0] +
          (-p0[0] + p2[0]) * t +
          (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
          (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3);
      const y =
        0.5 *
        (2 * p1[1] +
          (-p0[1] + p2[1]) * t +
          (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
          (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3);
      res.push([x, y]);
    }
  }
  return res;
}

export function generateRoad(seed: number): Pt[] {
  const rnd = makeRng(seed);
  const shapeIdx = Math.floor(rnd() * TRACK_SHAPES.length);
  const cx = WORLD / 2;
  const cy = WORLD / 2;
  const A = 560 + rnd() * (720 - 560);
  const R = 430 + rnd() * (520 - 430);
  const nStraight = 80;
  const nArc = 60;
  const pts: Pt[] = [];
  const tau = Math.PI * 2;

  if (shapeIdx === 0) {
    // Stadium Oval
    const wobAmp = R * (0.08 + rnd() * 0.06);
    const wobF = rnd() < 0.5 ? 2 : 3;
    const wobP = rnd() * tau;
    for (let i = 0; i < nStraight; i++) {
      const t = i / nStraight;
      const w = wobAmp * Math.sin(wobF * t * tau + wobP) * Math.max(0, (t - 0.45) / 0.55);
      pts.push([cx - A + 2 * A * t, cy + R + w]);
    }
    for (let i = 0; i < nArc; i++) {
      const t = i / nArc;
      const ang = Math.PI / 2 - Math.PI * t;
      pts.push([cx + A + R * Math.cos(ang), cy + R * Math.sin(ang)]);
    }
    for (let i = 0; i < nStraight; i++) {
      const t = i / nStraight;
      const w = wobAmp * Math.sin(wobF * t * tau + wobP + Math.PI) * Math.sin(Math.PI * t);
      pts.push([cx + A - 2 * A * t, cy - R + w]);
    }
    for (let i = 0; i < nArc; i++) {
      const t = i / nArc;
      const ang = -Math.PI / 2 - Math.PI * t;
      pts.push([cx - A + R * Math.cos(ang), cy + R * Math.sin(ang)]);
    }
  } else if (shapeIdx === 1) {
    // Peanut / Dogbone
    const dip = 160 + rnd() * 80;
    for (let i = 0; i < nStraight; i++) {
      const t = i / nStraight;
      pts.push([cx - A + 2 * A * t, cy + R]);
    }
    for (let i = 0; i < nArc; i++) {
      const t = i / nArc;
      const ang = Math.PI / 2 - Math.PI * t;
      pts.push([cx + A + R * Math.cos(ang), cy + R * Math.sin(ang)]);
    }
    for (let i = 0; i < nStraight; i++) {
      const t = i / nStraight;
      const w = dip * Math.sin(Math.PI * t);
      pts.push([cx + A - 2 * A * t, cy - R + w]);
    }
    for (let i = 0; i < nArc; i++) {
      const t = i / nArc;
      const ang = -Math.PI / 2 - Math.PI * t;
      pts.push([cx - A + R * Math.cos(ang), cy + R * Math.sin(ang)]);
    }
  } else if (shapeIdx === 2) {
    // Teardrop
    const rTight = 340 + rnd() * 50;
    const rWide = 540 + rnd() * 60;
    for (let i = 0; i < nStraight; i++) {
      const t = i / nStraight;
      const blend = 0.5 * (1 - Math.cos(Math.PI * Math.max(0, (t - 0.4) / 0.6)));
      const y = cy + rTight + (rWide - rTight) * blend;
      pts.push([cx - A + 2 * A * t, y]);
    }
    for (let i = 0; i < nArc; i++) {
      const t = i / nArc;
      const ang = Math.PI / 2 - Math.PI * t;
      pts.push([cx + A + rWide * Math.cos(ang), cy + rWide * Math.sin(ang)]);
    }
    for (let i = 0; i < nStraight; i++) {
      const t = i / nStraight;
      const y = cy - rWide + (rWide - rTight) * t;
      pts.push([cx + A - 2 * A * t, y]);
    }
    for (let i = 0; i < nArc; i++) {
      const t = i / nArc;
      const ang = -Math.PI / 2 - Math.PI * t;
      pts.push([cx - A + rTight * Math.cos(ang), cy + rTight * Math.sin(ang)]);
    }
  } else if (shapeIdx === 3) {
    // Tri-Oval / Delta
    const rBot = 430 + rnd() * 60;
    const rTop = 520 + rnd() * 80;
    const ctrl: Pt[] = [
      [cx - A, cy + rBot],
      [cx - A / 3, cy + rBot],
      [cx + A / 3, cy + rBot],
      [cx + A, cy + rBot],
      [cx + A + 240, cy + rBot - 190],
      [cx + A / 2 + 100, cy - rTop / 2],
      [cx + 150, cy - rTop],
      [cx, cy - rTop - 50],
      [cx - 150, cy - rTop],
      [cx - A / 2 - 100, cy - rTop / 2],
      [cx - A - 240, cy + rBot - 190],
    ];
    pts.push(...catmullRom(ctrl, 280));
  } else if (shapeIdx === 4) {
    // Technical Chicane / S-Loop
    const chicaneAmp = 140 + rnd() * 60;
    for (let i = 0; i < nStraight; i++) {
      const t = i / nStraight;
      pts.push([cx - A + 2 * A * t, cy + R]);
    }
    for (let i = 0; i < nArc; i++) {
      const t = i / nArc;
      const ang = Math.PI / 2 - Math.PI * t;
      pts.push([cx + A + R * Math.cos(ang), cy + R * Math.sin(ang)]);
    }
    for (let i = 0; i < nStraight; i++) {
      const t = i / nStraight;
      const w = chicaneAmp * Math.sin(2 * Math.PI * t);
      pts.push([cx + A - 2 * A * t, cy - R + w]);
    }
    for (let i = 0; i < nArc; i++) {
      const t = i / nArc;
      const ang = -Math.PI / 2 - Math.PI * t;
      pts.push([cx - A + R * Math.cos(ang), cy + R * Math.sin(ang)]);
    }
  } else {
    // Kidney Bean
    const bulge = 150 + rnd() * 70;
    for (let i = 0; i < nStraight; i++) {
      const t = i / nStraight;
      pts.push([cx - A + 2 * A * t, cy + R]);
    }
    for (let i = 0; i < nArc; i++) {
      const t = i / nArc;
      const ang = Math.PI / 2 - Math.PI * t;
      const rCurr = R + bulge * Math.sin(Math.PI * t);
      pts.push([cx + A + rCurr * Math.cos(ang), cy + R * Math.sin(ang)]);
    }
    for (let i = 0; i < nStraight; i++) {
      const t = i / nStraight;
      const w = -bulge * 0.7 * Math.sin(Math.PI * t);
      pts.push([cx + A - 2 * A * t, cy - R + w]);
    }
    for (let i = 0; i < nArc; i++) {
      const t = i / nArc;
      const ang = -Math.PI / 2 - Math.PI * t;
      pts.push([cx - A + R * Math.cos(ang), cy + R * Math.sin(ang)]);
    }
  }
  return pts;
}

export class Track {
  road: Pt[];
  roadS: number[] = [0];
  roadT: Pt[] = [];
  roadLen = 1;

  constructor(seed: number) {
    this.road = generateRoad(seed);
    const n = this.road.length;
    for (let i = 0; i < n; i++) {
      const [ax, ay] = this.road[i];
      const [bx, by] = this.road[(i + 1) % n];
      const seg = Math.hypot(bx - ax, by - ay) || 1e-9;
      this.roadS.push(this.roadS[this.roadS.length - 1] + seg);
      this.roadT.push([(bx - ax) / seg, (by - ay) / seg]);
    }
    this.roadLen = this.roadS[this.roadS.length - 1];
  }

  // point on the road at arc length s, shifted `lateral` px right of centre; heading in degrees
  roadPose(s: number, lateral = 0): [number, number, number] {
    s = ((s % this.roadLen) + this.roadLen) % this.roadLen;
    let i = this.bisectRight(s) - 1;
    if (i < 0) i = 0;
    if (i >= this.road.length) i = this.road.length - 1;
    const [ax, ay] = this.road[i];
    const [tx, ty] = this.roadT[i];
    const d = s - this.roadS[i];
    return [ax + tx * d - ty * lateral, ay + ty * d + tx * lateral, (Math.atan2(ty, tx) * 180) / Math.PI];
  }

  private bisectRight(s: number): number {
    let lo = 0;
    let hi = this.roadS.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (s < this.roadS[mid]) hi = mid;
      else lo = mid + 1;
    }
    return lo;
  }

  // (arc length, px right of centreline, nearest sample index) for a world point
  trackCoords(x: number, y: number, hint: number | null = null): [number, number, number] {
    const n = this.road.length;
    if (n === 0) return [0, 0, 0];
    let bestI = 0;
    let bestD = Infinity;
    const searchAll = hint === null;
    const lo = searchAll ? 0 : hint! - 40;
    const hi = searchAll ? n : hint! + 40;
    for (let j = lo; j < hi; j++) {
      const i = ((j % n) + n) % n;
      const [rx, ry] = this.road[i];
      const dx = wrapDelta(rx, x);
      const dy = wrapDelta(ry, y);
      const d = dx * dx + dy * dy;
      if (d < bestD) {
        bestD = d;
        bestI = i;
      }
    }
    if (!searchAll && bestD > 260 * 260) return this.trackCoords(x, y, null);
    let i = bestI;
    let [ax, ay] = this.road[i];
    let [tx, ty] = this.roadT[i];
    let dx = wrapDelta(ax, x);
    let dy = wrapDelta(ay, y);
    let along = dx * tx + dy * ty;
    if (along < 0) {
      i = (i - 1 + n) % n;
      [ax, ay] = this.road[i];
      [tx, ty] = this.roadT[i];
      dx = wrapDelta(ax, x);
      dy = wrapDelta(ay, y);
      along = dx * tx + dy * ty;
    }
    along = Math.min(Math.max(along, 0), this.roadS[i + 1] - this.roadS[i]);
    return [this.roadS[i] + along, -dx * ty + dy * tx, i];
  }

  // 0 on the road (or within EDGE_GRACE), ramps to 1 further onto the grass
  offroadFactor(x: number, y: number, hint: number | null = null): number {
    const [, lat] = this.trackCoords(x, y, hint);
    const distPastEdge = Math.max(0, Math.abs(lat) - ROAD_WIDTH / 2);
    const past = distPastEdge - EDGE_GRACE;
    return Math.max(past, 0) / OFFROAD_RANGE;
  }
}
