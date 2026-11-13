"""Read-only detector views. PASS and the endpoints are supplied by the v0.2.0 model."""
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .grid import PASS

PRIMARY_INK = "#176c75"
SCATTER_INK = "#aa521c"
ANGLE_EDGES = np.arange(-90., 91., 5.)


def detector_distributions(run, pair):
    """One bin per arriving photon, using the signed x–z angle to +z (not Compton θ)."""
    out = []
    for codes in (pair.without, pair.with_grid):
        counts = {}
        for kind, mask, directions in (("primary", pair.primary, run.incident),
                                       ("scatter", pair.scattered, run.outgoing)):
            ux, _, uz = directions[(codes == PASS) & mask].T
            deg = np.degrees(np.arctan2(ux, uz))
            counts[kind] = np.histogram(deg, bins=ANGLE_EDGES)[0]
        out.append(counts)
    return out


def arrival_share(primary, scatter):
    total = primary + scatter
    return None if not total else (primary / total, scatter / total)


def angle_figure(distributions):
    centers = (ANGLE_EDGES[1:] + ANGLE_EDGES[:-1]) / 2
    titles = ("グリッドなし", "グリッドあり")
    fig = make_subplots(rows=1, cols=2, shared_yaxes=True, subplot_titles=titles, horizontal_spacing=.07)
    ymax = 1
    for col, counts in enumerate(distributions, 1):
        ymax = max(ymax, int((counts["primary"] + counts["scatter"]).max()))
        for key, name, color in (("primary","一次線",PRIMARY_INK), ("scatter","散乱線",SCATTER_INK)):
            fig.add_bar(x=centers, y=counts[key], width=4.7, name=name, legendgroup=key, showlegend=col==1,
                        marker_color=color, customdata=list(zip(ANGLE_EDGES[:-1], ANGLE_EDGES[1:])),
                        hovertemplate=name+"：%{y} 個<br>%{customdata[0]}° ～ %{customdata[1]}°<extra></extra>",
                        row=1,col=col)
    fig.update_layout(template="plotly_white", barmode="stack", height=286,
                      margin=dict(l=12,r=8,t=28,b=5), legend=dict(orientation="h",y=-.21),
                      font=dict(size=12,color="#193444"))
    fig.update_xaxes(range=[-90,90], tickvals=[-90,-45,0,45,90], ticksuffix="°", fixedrange=True)
    fig.update_yaxes(range=[0,1.08*ymax], fixedrange=True)
    fig.update_yaxes(title_text="到達光子数（個）",row=1,col=1)
    return fig


def paired_movie_events(selected, pair, raw, frame):
    from .grid_display import projected_events
    cases = [projected_events(selected, pair, enabled, raw) for enabled in (False, True)]
    for i in np.flatnonzero(pair.entered):
        prefix = "incident_" if pair.primary[i] else "outgoing_"
        direction = [float(frame[prefix + axis].iat[i]) for axis in "xz"]
        for case in cases:
            case[i]["xzDirection"] = direction  # direction cosines, not a slope fitted to the drawing
    return cases
