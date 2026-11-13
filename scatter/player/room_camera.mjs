// The same physical-to-screen projection serves the original room view and both grid cases.
export function roomCamera(svg,scene,ev,data,inspect,clipId) {
  let W=0,H=0,scale=1,P;
  let guideLength=0;
  const ns="http://www.w3.org/2000/svg";
  const put=(node,attrs)=>{for(const [k,v] of Object.entries(attrs))node.setAttribute(k,v);return node;};
  function add(tag,parent,attrs={},text) {
    const node=put(svg.ownerDocument.createElementNS(ns,tag),attrs);parent.append(node);
    if(text!==undefined)node.textContent=text;
    return node;
  }
  svg.replaceChildren();
  const clipPath="url(#"+clipId+")";
  const clip=add("clipPath",add("defs",svg),{id:clipId});
  const clipRect=add("rect",clip);
  const grid=add("g",svg), backdrop=add("g",svg,{"clip-path":clipPath});
  const guides=data.pairedGrid ? add("g",svg,{"aria-label":"検出器面からの仮想延長線"}) : null;
  const tracks=add("g",svg,{"clip-path":clipPath}), signs=add("g",svg,{"pointer-events":"none"});
  const trails=add("g",tracks,{"aria-label":"累積飛跡"});
  const dot=add("circle",tracks,{r:4,fill:"#284952",stroke:"white","stroke-width":1});
  const drawn=new Map();
  let highlighted=-1;
  const color=e=>e.group<0?"#435D6B":data.colors[e.group];
  const label=e=>e.gridPrimary?"一次線":e.part<0?"検出器面（相互作用なし）":data.groups[e.group]+"・"+data.parts[e.part];
  function line(parent,a,b,attrs) {
    return add("line",parent,{x1:a[0],y1:a[1],x2:b[0],y2:b[1],...attrs});
  }
  const dline=(a,b)=>"M"+a.join(",")+" L"+b.join(",");
  function redraw(phases, pairedLayout) {
    const [xl,xr,zt,sceneBottom]=scene.bounds;
    const zb=pairedLayout ? data.gridGeometry.sid : sceneBottom;
    if (pairedLayout) {
      ({width:W, height:H, scale, project:P, guideLength}=pairedLayout);
    } else {
      W=Math.max(200,Math.round(svg.getBoundingClientRect().width || 500));
      H=scene.close?Math.min(445,Math.max(310,W*.80)):Math.min(485,Math.max(350,W*1.06));
      const left=32,right=11,top=10,bottom=27;
      scale=Math.min((W-left-right)/(xr-xl),(H-top-bottom)/(zb-zt));
      const x0=left+(W-left-right-(xr-xl)*scale)/2, z0=top+(H-top-bottom-(zb-zt)*scale)/2;
      P=(x,z)=>[x0+(x-xl)*scale,z0+(z-zt)*scale];
    }
    svg.style.height=H+"px";put(svg,{viewBox:"0 0 "+W+" "+H});
    const [x0,z0]=P(xl,zt), w=(xr-xl)*scale, h=(zb-zt)*scale;
    const proj=(x,z)=>P(x,z).join(",");
    // Allow the outlines of terminal markers to straddle the calculated endpoint.
    put(clipRect,{x:x0,y:z0,width:w,height:h+(pairedLayout?5:0)});
    grid.replaceChildren();backdrop.replaceChildren();signs.replaceChildren();
    const common={fill:"#516872","font-size":11};
    const gridStep=scene.close?5:20;
    for(let z=Math.ceil(zt/gridStep)*gridStep;z<=zb;z+=gridStep){
      const a=P(xl,z),b=P(xr,z);line(grid,a,b,{stroke:"#dfe7e9"});
      add("text",grid,{x:a[0]-4,y:a[1]+4,"text-anchor":"end",...common},z);
    }
    for(let x=Math.ceil(xl/gridStep)*gridStep;x<=xr;x+=gridStep){
      const a=P(x,zt),b=P(x,zb);line(grid,a,b,{stroke:"#e7edef"});
      add("text",grid,{x:b[0],y:pairedLayout?z0-5:b[1]+14,"text-anchor":"middle",...common},x);
    }
    add("text",grid,{x:5,y:13,...common},"z (cm)");
    add("text",grid,{x:Math.min(W-1,x0+w+32),y:pairedLayout?13:H-2,"text-anchor":"end",...common},"x (cm)");
    if (pairedLayout) {
      add("rect",grid,{class:"virtual-band",x:0,y:pairedLayout.detectorY,width:W,
                      height:H-pairedLayout.detectorY,fill:"#e8f3f2"});
      add("text",signs,{x:W/2,y:H-8,"text-anchor":"middle",fill:"#285e60","font-size":12},
          "仮想延長領域");
    }
    add("polygon",backdrop,{points:scene.beam.map(p=>proj(...p)).join(" "),fill:"#eaf1f4",stroke:"#a9bec5",
                           "stroke-dasharray":"3 3"});
    for(const s of scene.shapes){
      const style={fill:s.fillcolor,stroke:s.line.color,"stroke-width":s.line.width??1};
      if(s.type==="rect"){
        const a=P(s.x0,s.y0),b=P(s.x1,s.y1);
        add("rect",backdrop,{x:a[0],y:a[1],width:b[0]-a[0],height:Math.max(.3,b[1]-a[1]),...style});
      }else if(s.type==="path"){
        const coords=s.path.match(/-?\d+(?:\.\d+)?(?:e[+-]?\d+)?/gi).map(Number), points=[];
        for(let i=0;i<coords.length;i+=2)points.push(proj(coords[i],coords[i+1]));
        add("polygon",backdrop,{points:points.join(" "),...style});
      }
    }
    const origin=P(0,0);
    add("circle",backdrop,{cx:origin[0],cy:origin[1],r:2.8,fill:"#193444"});
    if (pairedLayout) {
      const half=data.gridGeometry.halfWidth;
      line(backdrop,P(-half,zb),P(half,zb),{class:"detector-plane",stroke:"#254952","stroke-width":2});
    }
    for(const l of scene.labels){
      const detectorLabel=pairedLayout && l.text==="検出器面";
      const [x,y]=detectorLabel ? [4,pairedLayout.detectorY-6] : P(l.x,l.z);
      add("text",signs,{x,y:y+3.6,"font-size":scene.close?12:10.8,"text-anchor":l.anchor==="right"?"end":"start",
          fill:"#304955",stroke:"#f8fafb","stroke-width":3,"paint-order":"stroke"},l.text);
    }
    clearDrawing();
    for (const [index,phase] of phases) drawPhoton(index,phase);
  }
  function mark(parent,e,i){
    const [x,y]=P(e.end[0],e.end[2]),c=color(e),g=add("g",parent,{class:"endpoint",transform:"translate("+x+" "+y+")"});
    const desc="シード "+e.seed+"・光子 #"+e.id+"・"+label(e)+"・"+data.processes[e.process];
    if(e.part>=0){
      put(g,{role:"button","aria-label":desc,tabindex:"0"});
      g.style.cursor="pointer";g.onclick=()=>inspect(i);
      g.onkeydown=ev=>{if(ev.key==="Enter"||ev.key===" "){ev.preventDefault();inspect(i);}};
    }
    add("title",g,{},desc);
    add("circle",g,{class:"halo",r:9,fill:c,opacity:.14});
    add("circle",g,{r:11,fill:"transparent"});
    if(e.gridPrimary) return g;
    const style={fill:c,stroke:"white","stroke-width":1};
    if(e.process===2)add("path",g,{d:"M-4,-4L4,4 M4,-4L-4,4",fill:"none",stroke:c,"stroke-width":2.6});
    else if(e.process===3)add("path",g,{d:"M0,-5L5,0L0,5L-5,0Z",fill:"white",stroke:c,"stroke-width":2});
    else if(e.process===0)add("circle",g,{r:4,fill:"white",stroke:c,"stroke-width":1.7});
    else if(e.group===0)add("circle",g,{r:4.7,...style});
    else if(e.group===1)add("rect",g,{x:-4.2,y:-4.2,width:8.4,height:8.4,...style});
    else if(e.group===2)add("path",g,{d:"M0,-5.7L5.7,0L0,5.7L-5.7,0Z",...style});
    else add("path",g,{d:"M0,-5.6L5,4.5L-5,4.5Z",...style});
    return g;
  }
  function clearDrawing() {
    trails.replaceChildren();
    guides?.replaceChildren();
    drawn.clear();
    highlighted=-1;
  }

  function drawPhoton(i,phase) {
    let track=drawn.get(i);
    if (track?.phase === phase) return;
    const e=ev[i], path=pathAt(e,phase,data.length);
    if (!track) {
      const group=add("g",trails,{class:"photon","data-seed":e.seed,"data-photon":e.id});
      track={group,primary:add("path",group,{class:"incident"}),at:P(e.end[0],e.end[2])};
      drawn.set(i,track);
    }
    track.phase=phase;
    put(track.primary,{d:dline(P(0,0),P(path.inc[0],path.inc[2]))});
    if (path.tip) {
      if (!track.secondary) {
        const c=color(e);
        track.secondary=add("path",track.group,{class:"outgoing",stroke:c});
        track.head=add("path",track.group,{class:"arrowhead",fill:c});
        if (track.marker) track.group.append(track.marker);
      }
      const end=P(path.tip[0],path.tip[2]);
      const dx=end[0]-track.at[0],dz=end[1]-track.at[1],length=Math.hypot(dx,dz);
      put(track.secondary,{d:dline(track.at,end)});
      if (length>.01) {
        const ux=dx/length,uz=dz/length,h=Math.min(length,5+.035*e.energy),w=.45*h;
        const x=end[0]-h*ux,y=end[1]-h*uz;
        put(track.head,{d:"M"+end.join(",")+" L"+[x-w*uz,y+w*ux].join(",")+
          " L"+[x+w*uz,y-w*ux].join(",")+" Z"});
      }
    }
    if (path.met && !track.marker) track.marker=mark(track.group,e,i);
    if (e.gridOutcome && path.complete && !track.terminal && [4,5,6].includes(e.gridCode)) {
      const end=e.exit||e.end;
      const [x,y]=P(end[0],end[2]);
      if (guides) {
        const tip=directionGuide(e,[x,y],guideLength);
        if (tip) {
          const ink=e.gridPrimary?"#536d79":color(e);
          track.guide=add("line",guides,{class:"virtual-ray",x1:x,y1:y,x2:tip[0],y2:tip[1],
              stroke:ink,"stroke-dasharray":"5 3","data-seed":e.seed,"data-photon":e.id});
          if (i===highlighted) track.guide.classList.add("active");
          add("title",track.guide,{},"#"+e.id+"　"+label(e)+"　検出器面での方向");
        }
      }
      const g=add("g",track.group,{class:"grid-terminal","data-outcome":e.gridOutcome,
                                  transform:"translate("+x+" "+y+")"});
      if(e.gridCode===5) add("path",g,{d:"M-3,-3L3,3 M-3,3L3,-3",stroke:"#a63832","stroke-width":2});
      else if(e.gridCode===4) add("circle",g,{r:3,fill:"white",stroke:"#146c68","stroke-width":1.6});
      else add("path",g,{d:"M-3,-3L3,0L-3,3",fill:"none",stroke:"#526777","stroke-width":1.5});
      add("title",g,{},"#"+e.id+" "+e.gridOutcome);
      track.terminal=g;
    }
  }

  function setHighlighted(index) {
    if (highlighted===index) return;
    drawn.get(highlighted)?.group.classList.remove("active");
    drawn.get(highlighted)?.guide?.classList.remove("active");
    highlighted=index;
    const track=drawn.get(index);
    if (track) {
      track.group.classList.add("active");
      track.guide?.classList.add("active");
      trails.append(track.group);
    }
  }
  function update(i,phase,active,nowPath,ready) {
    if (phase!==undefined) drawPhoton(i,phase);
    setHighlighted(phase===undefined || !active ? -1 : i);
    const pos=P(nowPath.inc[0],nowPath.inc[2]);
    put(dot,{cx:pos[0],cy:pos[1],visibility:nowPath.met||ready?"hidden":"visible"});
  }
  return {redraw,clear:clearDrawing,update};
}
