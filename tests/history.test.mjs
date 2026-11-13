import {test} from 'node:test';
import assert from 'node:assert/strict';
import {timeline, pathAt, PERIOD, IN, HIT, OUT} from '../scatter/player/clock.mjs';
import {TrackHistory} from '../scatter/player/history.mjs';

const photon = process => ({
  process, end: [3, -4, 80], direction: process === 1 ? [.6, 0, -.8] : null
});
const events = Array.from({length: 100}, (_, i) => photon(i % 4));
function observe(history, index, seed, fraction, sample = events) {
  history.observe(index, seed, fraction, pathAt(sample[index % sample.length], fraction, 18));
}

test('100 photons at 16x retain all prior IDs and only calculated outgoing paths', () => {
  const history = new TrackHistory();
  const clock = timeline(100, {showEveryPhoton: true});
  clock.speed(16, 0);
  clock.play(0);
  let previous = [], state;
  const milestones = new Set();
  for (let frame = 0; frame < 1500; frame++) {
    state = clock.snapshot(frame * 17);
    observe(history, state.i, 42, state.f);
    const ids = [...history.phases.keys()];
    assert.deepEqual(ids.slice(0, previous.length), previous);
    previous = ids;
    milestones.add(ids.length);
    if (state.state === 'ended') break;
  }
  assert.equal(state.state, 'ended');
  for (const n of [0, 1, 10, 50, 100]) assert.ok(milestones.has(n));
  assert.equal(history.completed.size, 100);
  assert.deepEqual([...history.scattered], events.flatMap((e, i) => e.direction ? [i] : []));
  assert.ok([...history.phases.values()].every(f => f === 1));
});

test('photons count at entry, interactions count at their recorded visible stages', () => {
  const history = new TrackHistory();
  observe(history, 1, 42, 0);
  assert.equal(history.phases.size, 0);
  observe(history, 1, 42, .1);
  assert.equal(history.phases.size, 1);
  observe(history, 1, 42, IN);
  assert.equal(history.scattered.size, 0);
  observe(history, 1, 42, HIT + .01);
  assert.equal(history.scattered.size, 1);
  assert.equal(history.completed.size, 0);
  observe(history, 1, 42, OUT);
  for (const i of [0, 2, 3]) observe(history, i, 42, IN);
  assert.deepEqual([history.phases.size, history.completed.size, history.scattered.size], [4, 4, 1]);
});

test('pause keeps the partial path through speed changes, then resume extends it', () => {
  const history = new TrackHistory(), clock = timeline(100);
  clock.play(0);
  clock.pause(PERIOD*.2);
  for (const time of [1000, 4000]) {
    clock.speed(8, time);
    const state = clock.snapshot(time);
    observe(history, state.i, 42, state.f);
    assert.equal(history.phases.get(0), .2);
    assert.equal(history.completed.size, 0);
  }
  clock.play(5000);
  const next = clock.snapshot(5020);
  observe(history, next.i, 42, next.f);
  assert.ok(history.phases.get(0) > .2);
  assert.equal(history.phases.size, 1);
});

test('inspection preserves actual partial tracks, does not invent skipped photons or count a visit twice', () => {
  const history = new TrackHistory();
  observe(history, 0, 42, .2);
  observe(history, 50, 42, 1);
  observe(history, 50, 42, 1);
  observe(history, 0, 42, .15);
  assert.deepEqual([...history.phases], [[0, .2], [50, 1]]);
  assert.deepEqual([...history.completed], [50]);
  observe(history, 0, 42, 1);
  assert.equal(history.completed.size, 2);
});

test('CSV-identical photon numbers across three seeds are separate visits and their drawings clear', () => {
  const history = new TrackHistory();
  for (const seed of [1, 2, 3]) {
    const start = (seed - 1)*100; // global playlist index, even when photon IDs repeat
    observe(history, start, seed, 0);
    assert.equal(history.phases.size, 0);
    assert.equal(history.scattered.size, 0);
    assert.equal(history.completed.size, start);
    for (let i = start; i < start + 100; i++) observe(history, i, seed, 1);
    assert.equal(history.phases.size, 100);
    assert.equal(history.scattered.size, 25);
    assert.equal(history.completed.size, start + 100);
    assert.equal(history.phases.keys().next().value, start);
  }
});

test('stopping clears completion and projected paths; another player retains its seed and history', () => {
  const a = new TrackHistory(), b = new TrackHistory();
  for (let i = 0; i < 100; i++) observe(a, i, 42, 1);
  observe(b, 1, 1, .8);
  a.reset();
  assert.deepEqual([a.completed.size, a.phases.size, a.scattered.size], [0, 0, 0]);
  assert.deepEqual([b.completed.size, b.phases.size, b.scattered.size, b.seed], [0, 1, 1, 1]);
  observe(a, 0, 42, .1);
  assert.deepEqual([...a.phases], [[0, .1]]);
});

test('partial and complete tracks can be reprojected from the same stored phases and events', () => {
  const h = new TrackHistory();
  observe(h, 1, 42, 1);
  observe(h, 3, 42, .2);
  const project = scale => [...h.phases].map(([i, phase]) => {
    const path = pathAt(events[i], phase, 18);
    const xz = point => point && [point[0] * scale, point[2] * scale];
    return [i, xz(path.inc), xz(path.tip)];
  });
  const room = project(1);
  assert.deepEqual(project(3), room.map(([i, inc, tip]) =>
    [i, inc.map(v => 3*v), tip && tip.map(v => 3*v)]));
  assert.deepEqual(project(1), room);
  assert.deepEqual([...h.completed], [1]);
});
