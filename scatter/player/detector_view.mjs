// Detector views use one common x scale, one common local camera and the existing phase history.
function detectorViews(panel, cases, geometry, pathFor) {
  const q=(name)=>panel.querySelector('[data-c="'+name+'"]');
  const ns="http://www.w3.org/2000/svg";
  function add(root,tag,attrs={},text) {
    const node=document.createElementNS(ns,tag);
    for(const [k,v] of Object.entries(attrs)) node.setAttribute(k,v);
    if(text!==undefined) node.textContent=text;
    root.append(node);return node;
  }
  function line(root,a,b,attrs) {return add(root,"line",{x1:a[0],y1:a[1],x2:b[0],y2:b[1],...attrs});}
  const tint=e=>RAY_INK[e.gridPrimary?"primary":"scatter"];
  function guide(root,e,a,size) {
    const b=directionGuide(e,a,size);
    if (!b) return;
    const dx=(b[0]-a[0])/size,dz=(b[1]-a[1])/size, h=4.2, w=2.5;
    line(root,a,b,{stroke:tint(e),"stroke-width":1.8,"stroke-dasharray":"4 3"});
    add(root,"path",{d:"M"+[b[0]-h*dx-w*dz,b[1]-h*dz+w*dx]+"L"+b+"L"+
         [b[0]-h*dx+w*dz,b[1]-h*dz-w*dx],stroke:tint(e),"stroke-width":1.6,fill:"none"});
  }
  function endpoint(root,e,xy,r) {
    if (e.gridCode===5) return add(root,"path",{d:"M-"+r+",-"+r+"L"+r+","+r+" M-"+r+","+r+"L"+r+",-"+r,stroke:"#ad3039",
                                  "stroke-width":2.6,transform:"translate("+xy+")"});
    if (e.gridCode===6) return add(root,"path",{d:"M-3,-4L3,0L-3,4",stroke:"#4b5761",fill:"none",
                                  "stroke-width":2,transform:"translate("+xy+")"});
    return e.gridPrimary ? add(root,"circle",{cx:xy[0],cy:xy[1],r,stroke:tint(e),fill:"white","stroke-width":1.8}):
      add(root,"path",{d:"M0,-"+r+"L"+r+",0L0,"+r+"L-"+r+",0Z",fill:"white",stroke:tint(e),
                      "stroke-width":1.8,transform:"translate("+xy+")"});
  }
  const boundary=(root,y,x1,x2)=>line(root,[x1,y],[x2,y],{stroke:"#466771","stroke-width":1.7});
  const g=geometry, zoom=q("down-zoom"), note=q("local-note"), overviewHist=[], zoomLayers=[];
  const firstInSeed=new Map();
  cases[0].forEach((e,i)=>{if(e.entry&&!firstInSeed.has(e.seed))firstInSeed.set(e.seed,i);});
  let lastEntered=-1, preview=-1, highlighted=-1, lastNote="", activeSeed=null;
  const overviewX=x=>170+119*x/g.halfWidth;
  cases.forEach((_,side)=>{
    const svg=q("landing-"+side);
    svg.replaceChildren();
    add(svg,"rect",{x:0,y:38,width:340,height:64,fill:"#edf5f4"});
    add(svg,"text",{x:50,y:10,"font-size":10,fill:"#526670"},"× 鉛箔接触の x");
    boundary(svg,38,overviewX(-g.halfWidth),overviewX(g.halfWidth));
    for (const x of [-g.halfWidth,0,g.halfWidth]) {
      const col=overviewX(x);
      line(svg,[col,32],[col,38],{stroke:"#49616a"});
      add(svg,"text",{x:col,y:26,"text-anchor":"middle",fill:"#3b5661","font-size":12},
          (x>0?"+":"")+x+" cm");
    }
    add(svg,"text",{x:170,y:99,"text-anchor":"middle",fill:"#45626a","font-size":11},"到達時の向き（方向ガイド）");
    overviewHist.push({layer:add(svg,"g",{"aria-label":"累積到達点"}),hits:add(svg,"g",{"aria-label":"鉛箔吸収位置の横座標"}),
                       seen:new Map(),blocked:new Set(),counts:[0,0],label:q("land-count-"+side),
                       roomCount:q("room-arrivals-"+side)});
  });
  function sumLabel(obj) {
    obj.roomCount.textContent="到達 "+(obj.counts[0]+obj.counts[1])+" 個";
    obj.label.textContent="到達 "+(obj.counts[0]+obj.counts[1])+" 個　｜　一次 "+obj.counts[0]+"・散乱 "+obj.counts[1]+"　／　鉛箔吸収 "+obj.blocked.size+" 個";
  }
  function observeArrival(side,i,phase) {
    const h=overviewHist[side], e=cases[side][i];
    if(e.gridCode===5 && !h.blocked.has(i) && pathFor(side,i,phase).complete){
      // This strip reports x only. The local section below shows the true x AND z contact.
      const at=e.exit||e.end, hit=add(h.hits,"g",{"data-photon":e.id,"data-hit-x":at[0],"data-hit-z":at[2]});
      endpoint(hit,e,[overviewX(at[0]),15],2.2);
      add(hit,"title",{},"#"+e.id+"　鉛箔との最初の接触：x="+at[0].toFixed(4)+" cm、z="+at[2].toFixed(4)+" cm");
      h.blocked.add(i);sumLabel(h);
    }
    if (e.gridCode!==4 || h.seen.has(i) || !pathFor(side,i,phase).complete) return;
    const terminal=e.exit||e.end, at=[overviewX(terminal[0]),38];
    const ray=add(h.layer,"g",{"class":"arrival","data-seed":e.seed,"data-photon":e.id,
        "data-kind":e.gridPrimary?"primary":"scatter","data-x-cm":terminal[0]});
    add(ray,"title",{},"#"+e.id+"　x="+terminal[0].toFixed(4)+" cm　"+
        (Math.atan2(...e.xzDirection)*180/Math.PI).toFixed(1)+"°");
    guide(ray,e,at,48);endpoint(ray,e,at,2.9);
    h.counts[e.gridPrimary?0:1]++;h.seen.set(i,ray);sumLabel(h);
  }
  function mark(i) {
    if(i===highlighted)return;
    for (const h of overviewHist) {
      h.seen.get(highlighted)?.classList.remove("active");
      const current=h.seen.get(i);
      if(current){current.classList.add("active");h.layer.append(current);}
    }
    highlighted=i;
  }
  function clear() {
    for(const h of overviewHist){h.layer.replaceChildren();h.seen.clear();h.hits.replaceChildren();h.blocked.clear();h.counts=[0,0];sumLabel(h);}
    lastEntered=preview=highlighted=-1; activeSeed=null; lastNote="";zoomLayers.length=0;
  }
  function prepare(i) {
    preview=i;zoomLayers.length=0;
    const camera=i<0?null:localCamera(g,cases[0][i],cases[1][i]);
    cases.forEach((events,side)=>{
      const svg=q("local-"+side);svg.replaceChildren();
      if(!camera) {
        add(svg,"text",{x:170,y:100,"text-anchor":"middle",fill:"#47616b","font-size":13},"この標本には入口を通る光子がありません");
        return;
      }
      const e=events[i], p=camera.point, top=p(camera.left,g.top), end=p(camera.right,g.sid);
      add(svg,"rect",{x:0,y:end[1],width:340,height:75,fill:"#edf5f4"});
      if(side===1) {
        const s=1-g.height/g.focus;
        const leftBound=Math.floor(Math.min(camera.left,camera.left/s)/g.pitch)-1;
        const rightBound=Math.ceil(Math.max(camera.right,camera.right/s)/g.pitch)+1;
        const clipId="vxsl-slit-window";
        const clip=add(add(svg,"defs"),"clipPath",{id:clipId});
        add(clip,"rect",{x:top[0],y:top[1],width:end[0]-top[0],height:end[1]-top[1]});
        if (g.pitch*camera.scale>=1) {
          const strips=[];
          for(let k=leftBound;k<=rightBound;k++) {
            const mid=(k+.5)*g.pitch,a=mid-g.foil/2,b=mid+g.foil/2;
            strips.push("M"+p(a*s,g.top)+"L"+p(b*s,g.top)+"L"+p(b,g.sid)+"L"+p(a,g.sid)+"Z");
          }
          add(svg,"path",{d:strips.join(" "),fill:"#596b79","clip-path":"url(#"+clipId+")"});
        } else {
          add(svg,"rect",{x:top[0],y:top[1],width:end[0]-top[0],height:end[1]-top[1],fill:"#d2d9dc"});
          add(svg,"text",{x:170,y:top[1]-4,"text-anchor":"middle","font-size":10},"この倍率では箔を分離できません");
        }
      }
      line(svg,[top[0],top[1]],[end[0],top[1]],{stroke:"#a2b3b8","stroke-dasharray":"3 3"});
      boundary(svg,end[1],top[0],end[0]);
      const bar=.1*camera.scale; // 1 mm in the solid, physical section (x and z have the same scale).
      line(svg,[12,16],[12+bar,16],{stroke:"#3f5662","stroke-width":2});
      add(svg,"text",{x:16+bar,y:20,"font-size":11,fill:"#3f5662"},"1 mm");
      const a=p(e.approach[0],e.approach[2]), final=e.exit||e.end, b=p(final[0],final[2]);
      const segment=line(svg,a,a,{stroke:tint(e),"stroke-width":2.8,visibility:"hidden"});
      const dot=add(svg,"circle",{r:3,cx:a[0],cy:a[1],fill:tint(e),visibility:"hidden"});
      const mark=add(svg,"g",{visibility:"hidden","data-code":e.gridCode,"data-photon":e.id});
      if(e.gridCode===4) guide(mark,e,b,55);
      endpoint(mark,e,b,4.4);
      zoomLayers.push({segment,dot,mark,p});
    });
  }
  function local(i,index,phase,visible) {
    if(!zoom.open)return;
    if(index!==preview || (index<0 && !q("local-0").childElementCount))prepare(index);
    let message="入口を通る光子がありません。";
    if(index>=0) {
      const example=cases[0][index];
      const status=(side)=>cases[side][index].gridOutcome;
      const reached=visible && pathFor(0,index,phase).complete;
      const offEnd=example.exit||example.end, on=cases[1][index], onEnd=on.exit||on.end;
      const prefix=(visible ? (index===i?"光子 ":"直近の入射光子 ") : "入口の拡大位置：光子 ")+"#"+example.id+
                   "　·　"+(example.gridPrimary?"一次線":"散乱線")+"　·　入口 x = "+example.entry[0].toFixed(3)+" cm";
      message=prefix+(reached?"　｜　なし："+status(0)+" x="+offEnd[0].toFixed(3)+" cm　／　あり："+status(1)+" x="+onEnd[0].toFixed(3)+" cm":
                          (visible?"":"　｜　到着すると飛跡を表示"));
      zoomLayers.forEach(({segment,dot,mark,p},side)=>{
        const e=cases[side][index], path=pathFor(side,index,phase), a=path.gridPoint;
        const show=visible && a && a[2]>=e.approach[2]-1e-12;
        segment.setAttribute("visibility",show?"visible":"hidden");
        dot.setAttribute("visibility",show&&!path.complete?"visible":"hidden");
        mark.setAttribute("visibility",visible&&path.complete?"visible":"hidden");
        if(show) {
          const [x,y]=p(a[0],a[2]);segment.setAttribute("x2",x);segment.setAttribute("y2",y);
          dot.setAttribute("cx",x);dot.setAttribute("cy",y);
        }
      });
    }
    if(lastNote!==message){lastNote=message;note.textContent=message;}
  }
  function update(i,phase,history,active) {
    const e=cases[0][i];
    if(e.seed!==activeSeed){clear();activeSeed=e.seed;}
    if(phase!==undefined){
      for(let side=0;side<2;side++)observeArrival(side,i,phase);
      if(e.entry)lastEntered=i;
    }
    mark(active && phase!==undefined?i:-1);
    let index=e.entry?i:lastEntered;
    if(index<0)index=firstInSeed.get(e.seed)??-1;
    const kept=history.phases.get(index);
    local(i,index,kept??0,kept!==undefined);
  }
  function restore(history) {
    clear();activeSeed=history.seed;
    for(const [i,phase] of history.phases){
      for(let side=0;side<2;side++)observeArrival(side,i,phase);
      if(cases[0][i].entry)lastEntered=i;
    }
  }
  return {clear,update,restore};
}
