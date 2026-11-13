import numpy as np
import plotly.graph_objects as go

from .model import GROUPS, PARTS, SID, TABLE_TOP, TABLE_BOTTOM, COMPTON, PHOTO, COHERENT, ENERGY_NAMES

COLORS = ("#246AA1", "#187452", "#B65412", "#7854A0")
SYMBOLS = ("circle", "square", "diamond", "triangle-up")
INK = "#193444"
ARROW_CM = 18.


def _base():
    f = go.Figure()
    f.update_layout(template="plotly_white", paper_bgcolor="white", plot_bgcolor="#F8FAFB",
                    font=dict(color=INK, size=12), hoverlabel=dict(font_size=13),
                    margin=dict(l=12,r=14,t=18,b=10), showlegend=False)
    f.update_xaxes(gridcolor="#E4EAED", zeroline=False, automargin=True)
    f.update_yaxes(gridcolor="#E4EAED", zeroline=False, automargin=True)
    return f


def _box(f, x0,x1,z0,z1, color, stroke):
    f.add_shape(type="rect",x0=x0,x1=x1,y0=z0,y1=z1,fillcolor=color,
                line=dict(color=stroke,width=1),layer="below")


def _label(f,x,z,s,anchor="left",color=INK):
    f.add_annotation(x=x,y=z,text=s,xanchor=anchor,showarrow=False,font=dict(size=11,color=color),
                     bgcolor="rgba(255,255,255,0.88)",borderpad=1)


def _crux(f):
    f.add_trace(go.Scatter(x=[0], y=[0], mode="markers", marker=dict(size=8,symbol="cross",color=INK),
                           name="X線焦点", hovertemplate="X線管の焦点：z = 0 cm<extra></extra>"))


def _segments(begin, end):
    sep = np.full(len(end),np.nan)
    return [np.column_stack((begin[:,k],end[:,k],sep)).ravel() for k in (0,2)]


