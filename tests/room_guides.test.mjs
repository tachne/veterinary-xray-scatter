import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

// Streamlit registers these assets in one ES module. Link the same production
// functions in Node, with just the SVG document interface the camera consumes.
const read = name => readFile(new URL('../scatter/player/'+name, import.meta.url), 'utf8');
const sources = await Promise.all(['clock.mjs','history.mjs','paired_ray.mjs','room_camera.mjs'].map(read));
const {roomCamera,focusedRoomLayout,TrackHistory,timeline,pathAt} = await import(
  'data:text/javascript;base64,'+Buffer.from(sources.join('\n')).toString('base64')
);

class SvgNode {
  constructor(tag, doc) {
    this.tag=tag;
    this.ownerDocument=doc;
    this.children=[];
    this.attrs={};
    this.style={};
    this.classList=new Set();
    this.classList.remove=name=>this.classList.delete(name);
  }
  setAttribute(key,value) {this.attrs[key]=String(value);}
  append(node) {
    if(node.parent) node.parent.children=node.parent.children.filter(child=>child!==node);
    node.parent=this;
    this.children.push(node);
  }
  replaceChildren() {this.children=[];}
  getBoundingClientRect() {return {width:320};}
  *descendants() {
    for(const child of this.children) {yield child;yield* child.descendants();}
  }
}

const grid={sid:100,height:.16,top:99.84,focus:100,halfWidth:22};
const bounds=[-34,34,-7,105];
const scene={bounds,beam:[[0,0],[-12,100],[12,100]],shapes:[],labels:[],close:false};
const inks=['#246AA1','#187452','#B65412','#7854A0'];
const base={id:1,seed:42,gridPrimary:true,end:[10,0,100],entry:[9.984,0,99.84],approach:[9.98,0,99.8],
            direction:null,xzDirection:[.1,1],process:0,group:-1,part:-1,gridCode:4,gridOutcome:'検出器面に到達'};
const scatter={...base,id:2,gridPrimary:false,end:[4,0,80],entry:[-.96,0,99.84],approach:[-.95,0,99.8],
               exit:[-1,0,100],direction:[-.25,0,1],xzDirection:[-.25,1],group:0,part:1,process:1,energy:71};
const stopped={...scatter,gridCode:5,gridOutcome:'鉛箔で吸収',exit:[-.975,0,99.9]};

function makeRoom(events, width=320, paired=true) {
  const doc={createElementNS:(_ns,name)=>new SvgNode(name,doc)};
  const svg=new SvgNode('svg',doc);
  const data={pairedGrid:paired,gridGeometry:grid,length:18,colors:inks,groups:['被写体'],parts:['空気','被写体'],processes:['無相互作用','コンプトン']};
  const camera=roomCamera(svg,scene,events,data,()=>{},'test-clip');
  const layout=focusedRoomLayout(width,bounds,grid);
  camera.redraw([],paired?layout:undefined);
  const nodes=()=>[...svg.descendants()];
  const guides=()=>nodes().filter(n=>n.attrs.class==='virtual-ray');
  const draw=(i,f)=>camera.update(i,f,true,pathAt(events[i],f,18),false);
  return {camera,layout,nodes,guides,draw};
}
const near=(a,b,tol=1e-9)=>assert.ok(Math.abs(a-b)<tol,a+' differs from '+b);

for(const sid of [96,100,180]) {
  test('virtual area and both detector edges fit on narrow and large screens at SID '+sid,()=>{
    for(const width of [96,150,223,320,540,750]) {
      const g={...grid,sid}, p=focusedRoomLayout(width,[-34,34,-7,sid+5],g);
      const [xLeft,yPlane]=p.project(-22,sid), [xRight]=p.project(22,sid);
      near(p.project(1,sid)[0]-p.project(0,sid)[0],p.project(0,sid)[1]-p.project(0,sid-1)[1]);
      assert.ok(xLeft-p.guideLength>0 && xRight+p.guideLength<width);
      assert.ok(yPlane+p.guideLength<p.height);
      const room=makeRoom([base],width);
      const band=room.nodes().find(n=>n.attrs.class==='virtual-band');
      near(+band.attrs.y,room.layout.detectorY);
      assert.ok(+band.attrs.height>room.layout.guideLength);
    }
  });
}

