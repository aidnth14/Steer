// Keyboard input, matching steer/main.py's default bindings (A/D steer, Space ram, Q/E side-bash,
// Shift drift, S brake). Touch/gyro mobile controls are not ported yet (next milestone).
export class Keyboard {
  private down = new Set<string>();

  constructor() {
    window.addEventListener("keydown", (e) => this.down.add(e.code));
    window.addEventListener("keyup", (e) => this.down.delete(e.code));
  }

  isDown(code: string): boolean {
    return this.down.has(code);
  }

  steer(): number {
    let s = 0;
    if (this.isDown("KeyA") || this.isDown("ArrowLeft")) s -= 1;
    if (this.isDown("KeyD") || this.isDown("ArrowRight")) s += 1;
    return s;
  }

  drift(): boolean {
    return this.isDown("ShiftLeft") || this.isDown("ShiftRight");
  }

  brake(): boolean {
    return this.isDown("KeyS") || this.isDown("ArrowDown");
  }

  ramPressed(): boolean {
    return this.isDown("Space");
  }

  bashLeftEdge(): boolean {
    return this.consumeEdge("KeyQ");
  }

  bashRightEdge(): boolean {
    return this.consumeEdge("KeyE");
  }

  private edges = new Set<string>();
  private consumeEdge(code: string): boolean {
    if (this.down.has(code) && !this.edges.has(code)) {
      this.edges.add(code);
      return true;
    }
    if (!this.down.has(code)) this.edges.delete(code);
    return false;
  }
}
