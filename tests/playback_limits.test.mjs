import {test} from 'node:test';
import assert from 'node:assert/strict';
import {timeline, PERIOD, OUT, SPEEDS} from '../scatter/player/clock.mjs';

function display(n) {
  return timeline(n, {showEveryPhoton: true});
}

test('the five offered rates preserve the current virtual time when selected', () => {
  assert.deepEqual(SPEEDS, [1, 2, 4, 8, 16]);
  const c = display(100);
  c.play(0);
  let now = 0;
  for (const rate of SPEEDS) {
    const cursor = c.snapshot(now);
    c.speed(rate, now);
    assert.deepEqual(c.snapshot(now), {...cursor, rate});
    now += 17;
    assert.equal(c.snapshot(now).t, cursor.t + 17 * rate);
  }
  assert.throws(() => c.speed(32, now));
});

for (const count of [16, 32, 50, 100, 300]) {
  test(count + ' distinct photons reach their full paths and the last frame at 16x', () => {
    const c = display(count);
    c.speed(16, 0);
    c.play(0);
    const seen = new Set(), complete = new Set();
    // Normal 60 Hz cadence. Half a millisecond of jitter and one slow frame.
    for (let tick = 0; tick <= count * 12; tick++) {
      const elapsed = tick * (1000 / 60) + (tick % 2) * .5 + (tick >= 9 ? 260 : 0);
      const s = c.snapshot(elapsed);
      seen.add(s.i);
      if (s.f >= OUT - 1e-12) complete.add(s.i);
      if (s.state === 'ended') {
        assert.equal(s.f, 1);
        assert.equal(s.i, count-1);
        assert.ok(Math.abs(elapsed - count * PERIOD / 16) < 400);
        break;
      }
    }
    const expected = Array.from({length: count}, (_, i) => i);
    assert.deepEqual([...seen], expected);
    assert.deepEqual([...complete], expected);
    assert.equal(c.snapshot(1e7).state, 'ended');
  });
}

test('even when frames arrive slowly, a full outgoing path is drawn for each photon', () => {
  const c = display(100);
  c.speed(16, 0);
  c.play(0);
  const completed = new Set();
  for (let frame = 1; frame <= 600; frame++) {
    const s = c.snapshot(frame * 265);
    if (s.f >= OUT - 1e-12) completed.add(s.i);
    if (s.state === 'ended') break;
  }
  assert.equal(completed.size, 100);
  assert.equal(c.snapshot(2e5).state, 'ended');
});

test('paused and running speed changes preserve position and separate sessions', () => {
  const a = display(300), b = display(100);
  a.play(0);
  for (let t = 10; t <= 500; t += 10) a.snapshot(t);
  a.speed(8, 500);
  a.pause(525);
  const paused = a.snapshot(525);
  a.speed(16, 2000);
  assert.deepEqual(a.snapshot(5e4), {...paused, rate:16});
  a.play(6e4);
  assert.equal(a.snapshot(6e4+10).t, paused.t+160);
  assert.deepEqual(b.snapshot(7e4), {state:'ready', t:0, i:0, f:0, rate:1});
  a.stop();
  assert.equal(a.snapshot(7e4).t, 0);
});
