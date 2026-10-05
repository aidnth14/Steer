// Ported from steer/sim.py. Keep values in sync with the Python original -- these are the
// tuned numbers that give the game its feel, not arbitrary.

export const W = 600;
export const H = 400;
export const WORLD = 4800; // world wraps at this size

// ---- track ----
export const ROAD_WIDTH = 240;
export const OFFROAD_RANGE = 50.0;
export const EDGE_GRACE = 6.0;

// ---- car dimensions ----
export const CAR_HL = 14.0;
export const CAR_HW = 7.0;
export const AXLE_FRONT = 9.5;
export const AXLE_REAR = 8.5;
export const WHEELBASE = AXLE_FRONT + AXLE_REAR;
export const WHEEL_Y = 8.5;
export const CAR_MASS = 1.0;
export const CAR_INERTIA = (1.6 * (4 * CAR_HL * CAR_HL + 4 * CAR_HW * CAR_HW)) / 12;

// ---- engine ----
export const MAX_SPEED = 380.0;
export const ENGINE_ACCEL = 430.0;
export const ENGINE_FALLOFF = 0.3;
export const ROLL_RESIST = 25.0;
export const AIR_DRAG = 0.0019;

// ---- tyres ----
export const GRIP = 560.0;
export const TIRE_PEAK_SLIP = 0.14;
export const TIRE_SHAPE = 1.45;
export const TIRE_B = Math.tan(Math.PI / (2 * TIRE_SHAPE)) / TIRE_PEAK_SLIP;
export const DRIVE_GRIP_USE = 0.45;
export const STEER_MAX = 0.6;
export const STEER_GRIP_RATIO = 1.2;
export const STEER_RATE = 5.0;
export const V_FLOOR = 40.0;
export const YAW_DAMP = 0.6;
export const STABILITY = 3.0;
export const DRIFT_GRIP = 0.55;

// ---- grass ----
export const GRASS_GRIP = 0.6;
export const GRASS_ENGINE_LOSS = 0.5;
export const GRASS_RESIST = 2.5;

// ---- collisions ----
export const CAR_RESTITUTION = 0.45;
export const CAR_FRICTION = 0.3;
export const WALL_RESTITUTION = 0.3;
export const WALL_FRICTION = 0.5;
export const MAX_SPIN = 9.0;

// ---- bashing ----
export const BASH_COOLDOWN = 1.5;
export const BASH_TIME = 0.18;
export const BASH_SIDE_SPEED = 190.0;
export const BASH_MASS = 2.5;
export const BASH_KNOCK = 150.0;
export const BASH_TIRE = 0.35;
export const BASH_SPIN = 0.3;
export const RAM_TIME = 0.3;
export const RAM_SPEED = 150.0;
export const STAGGER_TIME = 0.45;
export const STAGGER_GRIP = 0.5;

// ---- reverse / stuck recovery ----
export const STUCK_SPEED = 25.0;
export const STUCK_TIME = 0.8;
export const REVERSE_TIME = 0.7;
export const REVERSE_ACCEL = 260.0;
export const REVERSE_SPEED = 90.0;
export const RESCUE_TIME = 3.0;
export const BRAKE_ACCEL = 480.0;

// ---- hearts ----
export const HEART_COUNT = 3;
export const HEART_PENALTY = 0.5;
export const HEART_COOLDOWN = 1.0;

// ---- boxes / boost ----
export const BOOST_TIME = 1.8;
export const BOOST_PACE = 0.9;
export const BOOST_KICK = 90.0;
export const DRAFT_PACE = 0.16;
export const SLIPSTREAM_ASSIST = true;

// ---- skid marks ----
export const SKID_SLIP = 55.0;
export const TRAIL_LIFE = 13.0;
export const TRAIL_MAX_POINTS = 3000;

// ---- laps / fence ----
export const TOTAL_LAPS = 3;
export const FENCE_OFFSET = 2;
export const TILE = 16;

// ---- camera ----
export const ZOOM = 1.68;

export const TEAM_COLORS = ["#e64646", "#4678eb"];
