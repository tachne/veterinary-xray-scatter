from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from scatter.downstream import ANGLE_EDGES, angle_figure, arrival_share, detector_distributions, paired_movie_events
from scatter.grid import Grid, LEAD_HIT, PASS, add_grid_columns, project_grid
from scatter.grid_display import selection_projection
from scatter.model import Settings, simulate
from scatter.playback import pools_for, selected_frame, selections, tracks_payload


@pytest.mark.parametrize("grid",[Grid(),Grid(5,70,150),Grid(12,180,96)])
def test_histograms_count_exact_csv_outcomes_and_use_projected_angle(grid):
    run=simulate(Settings());pair=project_grid(run,grid)
    hist=detector_distributions(run,pair)
    for i,key in enumerate((pair.without,pair.with_grid)):
        # An independent scalar reference uses the *incoming ray at the foil*, not the
        # Compton scattering angle, nor the detector’s energy or an absolute angle.
        reference=np.zeros((2,36),int)
        for j in np.flatnonzero(key==PASS):
            group=int(pair.scattered[j])
            v=run.outgoing[j] if group else run.incident[j]
            deg=np.degrees(np.arctan(v[0]/v[2]))
            reference[group,min(35,int((deg+90)//5))]+=1
        np.testing.assert_array_equal(np.array([hist[i]["primary"],hist[i]["scatter"]]),reference)
        counts=pair.counts().iloc[i]
        assert hist[i]["primary"].sum()==counts.primary_passed
        assert hist[i]["scatter"].sum()==counts.scatter_passed
    fig=angle_figure(hist)
    assert fig.layout.yaxis.range==fig.layout.yaxis2.range and fig.layout.xaxis.range==(-90,90)
    assert list(fig.data[0].x)==list((ANGLE_EDGES[:-1]+ANGLE_EDGES[1:])/2)


@pytest.mark.parametrize(("p","s","expected"),[(0,0,None),(0,2,(0.,1.)),(4,0,(1.,0.)),(491,290,(491/781,290/781))])
def test_shares_use_detector_counts_and_do_not_invent_an_empty_fraction(p,s,expected):
    assert arrival_share(p,s)==expected


def test_paired_replay_matches_both_csv_endpoints_and_unmodified_direction_for_three_seeds():
    run=simulate(Settings())
    selected=selections(pools_for({},run,True,capacity=400),400,range(4),False,fill_ordered=True)
    frame=selected_frame(selected);raw=tracks_payload(selected);unchanged=deepcopy(raw)
    pair=selection_projection(frame,raw,Grid())
    exported=add_grid_columns(frame,pair,np.arange(len(frame)))
    off,on=paired_movie_events(selected,pair,raw,frame)
    assert raw==unchanged and len(off)==len(on)==1200
    for i,(a,b,row) in enumerate(zip(off,on,exported.itertuples(index=False))):
        assert (a["seed"],a["id"])==(b["seed"],b["id"])==(row.seed_PCG64,row.photon_id)
        assert a["gridOutcome"]==row.without_grid and b["gridOutcome"]==row.with_grid
        if row.entered:
            for e,x,z in ((a,row.without_end_x_cm,row.without_end_z_cm),(b,row.with_end_x_cm,row.with_end_z_cm)):
                terminal=e.get("exit",e["end"])
                assert terminal[0]==x and terminal[2]==z
                vector=e["xzDirection"]
                assert vector==([row.incident_x,row.incident_z] if e["gridPrimary"] else [row.outgoing_x,row.outgoing_z])
                dx=x-e["entry"][0];dz=z-e["entry"][2]
                assert dx*vector[1]-dz*vector[0]==pytest.approx(0,abs=1e-12)
                if e["gridCode"]==PASS: assert z==row.grid_sid_cm
            if b["gridCode"]==LEAD_HIT: assert b.get("exit",b["end"])[2]<=row.grid_sid_cm
        else: assert "xzDirection" not in a and "xzDirection" not in b


def test_empty_arrival_ui_and_session_scope_of_the_paired_player():
    path=str(Path(__file__).resolve().parents[1]/"app.py")
    a,b=[AppTest.from_file(path,default_timeout=15).run() for _ in range(2)]
    for app in (a,b):
        app.session_state["lab_tab"]="集束グリッド";app.run()
    old=b.session_state["_run"]
    a.number_input(key="count").set_value(1)
    # Default single-photon sample/seed 7 has no detector arrivals on either side.
    a.number_input(key="seed").set_value(7).run()
    pair=a.session_state["_grid_projection"][1]
    assert not pair.counts()[["primary_passed","scatter_passed"]].to_numpy().any()
    assert sum("割合は算出できません" in c.value for c in a.caption)==2
    assert not a.exception and not b.exception
    assert b.session_state["_run"] is old and b.number_input(key="count").value==20_000
    assert any("62.9%" in c.value for c in b.caption)
