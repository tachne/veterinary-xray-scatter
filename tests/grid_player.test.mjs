import {test} from 'node:test';
import assert from 'node:assert/strict';
import {timeline, PERIOD, pathAt} from '../scatter/player/clock.mjs';
import {TrackHistory} from '../scatter/player/history.mjs';

test('scattered segments use the paired endpoint and never extend through lead', () => {
  const event={process:1,end:[2,0,94],direction:[0.6,0,0.8],exit:[6.2,0,99.6],
    gridOutcome:'鉛箔で吸収'};
  const start=pathAt(event,.60,18), mid=pathAt(event,.8,18), end=pathAt(event,1,18);
  assert.equal(start.tip,null);
  assert.ok(mid.tip[2]>94 && mid.tip[2]<99.6 && !mid.complete);
  assert.deepEqual(end.tip,event.exit);
  assert.equal(end.stage,event.gridOutcome);
  const primary={process:0,end:[2.4,0,99.84],direction:null,gridOutcome:'鉛箔で吸収'};
  assert.deepEqual(pathAt(primary,.9,18).inc,primary.end);
  assert.equal(pathAt(primary,.9,18).tip,null);
});

test('the room and millimetre inset share one point through the grid, without a direction change',()=>{
  const e={process:1,end:[2,-1,80],direction:[.3,.1,1],entry:[8,1,100],approach:[7.97,.99,99.9],
           exit:[8.03,1.01,100.1],gridOutcome:'鉛箔で吸収',gridPrimary:false};
  const atEntry=pathAt(e,.82,18), middle=pathAt(e,.88,18), final=pathAt(e,1,18);
  assert.deepEqual(atEntry.tip,e.entry);
  assert.ok(Math.abs(middle.tip[2]-100.05)<1e-12);
  assert.ok(Math.abs(middle.tip[0]-8.015)<1e-12);
  assert.equal(middle.tip,middle.gridPoint);
  assert.deepEqual(final.tip,e.exit);
  const primary={process:0,gridPrimary:true,end:[10,0,100],approach:[9.97,0,99.7],
      entry:[9.98,0,99.8],gridOutcome:'検出器面に到達'};
  const result=pathAt(primary,.82,18);
  assert.deepEqual(result.inc,primary.entry);
  assert.equal(result.tip,null);
  assert.equal(result.complete,false);
});

for (const count of [200,400,1200]) {
  test(count+' real-time slots at 16x preserve each projected path and independent seed histories',()=>{
    const c=timeline(count,{showEveryPhoton:true}), history=new TrackHistory();
    c.speed(16,0);
    c.play(0);
    const event={process:1,end:[1,0,95],direction:[0,0,1],exit:[1,0,100],gridOutcome:'検出器面に到達'};
    let last, now=0;
    for (let frame=0; frame<count*14; frame++) {
      last=c.snapshot(now);
      const seed=Math.floor(last.i/400)+1;
      history.observe(last.i,seed,last.f,pathAt(event,last.f,18));
      if (frame===110) {
        c.pause(now);
        const before=c.snapshot(now);
        now+=600;
        assert.deepEqual(c.snapshot(now),before);
        c.play(now);
      }
      if (last.state==='ended') break;
      now+=(frame===25 ? 250 : 17);
    }
    assert.equal(last.state,'ended');
    assert.equal(history.completed.size,count);
    assert.equal(history.phases.size,Math.min(count,400));
    assert.equal(history.scattered.size,Math.min(count,400));
    assert.equal(history.seed,Math.ceil(count/400));
    assert.ok(now<count*PERIOD/16+950);
    history.reset();c.stop();
    assert.equal(history.phases.size,0);
  });
}
