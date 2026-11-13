import {test} from 'node:test';
import assert from 'node:assert/strict';
import {pathAt, PERIOD, timeline} from '../scatter/player/clock.mjs';
import {TrackHistory} from '../scatter/player/history.mjs';
import {directionGuide,localCamera,syncedGridPhase} from '../scatter/player/paired_ray.mjs';

const grid={top:99.84,sid:100,height:.16,focus:100,halfWidth:22,gap:.02,foil:.005,pitch:.025};
const entry=[11.12,0,grid.top], slope=.36;
const ray=z=>[entry[0]+(z-grid.top)*slope,0,z];
const off={id:16,seed:42,process:1,gridPrimary:false,entry,approach:ray(99.82),end:ray(82),
           direction:[slope,0,1],xzDirection:[slope,1],exit:ray(grid.sid),gridCode:4,gridOutcome:'到達'};
const on={...off,gridCode:5,exit:ray(99.90),gridOutcome:'鉛箔で吸収'};
const approx=(a,b)=>assert.ok(Math.abs(a-b)<1e-10, a+' != '+b);
test('both moving rays coincide until first lead contact; only the clear ray continues',()=>{
  for(const f of [.5,.67,.77,.82,.83,.85,.87,.89,.91,.94,1]){
    const a=pathAt(off,f,18),b=pathAt(on,syncedGridPhase(off,on,f),18);
    if(a.gridPoint && b.gridPoint) {
      const z=Math.min(a.gridPoint[2],on.exit[2]); approx(b.gridPoint[2],z);approx(b.gridPoint[0],ray(z)[0]);
      if(b.complete) assert.deepEqual(b.gridPoint,on.exit);
    }
    assert.equal(directionGuide(on,[30,40],55),null);
  }
  const faceHit={...on,exit:entry};assert.deepEqual(pathAt(faceHit,syncedGridPhase(off,faceHit,.82),18).gridPoint,entry);
});
test('only real arrivals receive a display-unit arrow, preserving its sign, normal and magnitude-independent direction',()=>{
  for(const code of [0,1,2,3,5,6])assert.equal(directionGuide({...off,gridCode:code},[0,0],44),null);
  for(const dx of [-.99,0,.45,.99]){
    const e={...off,xzDirection:[dx,.03]};
    for(const size of [24,55]){
      const [x,z]=directionGuide(e,[12,3],size);
      approx((x-12)*.03,(z-3)*dx);approx(Math.hypot(x-12,z-3),size);
      assert.ok(z>3); assert.equal(e.exit[2],grid.sid);
    }
  }
});
test('the identical local x/z metric preserves rays, actual entrance, contact and detector coordinates on both sides',()=>{
  const camera=localCamera(grid,off,on);const point=v=>camera.point(v[0],v[2]);
  const [x,z]=point(entry);
  for(const e of [off,on]){const [x2,z2]=point(e.exit);
    approx((x2-x)/(z2-z),slope);approx((z2-z)/camera.scale,e.exit[2]-grid.top);
  }
  assert.ok(point(on.exit)[1]<point(off.exit)[1]);
  approx(point(off.exit)[1],142);
  const edge={...off,entry:[22,0,grid.top],exit:[22,0,grid.sid]};
  assert.equal(localCamera(grid,edge,edge).right,22);
});
test('400 paired events complete at 16x, with separate detector sets, no invented arrivals or session cross-talk',()=>{
  const records=Array.from({length:400},(_,i)=>[off,i%5===0?off:on]);
  const h=new TrackHistory(),clock=timeline(records.length,{showEveryPhoton:true});
  const arrivals=[new Set(),new Set()], second=new TrackHistory();
  clock.speed(16,0);clock.play(0);
  let snap;
  for(let now=0;now<61000;now+=17){
    snap=clock.snapshot(now);
    const [a,b]=records[snap.i], pa=pathAt(a,snap.f,18), pb=pathAt(b,syncedGridPhase(a,b,snap.f),18);
    h.observe(snap.i,42,snap.f,pa);
    for(const [k,e,p] of [[0,a,pa],[1,b,pb]])if(p.complete&&directionGuide(e,[0,0],48))arrivals[k].add(snap.i);
    if(snap.state==='ended')break;
  }
  assert.equal(snap.state,'ended');assert.equal(h.phases.size,400);
  assert.deepEqual(arrivals.map(a=>a.size),[400,80]);assert.equal(second.phases.size,0);
  assert.equal(snap.t,400*PERIOD);
});