def room_figure(run, idx, close=False):
    """Project the real x,z coordinates without changing primary or scattered directions."""
    p = run.settings
    f = _base()
    if close:
        xrange,zrange,h = [-13,13],[20,-5],440
    else:
        xrange,zrange,h = [-34,34],[105,-7],565
    f.update_layout(height=h,dragmode=False,margin_t=14)
    f.update_xaxes(title="左右 x (cm)",range=xrange,constrain="domain",fixedrange=True)
    f.update_yaxes(title="焦点から下方 z (cm)",range=zrange,scaleanchor="x",scaleratio=1,
                   constrain="domain",fixedrange=True)
    # Nominal open field in the absence of blade transmission.
    half = p.field/2
    f.add_trace(go.Scatter(x=[0,-half,half,0],y=[0,SID,SID,0],mode="lines",fill="toself",
                           fillcolor="rgba(45,107,131,0.055)",line=dict(color="#A6BBC5",width=1,dash="dot"),
                           name="開口の幾何学的境界",hoverinfo="skip"))
    _box(f,-4,4,-3.5,-.4,"#496474","#324B5A")
    _crux(f)
    _label(f,4.7,-2,"X線管")
    # Envelope of the teaching device is schematic; layers are the input to the calculation.
    _box(f,-4.2,4.2,4.7,15.5,"rgba(199,123,56,.065)","#C8A789")
    for z,w,depth,col in ((5,1.3,.1,"#A67951"),(8,1.95,.04,"#718993"),(15,3.5,.2,"#B38157")):
        _box(f,-w,w,z,z+depth,col,col)
    h0,h1=p.field*11/(2*SID),p.field*11.3/(2*SID)
    for sign in (-1,1):
        f.add_shape(type="path",path=f"M {sign*h0},11 L {sign*3.1},11 L {sign*3.1},11.3 L {sign*h1},11.3 Z",
                    fillcolor="#515766",line=dict(color="#515766",width=1.4),layer="below")
    if close:
        for z,label in ((5,"付加フィルタ"),(8,"照射野ミラー"),(11.2,"絞り羽根"),(15.1,"出口カバー")):
            _label(f,4.4,z,label)
    else:
        _label(f,5.0,11,"コリメータ")
        _label(f,-27,45,"空気",color="#765D8E")
        if p.thickness:
            _box(f,-22,22,TABLE_TOP-p.thickness,TABLE_TOP,"rgba(48,124,167,.12)","#6995AF")
            _label(f,-21,TABLE_TOP-p.thickness/2,"被写体")
        _box(f,-26,26,TABLE_TOP,TABLE_BOTTOM,"#BCDACA","#609576")
        _label(f,25.7,95.3,"撮影台","right")
        _box(f,-22,22,SID,SID+.55,"#547183","#344E5E")
        _label(f,-21,SID+2.4,"検出器面")
    positions = run.position[idx]
    x,z=_segments(np.zeros_like(positions),positions)
    f.add_scatter(x=x,y=z,mode="lines",line=dict(color="rgba(60,88,101,.28)",width=1),
                  name="一次X線",hoverinfo="skip")
    g=run.groups
    for j,name in enumerate(GROUPS):
        ids=idx[(g[idx]==j)&(run.process[idx]==COMPTON)]
        if not len(ids):
            continue
        v,w=run.position[ids],run.outgoing[ids]
        end=v+ARROW_CM*w
        x,z=_segments(v,end)
        f.add_scatter(x=x,y=z,mode="lines",line=dict(color=COLORS[j],width=2),name=name+" · 方向",hoverinfo="skip")
        details=[[int(i+1),PARTS[run.part[i]],float(np.degrees(np.arccos(run.cosine[i]))),
                  float(run.scattered_energy[i]),float(run.position[i,1])] for i in ids]
        f.add_scatter(x=v[:,0],y=v[:,2],mode="markers",marker=dict(color=COLORS[j],size=7,
                      symbol=SYMBOLS[j],line=dict(color="white",width=.6)),name=name+" · 発生点",customdata=details,
                      hovertemplate=name+" #%{customdata[0]} · %{customdata[1]}<br>x %{x:.3f} / "
                          "y %{customdata[4]:.3f} / z %{y:.3f} cm<br>θ %{customdata[2]:.1f}° · "
                          "E′ %{customdata[3]:.2f} keV<extra></extra>")
        angles=np.degrees(np.arctan2(w[:,0],-w[:,2]))
        # Fixed energy-to-size mapping across runs; the vector length remains purely illustrative.
        f.add_scatter(x=end[:,0],y=end[:,2],mode="markers",marker=dict(color=COLORS[j],symbol="arrow",
                      size=6.+.065*run.scattered_energy[ids],angle=angles,angleref="up"),
                      name=name+" · 矢印",customdata=details,
                      hovertemplate=name+" #%{customdata[0]}<br>θ %{customdata[2]:.1f}° · "
                          "E′ %{customdata[3]:.2f} keV<extra></extra>")
    for code,sym,size in ((PHOTO,"x",7),(COHERENT,"diamond-open",9)):
        ids=idx[run.process[idx]==code]
        if len(ids):
            f.add_scatter(x=run.position[ids,0],y=run.position[ids,2],mode="markers",name=ENERGY_NAMES[code],
                          marker=dict(symbol=sym,size=size,color=[COLORS[k] for k in g[ids]]),
                          text=[f"#{i+1} · {PARTS[run.part[i]]} · {ENERGY_NAMES[code]}" for i in ids],
                          hovertemplate="%{text}<extra></extra>")
    return f


def distribution_figure(run, angle):
    f=_base()
    vals=np.degrees(np.arccos(run.cosine)) if angle else run.scattered_energy
    edges=np.linspace(0,180 if angle else run.settings.energy,19 if angle else 25)
    mids=(edges[1:]+edges[:-1])/2
    for j,name in enumerate(GROUPS):
        cut=(run.groups==j)&(run.process==COMPTON)
        y,_=np.histogram(vals[cut],bins=edges)
        f.add_bar(x=mids,y=y,width=edges[1]-edges[0],name=name,marker_color=COLORS[j],
                  hovertemplate=name+" · %{y} 個<extra></extra>")
    f.update_layout(barmode="stack",height=300)
    f.update_xaxes(title="一次方向からの散乱角 θ (°)" if angle else "散乱後エネルギー E′ (keV)",
                   range=[edges[0],edges[-1]])
    f.update_yaxes(title="発生数 (個)",rangemode="tozero")
    if not (run.process==COMPTON).any():
        f.add_annotation(text="この標本にはコンプトン事象がありません",xref="paper",yref="paper",x=.5,y=.65,showarrow=False)
    return f
