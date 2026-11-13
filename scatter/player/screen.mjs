// A single browser clock drives every camera; zoom and controls never call Streamlit.
export default function render({parentElement,data}) {
  const panel=parentElement.querySelector(".film"), el=k=>panel.querySelector('[data-c="'+k+'"]');
  const sig=JSON.stringify(data.signature), old=panel._filmState, same=old?.sig===sig;
  const ev=data.events, cases=data.pairedGrid ? [ev,data.eventsWith] : [ev];
  const clock=same?old.clock:timeline(ev.length,{showEveryPhoton:true});
  const history=same?old.history:new TrackHistory();
  old?.dispose?.();
  const binding={sig,clock,history};panel._filmState=binding;
  let raf=0,disposed=false,lastText="",width=0,exampleSeed=null;
  const labels={ready:"準備完了",playing:"再生中",paused:"一時停止中",ended:"再生終了"};
  const play=el("play"),pause=el("pause"),stop=el("stop"),speed=el("speed"),opt=el("seek");
  const zoom=el("down-zoom"), paired=!!data.pairedGrid;
  panel.classList.toggle("has-pair",paired);el("rooms").classList.toggle("paired-rooms",paired);
  el("paired").hidden=!paired;el("second-room").hidden=!paired;el("room-label").hidden=!paired;
  el("room-intro").hidden=!paired;
  if (paired) {
    const names=["一次線", ...data.groups], colors=["#536d79", ...data.colors];
    el("room-sources").replaceChildren(...names.map((name,index)=>{
      const swatch=document.createElement("span");
      swatch.style.setProperty("--ray-color",colors[index]);
      swatch.textContent=name;
      return swatch;
    }));
  }
  function casePhase(side,i,f){return side?syncedGridPhase(ev[i],cases[1][i],f):f;}
  const pathFor=(side,i,f)=>pathAt(cases[side][i],casePhase(side,i,f),data.length);
  const cams=cases.map((events,k)=>roomCamera(el(k?"screen-on":"screen"),k?data.sceneWith:data.scene,
       events,data,inspect,(paired?"paired-":"room-")+k+"-camera-clip"));
  const detector=paired ? detectorViews(panel,cases,data.gridGeometry,pathFor):null;
  const label=e=>e.gridPrimary?"一次線":e.part<0?"検出器面（相互作用なし）":data.groups[e.group]+"・"+data.parts[e.part];
  function write(k,v){const node=el(k);if(node.textContent!==v)node.textContent=v;}
  function inspect(i) {
    const now=performance.now();clock.pause(now);frame(now);clock.inspect(i,now);
    cancelAnimationFrame(raf);frame(now);
  }
  function examples(seed) {
    if(!paired||exampleSeed===seed)return;
    exampleSeed=seed;
    const hits=(fn)=>cases[1].findIndex(e=>e.seed===seed && fn(e));
    const blocked=e=>e.entry && !e.gridPrimary && e.gridCode===5;
    const inside=hits(e=>blocked(e) && (e.exit[2]-e.entry[2])>.2*data.gridGeometry.height &&
                     (e.exit[2]-e.entry[2])<.85*data.gridGeometry.height &&
                     Math.abs(e.xzDirection[0]/e.xzDirection[1])*data.gridGeometry.height<4*data.gridGeometry.gap);
    for(const [key,i,name] of [
        ["primary",hits(e=>e.gridPrimary && e.gridCode===4),"一次線の通過"],
        ["block",inside>=0?inside:hits(blocked),"散乱線の吸収"],
        ["pass",hits(e=>!e.gridPrimary && e.gridCode===4),"散乱線の通過"]]){
      const b=el("sample-"+key); b.disabled=i<0;b.onclick=i<0?null:()=>inspect(i);
      b.textContent=name+(i<0?"（該当なし）":" #"+ev[i].id);
    }
  }
  function frame(now) {
    if(disposed||panel._filmState!==binding||!panel.isConnected)return;
    const s=clock.snapshot(now),i=s.i,e=ev[i];if(!e)return;
    const p=pathFor(0,i,s.f);
    if(history.seed!==e.seed) cams.forEach(c=>c.clear());
    history.observe(i,e.seed,s.f,p);
    const kept=history.phases.get(i);
    cams.forEach((camera,k)=>camera.update(i,kept===undefined?undefined:casePhase(k,i,kept),
               s.state!=="ended",k?pathFor(k,i,s.f):p,s.state==="ready"));
    detector?.update(i,kept,history,s.state!=="ended");examples(e.seed);
    write("played",history.completed.size+" / "+ev.length+" 個");
    write("retained",history.phases.size+" 本");write("scattered",history.scattered.size+" 本");
    const key=i+":"+s.state;
    if(key!==lastText){
      write("state",labels[s.state]);write("counter","シード "+e.seed+"　·　光子 #"+e.id);
      const sample=data.samples.find(d=>d.seed===e.seed);
      write("seeds","再生順 "+(i+1)+"/"+ev.length+"　·　この標本 "+sample.shown+"/"+sample.count.toLocaleString("ja-JP")+" 個");
      play.disabled=s.state==="playing";pause.disabled=s.state!=="playing";stop.disabled=s.state==="ready";
      opt.value=String(i);lastText=key;
    }
    const outcome=paired && p.complete?"なし："+e.gridOutcome+"　／　あり："+cases[1][i].gridOutcome:"";
    write("stage",s.state==="ready"?"焦点から開始":outcome||p.stage);
    const text=e.gridPrimary && p.met?"一次線":p.met?label(e)+"　｜　"+data.processes[e.process]+"　｜　"+
        (e.energy!=null?"θ "+e.theta.toFixed(1)+"°　 E′ "+e.energy.toFixed(2)+" keV":"θ・E′：対象外"):
        ("入射 "+data.incidentEnergy+" keV　｜　"+(s.state==="ready"?"再生で開始":"初回相互作用の前"));
    write("details",text);
    el("progress").style.transform="scaleX("+s.t/(ev.length*PERIOD)+")";
    if(s.state==="playing"){cancelAnimationFrame(raf);raf=requestAnimationFrame(frame);}
  }
  opt.replaceChildren(...ev.map((e,i)=>new Option("シード "+e.seed+" / #"+e.id+"　"+label(e),String(i))));
  speed.replaceChildren(...SPEEDS.map(r=>new Option(r+"倍",String(r))));
  speed.value=String(clock.snapshot(performance.now()).rate);
  const action=fn=>()=>{const now=performance.now();fn(now);frame(now);};
  function reset(){history.reset();cams.forEach(c=>c.clear());detector?.clear();}
  play.onclick=action(now=>{if(clock.snapshot(now).state==="ended")reset();clock.play(now);});
  pause.onclick=action(now=>clock.pause(now));stop.onclick=action(()=>{clock.stop();reset();});
  speed.onchange=action(now=>clock.speed(Number(speed.value),now));opt.onchange=()=>inspect(Number(opt.value));
  zoom.ontoggle=()=>{if(paired&&zoom.open)frame(performance.now());};
  function hide(){if(document.hidden && !disposed && panel._filmState===binding){clock.pause(performance.now());frame(performance.now());}}
  document.addEventListener("visibilitychange",hide);
  function redraw(){
    let layout;
    if (paired) {
      const paneWidth=Math.min(el("screen").getBoundingClientRect().width,el("screen-on").getBoundingClientRect().width);
      layout=focusedRoomLayout(Math.max(96,Math.floor(paneWidth || 400)),data.scene.bounds,data.gridGeometry);
    }
    cams.forEach((c,k)=>c.redraw([...history.phases].map(([i,f])=>[i,casePhase(k,i,f)]),layout));
    frame(performance.now());
  }
  detector?.restore(history);redraw();
  const resize=new ResizeObserver(entries=>{
    const w=entries[0].contentRect.width;if(!disposed && Math.abs(w-width)>1){width=w;redraw();}
  });
  resize.observe(el("rooms"));
  binding.dispose=()=>{disposed=true;cancelAnimationFrame(raf);resize.disconnect();
                      document.removeEventListener("visibilitychange",hide);};
  return binding.dispose;
}