test('a guide starts at the measured endpoint, uses the saved direction and the upstream colour only after PASS',()=>{
  const events=[base,scatter];const room=makeRoom(events);
  for(const [i,e] of events.entries()) {
    room.draw(i,.90);
    assert.equal(room.guides().length,i);
    room.draw(i,1);
    const line=room.guides()[i], a=line.attrs,at=e.exit||e.end,[x,y]=room.layout.project(at[0],at[2]);
    near(+a.x1,x);near(+a.y1,y);
    const dx=+a.x2-x,dy=+a.y2-y;
    near(dx*e.xzDirection[1],dy*e.xzDirection[0]);assert.ok(dy>0);
    near(Math.hypot(dx,dy),room.layout.guideLength);
    assert.equal(a.stroke,i?inks[0]:'#536d79');
    assert.equal(a['data-photon'],String(e.id));assert.match(a['stroke-dasharray'],/\d+ \d+/);
    room.draw(i,1);
    assert.equal(room.guides().length,i+1);
  }
  assert.equal(room.nodes().filter(n=>n.attrs.class==='incident').length,2);
});

test('lead, side exit, missed and unresolved rays have no room guide; lead contact remains a solid endpoint',()=>{
  const side={...stopped,gridCode:6,gridOutcome:'側方退出',exit:[22,0,99.88]};
  const events=[stopped,side,...[0,1,2,3].map(code=>({...base,entry:undefined,xzDirection:undefined,gridCode:code}))];
  const room=makeRoom(events);
  events.forEach((_,i)=>room.draw(i,1));
  assert.equal(room.guides().length,0);
  const contact=room.nodes().find(n=>n.attrs['data-outcome']==='鉛箔で吸収');
  const [x,z]=room.layout.project(stopped.exit[0],stopped.exit[2]);
  assert.equal(contact.attrs.transform,'translate('+x+' '+z+')');
});

test('paired 400-photon playback at 16x keeps each side’s actual guides through pause, resize and reset',()=>{
  const offEvents=Array.from({length:400},(_,i)=>({...((i%3)?scatter:base),id:i+1}));
  const onEvents=offEvents.map((e,i)=>i%3?{...stopped,id:i+1}:e);
  const off=makeRoom(offEvents),on=makeRoom(onEvents),history=new TrackHistory();
  const clock=timeline(400,{showEveryPhoton:true});clock.speed(16,0);clock.play(0);
  let time=0,s;
  for(let k=0;k<5000;k++) {
    s=clock.snapshot(time);
    const offPath=pathAt(offEvents[s.i],s.f,18);
    history.observe(s.i,42,s.f,offPath);
    const phase=history.phases.get(s.i);
    if(phase!==undefined){off.draw(s.i,phase);on.draw(s.i,phase);}
    if(k===500){
      const before=off.guides().map(n=>n.attrs['data-photon']);
      clock.pause(time);time+=500;
      assert.equal(clock.snapshot(time).state,'paused');
      off.camera.redraw(history.phases,focusedRoomLayout(223,bounds,grid));
      assert.deepEqual(off.guides().map(n=>n.attrs['data-photon']),before);
      clock.play(time);
    }
    if(s.state==='ended')break;
    time+=17;
  }
  assert.equal(s.state,'ended');
  assert.deepEqual(off.guides().map(n=>+n.attrs['data-photon']),offEvents.map(e=>e.id));
  assert.deepEqual(on.guides().map(n=>+n.attrs['data-photon']),onEvents.filter(e=>e.gridCode===4).map(e=>e.id));
  assert.equal(on.nodes().filter(n=>n.attrs.class==='incident').length,400);
  const other=makeRoom([base]);other.draw(0,1);
  on.camera.clear();off.camera.clear();
  assert.equal(off.guides().length+on.guides().length,0);assert.equal(other.guides().length,1);
});

test('room used outside the focused-grid tab keeps its original calculation area and paths',()=>{
  const legacy={...scatter,entry:undefined,gridCode:undefined,gridOutcome:undefined,xzDirection:undefined};
  const camera=makeRoom([legacy],320,false);
  camera.draw(0,1);
  assert.ok(camera.nodes().some(n=>n.attrs.class==='outgoing'));
  assert.ok(!camera.nodes().some(n=>['virtual-band','virtual-ray'].includes(n.attrs.class)));
});
