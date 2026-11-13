"""Build a common two-case comparison from one set of photon IDs."""
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .grid import (GAP, LEAD, PITCH, HALF_WIDTH, KINDS, OUTCOMES, LEAD_HIT,
                   PASS, SIDE, off_endpoints, project_rays)
from .model import NO_HIT, COMPTON, SID, GROUP
from .playback import scene, tracks_payload
from .plots import COLORS


def selection_projection(frame, events, grid):
    position = np.asarray([e["end"] for e in events], dtype=float)
    incident = frame[["incident_"+axis for axis in "xyz"]].to_numpy()
    outgoing = frame[["outgoing_"+axis for axis in "xyz"]].to_numpy()
    process = np.asarray([e["process"] for e in events])
    return project_rays(position, incident, outgoing, process, grid)


def projected_events(selected, pair, enabled, events=None):
    """Change drawing endpoints on copies only. Save the actual first collision separately."""
    source = tracks_payload(selected) if events is None else events
    indices = np.arange(len(source))
    if enabled:
        ex, ez, codes = pair.end_x, pair.end_z, pair.with_grid
    else:
        ex, ez = off_endpoints(pair, indices)
        codes = pair.without
    result = []
    for i, photon in enumerate(source):
        e = photon.copy()
        code = int(codes[i])
        e.update(gridOutcome=OUTCOMES[code], gridCode=code, gridPrimary=bool(pair.primary[i]))
        if pair.primary[i]:
            # Collisions at/beyond the virtual grid must not be drawn upstream.
            z = e["end"][2]
            slope = np.asarray(e["end"])/z
            stop = ez[i] if pair.entered[i] else pair.geometry.top
            end = slope*stop
            if pair.entered[i]:
                end[0],end[2]=ex[i],ez[i]
            e.update(process=NO_HIT, group=-1, part=-1, end=end.tolist(),
                     direction=None, theta=None, energy=None)
        elif photon["process"] == COMPTON:
            if pair.entered[i]:
                # Both transverse coordinates follow the original 3D direction.
                distance = (ez[i]-e["end"][2])/e["direction"][2]
                e["exit"] = (np.asarray(e["end"])+distance*np.asarray(e["direction"])).tolist()
                e["exit"][0], e["exit"][2] = float(ex[i]), float(ez[i])
            else:
                # A nonincident scattered ray is shown only in the room display
                # window, with an upper limit of 18 cm and no foil/detector claim.
                length = 18.
                if e["direction"][2] > 0:
                    length = min(length, (pair.geometry.top-e["end"][2])/e["direction"][2])
                e["exit"] = (np.asarray(e["end"])+length*np.asarray(e["direction"])).tolist()
        if pair.entered[i]:
            if pair.primary[i]:
                origin = np.zeros(3)
                ray = np.asarray(photon["end"])
            else:
                origin = np.asarray(photon["end"])
                ray = np.asarray(photon["direction"])
            # The two camera views share these points on the very same ray.
            top = pair.geometry.top
            near = max(origin[2], top-.22*pair.geometry.height)
            entry = origin + (top-origin[2])/ray[2]*ray
            entry[0],entry[2] = pair.entry_x[i],top
            e["entry"] = entry.tolist()
            e["approach"] = (origin + (near-origin[2])/ray[2]*ray).tolist()
        result.append(e)
    return result


def grid_scene(run, grid, enabled):
    view = scene(run, False)
    view["bounds"][3] = grid.sid+5.
    view["beam"] = [(x*grid.sid/SID if z else x, grid.sid if z else z) for x,z in view["beam"]]
    for shape in view["shapes"]:
        if shape.get("type") == "rect" and shape.get("y0") == SID:
            shape["y0"], shape["y1"] = grid.sid, grid.sid+.55
    for label in view["labels"]:
        if label["text"] == "検出器面":
            label["z"] = grid.sid+2.4
    if enabled:
        view["shapes"].append(dict(type="rect", x0=-HALF_WIDTH, x1=HALF_WIDTH,
            y0=grid.top, y1=grid.sid, fillcolor="#ba886c", line=dict(color="#a86948",width=1)))
        view["labels"].append(dict(x=22.8,z=grid.top-.6,text="グリッド",anchor="left"))
    if grid.sid < 98:
        for item in view["labels"]:
            if item["text"]=="撮影台":
                item.update(x=-25.7,z=93.7,anchor="left")
    return view


