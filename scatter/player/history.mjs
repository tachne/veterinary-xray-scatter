// The indices belong to one immutable playlist. A seek visits just the
// selected record. A camera change retains the same instance and phases.
export class TrackHistory {
  constructor() {
    this.phases = new Map();
    this.scattered = new Set();
    this.completed = new Set();
    this.reset();
  }

  reset() {
    this.seed = null;
    this.phases.clear();
    this.scattered.clear();
    this.completed.clear();
  }

  observe(index, seed, fraction, path) {
    if (this.seed !== seed) {
      this.seed = seed;
      this.phases.clear();
      this.scattered.clear();
    }
    if (fraction <= 0) return;
    const phase = path.complete ? 1 : fraction;
    if (phase > (this.phases.get(index) ?? 0)) this.phases.set(index, phase);
    if (path.tip) this.scattered.add(index);
    if (path.complete) this.completed.add(index);
  }
}
