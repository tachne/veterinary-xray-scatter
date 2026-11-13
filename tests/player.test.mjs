import {test} from 'node:test';
import assert from 'node:assert/strict';
import {timeline, PERIOD, pathAt} from '../scatter/player/clock.mjs';

test('pause freezes both the current photon and its exact phase, resume from it',()=>{
  const c=timeline(3);c.play(100); c.pause(100+PERIOD+700);
  const s=c.snapshot(9000); assert.equal(s.i,1);assert.equal(s.t,PERIOD+700);
  assert.deepEqual(s,c.snapshot(13000));c.play(15000);
  assert.equal(c.snapshot(15200).t,PERIOD+900);
});
test('rate change is continuous and stop returns to first photon',()=>{
  const c=timeline(5);c.play(0);c.speed(4,400);assert.equal(c.snapshot(400).t,400);
  assert.equal(c.snapshot(900).i,1);c.stop();
  const init=c.snapshot(15000);assert.equal(init.i,0);assert.equal(init.f,0);assert.equal(init.state,'ready');
});
test('automatic advancement crosses a seed boundary and terminates, play restarts',()=>{
  const c=timeline(3),seeds=[1,2,3];c.play(0);
  [0,1,2].forEach(i=>assert.equal(seeds[c.snapshot(i*PERIOD).i],i+1));
  const end=c.snapshot(9*PERIOD);assert.equal(end.state,'ended');assert.equal(end.i,2);assert.equal(end.f,1);
  c.play(10*PERIOD);assert.equal(c.snapshot(10*PERIOD).i,0);
});
test('independent players and selection pause only the chosen instance',()=>{
  const a=timeline(12),b=timeline(12);a.play(0);a.inspect(7,460);
  assert.equal(a.snapshot(900).i,7);assert.equal(a.snapshot(900).state,'paused');
  assert.equal(b.snapshot(900).state,'ready');assert.equal(b.snapshot(900).i,0);
});
test('all stages project the saved vectors, the arrow starts at the interaction',()=>{
  const e={end:[3,4,10],direction:[-.6,0,.8],process:1};
  assert.deepEqual(pathAt(e,.23,18).inc,[1.5,2,5]);
  assert.equal(pathAt(e,.55,18).tip,null);
  const last=pathAt(e,1,18);assert.deepEqual(last.inc,e.end);
  assert.deepEqual(last.tip,e.end.map((v,i)=>v+18*e.direction[i]));
});
test('unscattered, absorbed and coherent tracks have no outgoing segment; an empty queue cannot run',()=>{
  for(const code of [0,2,3]) for(const f of [.2,.6,1])
    assert.equal(pathAt({end:[0,0,8],direction:null,process:code},f,18).tip,null);
  const c=timeline(0);c.play(0);assert.equal(c.snapshot(5000).state,'ready');
});