def default_detail_id(pair):
    # Prefer a hit inside a foil wall (rather than at its front surface), with
    # both paths and several adjacent foils legible in the same physical scale.
    depth = (pair.end_z-pair.geometry.top)/pair.geometry.height
    oblique = np.abs(pair.clear_x-pair.entry_x)
    cut = pair.scattered & (pair.with_grid == LEAD_HIT)
    for mask in (cut & (depth>.2) & (depth<.85) & (oblique>GAP) & (oblique<4*GAP),
                 cut,
                 pair.primary & (pair.with_grid == PASS), pair.entered):
        hits=np.flatnonzero(mask)
        if hits.size:
            return int(hits[0])+1
    return 1


def comparison_figure(run, pair, index):
    """Magnify the same few real strips and the same ray in both panes (axes in mm)."""
    grid=pair.geometry
    entered=bool(pair.entered[index])
    center=float(pair.entry_x[index]) if entered else HALF_WIDTH*.7
    half=max(.085, grid.height*.65)
    x0,x1 = center-half,center+half
    top,bottom = grid.top,grid.sid
    z0,z1 = top-grid.height*.22,bottom+grid.height*.14
    offx,offz=off_endpoints(pair,np.array([index]))
    if entered:
        direction=run.incident[index] if pair.primary[index] else run.outgoing[index]
        slope=direction[0]/direction[2]
        startz=max(z0, 0 if pair.primary[index] else run.position[index,2])
        initialx=center+(startz-top)*slope
        anchors=(initialx,center,offx[0],pair.end_x[index])
        x0=min(x0,min(anchors)-GAP)
        x1=max(x1,max(anchors)+GAP)
    # At the physical side edge clip the view to the actual 44 cm-wide stack.
    # Plotly clips the oblique foil polygons and the ray in that common window.
    x0,x1=max(x0,-HALF_WIDTH),min(x1,HALF_WIDTH)
    ref=go.Figure(make_subplots(rows=1,cols=2,subplot_titles=("グリッドなし","グリッドあり"),
                                horizontal_spacing=.11))
    # Express horizontal values relative to the entry for readable precision.
    def xy(x,z):
        return ((np.asarray(x)-center)*10,(np.asarray(z)-top)*10)
    slit_range = [x/grid.scale(z) for x in (x0,x1) for z in (top,bottom)]
    strips = range(int(np.floor(min(slit_range)/PITCH))-1, int(np.ceil(max(slit_range)/PITCH))+1)
    px,pz=[],[]
    for k in strips:
        lt,rt=grid.foil_edges(k,top); lb,rb=grid.foil_edges(k,bottom)
        xx,zz=xy([lt,rt,rb,lb,lt],[top,top,bottom,bottom,top])
        px.extend([*xx,None]);pz.extend([*zz,None])
    ref.add_trace(go.Scatter(x=px,y=pz,fill="toself",fillcolor="#4d626d",mode="lines",
                             line=dict(color="#4d626d",width=.6),hoverinfo="skip",name="鉛箔"),row=1,col=2)
    for col in (1,2):
        ref.add_hline(y=grid.height*10,row=1,col=col,line_color="#21576c",line_width=2)
        if not entered:
            continue
        finalz=float(offz[0]) if col==1 else pair.end_z[index]
        finalx=float(offx[0]) if col==1 else pair.end_x[index]
        xx,zz=xy([initialx,center,finalx],[startz,top,finalz])
        ray_color=COLORS[GROUP[run.part[index]]] if pair.scattered[index] else "#314f5e"
        ref.add_trace(go.Scatter(x=xx,y=zz,mode="lines",line=dict(color=ray_color,width=3),
                                 name=KINDS[1 if pair.primary[index] else 2],hoverinfo="skip"),row=1,col=col)
        code=pair.without[index] if col==1 else pair.with_grid[index]
        symbol={LEAD_HIT:"x",SIDE:"triangle-right",PASS:"circle-open"}[code]
        ref.add_trace(go.Scatter(x=[xx[-1]],y=[zz[-1]],mode="markers",
            marker=dict(symbol=symbol,color="#a63832" if code==LEAD_HIT else ray_color,size=10),
            hovertemplate=OUTCOMES[code]+"<extra></extra>",name=OUTCOMES[code]),row=1,col=col)
    ref.update_xaxes(range=[(x0-center)*10,(x1-center)*10],title_text="局所 x (mm)",fixedrange=True,
                     constrain="domain")
    for col,axis in ((1,"x"),(2,"x2")):
        ref.update_yaxes(range=[(z1-top)*10,(z0-top)*10],scaleanchor=axis,scaleratio=1,
                         constrain="domain",fixedrange=True,row=1,col=col)
    ref.update_yaxes(title_text="入口から (mm)",row=1,col=1)
    ref.update_layout(template="plotly_white",height=310,showlegend=False,margin=dict(l=18,r=12,t=42,b=18),
                      font=dict(size=12,color="#193444"))
    return ref
