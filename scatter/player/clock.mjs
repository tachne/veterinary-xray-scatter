// All time in this module is display time. No random numbers or transport calculations.
export const PERIOD = 2400;
export const IN = .46, HIT = .67, OUT = .94;
export const SPEEDS = Object.freeze([1, 2, 4, 8, 16]);
export function timeline(n, {showEveryPhoton = false} = {}) {
  let t=0, anchor=0, rate=1, state="ready", pending=0;
  const duration=n*PERIOD;
  function sync(now) {
    if (state!=="playing" || now<=anchor) return;
    const elapsed = (now-anchor)*rate;
    anchor=now;
    if (showEveryPhoton) {
      // A late display frame must not jump over photons. Show the completed
      // direction before advancing, with bounded catch-up on the next frame.
      const owed = Math.min(duration-t, elapsed+pending);
      const step = Math.min(owed, PERIOD/3);
      const start = Math.floor(t/PERIOD)*PERIOD;
      const fullArrow = start + OUT*PERIOD;
      const next = t<fullArrow && t+step>=start+PERIOD ? fullArrow : t+step;
      pending = Math.min(PERIOD/3, Math.max(0, owed-(next-t)));
      t=next;
    } else {
      t=Math.min(duration,t+elapsed);
    }
    if (t===duration) state="ended";
  }
  function snapshot(now) {
    sync(now);
    const i=n ? Math.min(n-1,Math.floor(t/PERIOD)) : 0;
    return {state,t,rate,i,f:n?(t-i*PERIOD)/PERIOD:0};
  }
  return {
    snapshot,
    play(now) { if(!n || state==="playing")return; if(state==="ended")t=0; pending=0;anchor=now;state="playing"; },
    pause(now) { sync(now);if(state==="playing")state="paused"; },
    stop() {t=0;pending=0;state="ready";},
    speed(value,now) { if(!SPEEDS.includes(value))throw Error("speed");sync(now);pending=0;rate=value; },
    inspect(i,now) {if(!Number.isInteger(i)||i<0||i>=n)return;this.pause(now);t=(i+1)*PERIOD-0.001;state="paused";}
  };
}
export function pathAt(e,f,length) {
  if (e.entry) return gridPathAt(e,f);
  const q=Math.max(0,Math.min(1,f/IN)), met=f>=IN;
  const inc=e.end.map(v=>v*q);
  const s=Math.max(0, Math.min(1,(f-HIT)/(OUT-HIT)));
  const tip=e.direction && f>HIT ? e.end.map((v,i)=>
    v+s*(e.exit ? e.exit[i]-v : length*e.direction[i])) : null;
  const stage=!met?"一次X線が進行中":e.process===0?"無相互作用で検出器面に到達":
    e.process===2?"光電吸収・ここで停止":e.process===3?"干渉性散乱・ここで追跡終了":
    tip?"散乱後の方向を表示":"最初の相互作用・コンプトン散乱";
  const complete = e.direction ? f >= OUT - 1e-12 : met;
  const gridStage=e.gridOutcome && complete ? e.gridOutcome : stage;
  return {inc,met,tip,stage:gridStage,complete};
}

const interpolate=(a,b,q)=>a.map((value,i)=>value+(b[i]-value)*q);
function gridPathAt(e,f) {
  // Both views slow the last millimetres for inspection, on the same saved line.
  const start=e.gridPrimary?[0,0,0]:e.end;
  const final=e.gridPrimary?e.end:e.exit;
  const forwardStart=e.gridPrimary?0:HIT;
  const firstLeg=Math.max(0,Math.min(1,(f-forwardStart)/(.76-forwardStart)));
  let point=interpolate(start,e.approach,firstLeg);
  let stage=e.gridPrimary?"一次線がグリッド面へ進行中":"散乱線がグリッド面へ進行中";
  if (f>=.76) point=interpolate(e.approach,e.entry,Math.min(1,(f-.76)/.06));
  if (f>=.82) {
    point=interpolate(e.entry,final,Math.min(1,(f-.82)/(OUT-.82)));
    stage="グリッドの厚さを通る区間";
  }
  const complete=f>=OUT-1e-12;
  if (complete) {point=final;stage=e.gridOutcome;}
  if (e.gridPrimary) return {inc:point,met:complete,tip:null,stage,complete,gridPoint:point};
  const met=f>=IN, tip=f>HIT?point:null;
  if (!met) stage="一次X線が進行中";
  else if (!tip) stage="最初の相互作用・コンプトン散乱";
  return {inc:interpolate([0,0,0],e.end,Math.min(1,f/IN)),met,tip,stage,complete,gridPoint:tip};
}
