from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import streamlit as st
from streamlit.runtime import get_instance
from streamlit.testing.v1 import AppTest

from scatter.grid import (Grid, GAP, LEAD, PITCH, HALF_WIDTH, RATIOS, ABSORBED, UNRESOLVED,
                          BACK, MISS, PASS, LEAD_HIT, SIDE, OUTCOMES, add_grid_columns,
                          grid_csv, project_grid, project_rays)
from scatter.grid_display import (comparison_figure, default_detail_id, grid_scene,
                                  projected_events, selection_projection)
from scatter.model import Settings, simulate, NO_HIT, COMPTON, PHOTO, COHERENT
from scatter.playback import pools_for, selections, selected_frame, tracks_payload


def scattered_at(grid, entry, slope):
    entry,slope=np.broadcast_arrays(np.atleast_1d(entry).astype(float), np.atleast_1d(slope))
    z=np.full(len(entry),grid.top-1)
    pos=np.column_stack((entry-slope,np.zeros(len(entry)),z))
    direction=np.column_stack((slope,np.zeros(len(entry)),np.ones(len(entry))))
    return project_rays(pos,np.zeros_like(pos),direction,np.full(len(entry),COMPTON),grid)


@pytest.mark.parametrize("ratio", RATIOS)
def test_divergent_primaries_and_foil_edges_share_the_grid_focus(ratio):
    grid=Grid(ratio,100,100)
    centers=PITCH*np.arange(-700,701,100)
    x=np.r_[centers,centers+PITCH/2]
    pos=np.column_stack((x,x*0,x*0+100))
    directions=pos/np.linalg.norm(pos,axis=1)[:,None]
    p=project_rays(pos,directions,np.zeros_like(pos),np.zeros(len(x),int),grid)
    assert np.all(p.without==PASS)
    assert np.all(p.with_grid[:len(centers)]==PASS)
    assert np.all(p.with_grid[len(centers):]==LEAD_HIT)
    assert np.all(p.end_z[len(centers):]==grid.top)
    np.testing.assert_allclose(p.end_x[:len(centers)],centers)
    for i in (-600,0,600):
        upper=np.array(grid.foil_edges(i, grid.top))
        lower=np.array(grid.foil_edges(i, grid.sid))
        np.testing.assert_allclose(lower-upper,lower*grid.height/grid.focus,atol=1e-13)
        np.testing.assert_allclose(grid.foil_edges(i, grid.sid-grid.focus),[0,0])
        assert lower[1]-lower[0]==pytest.approx(LEAD)
    assert grid.height/GAP==ratio


@pytest.mark.parametrize("slope", [-.5,.5])
def test_absorption_is_first_wall_contact_not_detector_or_far_foil(slope):
    grid=Grid()
    p=scattered_at(grid,0.,slope)
    wall=np.sign(slope)*GAP/2
    depth=wall*grid.scale(grid.top)/(slope-wall/grid.focus)
    assert p.with_grid[0]==LEAD_HIT and p.without[0]==PASS
    assert p.end_z[0]-grid.top==pytest.approx(depth)
    assert p.end_x[0]==pytest.approx(slope*depth)
    assert 0 < depth < grid.height and abs(p.clear_x[0])>PITCH


def test_first_intersection_matches_independent_foil_polygon_clipping():
    grid=Grid(12,90,110)
    # Mix both directions and slopes near a channel edge and across multiple pitches.
    xs=np.linspace(-.021,.021,31)+5.
    for slope in (-.93,-.19,-.018,.014,.13,.74):
        p=scattered_at(grid,xs,slope)
        for i,x in enumerate(xs):
            possible=[]
            for k in range(182,217):
                lt,rt=grid.foil_edges(k,grid.top);lb,rb=grid.foil_edges(k,grid.sid)
                if lt<=x<=rt: possible.append(0.)
                for start,end in ((lt,lb),(rt,rb)):
                    delta=(start-x)/(slope-(end-start)/grid.height)
                    if 0<=delta<=grid.height: possible.append(delta)
            if possible:
                assert p.with_grid[i]==LEAD_HIT and p.end_z[i]-grid.top==pytest.approx(min(possible))
            else:
                assert p.with_grid[i]==PASS and p.end_z[i]==pytest.approx(grid.sid)


def test_absence_side_escape_backscatter_undefined_and_downstream_first_collision():
    grid=Grid()
    far=scattered_at(grid,[HALF_WIDTH+.2,HALF_WIDTH],[0.,.5])
    assert far.without.tolist()==[MISS,SIDE] and not far.entered[0]
    assert np.isnan(far.end_x[0])
    pos=np.array([[0.,0.,80.],[0.,0.,80.],[0.,0.,80.],[0.,0.,grid.top+.01]])
    inc=np.tile([0.,0.,1.],(4,1))
    out=np.tile([0.,0.,-1.],(4,1))
    p=project_rays(pos,inc,out,np.array([PHOTO,COHERENT,COMPTON,PHOTO]),grid)
    assert p.with_grid.tolist()==[ABSORBED,UNRESOLVED,BACK,PASS]
    assert p.primary.tolist()==[False,False,False,True]
    assert p.entered.tolist()==[False,False,False,True]
    # A scatter along the strips in y retains its x channel, just as defined by the 2D section.
    out=np.array([[0.,.999,.04]])
    q=project_rays(pos[:1],inc[:1],out,np.array([COMPTON]),grid)
    assert q.with_grid[0]==PASS


def test_ratio_and_off_focus_selectivity_without_a_change_in_incident_photons():
    shallow=scattered_at(Grid(5), 0.,.085)
    deep=scattered_at(Grid(12), 0.,.085)
    assert shallow.with_grid[0]==PASS and deep.with_grid[0]==LEAD_HIT
    run=simulate(Settings())
    matched=project_grid(run,Grid())
    off=project_grid(run,Grid(8,70,100))
    assert matched.primary[86] and matched.with_grid[86]==PASS and off.with_grid[86]==LEAD_HIT
    np.testing.assert_array_equal(matched.entered,off.entered)
    moved=project_grid(run,Grid(8,100,150))
    refocused=project_grid(run,Grid(8,150,150))
    assert moved.with_grid[86]==LEAD_HIT and refocused.with_grid[86]==PASS
    np.testing.assert_array_equal(moved.entered,refocused.entered)
    for g in [Grid(8,70,96),Grid(12,180,180)]:
        assert g.top>94 and np.isfinite(project_grid(run,g).end_x[project_grid(run,g).entered]).all()


def test_400_paths_per_seed_match_paired_csv_and_drawn_endpoints():
    run=simulate(Settings()); grid=Grid()
    sel=selections(pools_for({},run,True,capacity=400),400,range(4),False,fill_ordered=True)
    frame=selected_frame(sel); events=tracks_payload(sel)
    p=selection_projection(frame,events,grid)
    export=add_grid_columns(frame,p,np.arange(len(frame)))
    assert len(events)==1200 and not export.duplicated(["seed_PCG64","photon_id"]).any()
    for seed in (1,2,3):
        sample=simulate(Settings(seed=seed))
        other=project_grid(sample,grid)
        rows=export.loc[export.seed_PCG64==seed]
        assert rows.photon_id.tolist()==list(range(1,401))
        assert list(rows.with_grid)==np.asarray(OUTCOMES)[other.with_grid[:400]].tolist()
    for enabled in (False,True):
        painted=projected_events(sel,p,enabled,events)
        code=export.with_grid if enabled else export.without_grid
        for i,e in enumerate(painted):
            assert e["gridOutcome"]==code.iat[i] and e["id"]==events[i]["id"]
            if p.entered[i]:
                end=e["exit"] if p.scattered[i] else e["end"]
                key="with_end_" if enabled else "without_end_"
                np.testing.assert_allclose([end[0],end[2]],[export[key+"x_cm"].iat[i],export[key+"z_cm"].iat[i]])
                if p.scattered[i]:
                    np.testing.assert_allclose(np.cross(np.subtract(end,e["end"]),e["direction"]),0,atol=1e-10)
    assert all("gridOutcome" not in e for e in events)


def test_detail_plot_uses_true_coordinates_and_same_scales_for_each_disposition():
    run=simulate(Settings()); grid=Grid(); pair=project_grid(run,grid)
    for index in (default_detail_id(pair)-1,5,1):
        fig=comparison_figure(run,pair,index)
        assert fig.layout.xaxis.range==fig.layout.xaxis2.range and fig.layout.yaxis.range==fig.layout.yaxis2.range
        if pair.entered[index]:
            ends=[t for t in fig.data if t.mode=="markers"]
            assert len(ends)==2 and ends[1].y[0]==pytest.approx((pair.end_z[index]-grid.top)*10)
            assert ends[1].x[0]==pytest.approx((pair.end_x[index]-pair.entry_x[index])*10)
        else:
            assert not any(t.mode=="markers" for t in fig.data)
    for sid in (96,150):
        new=Grid(sid=sid)
        scene=grid_scene(run,new,True)
        assert [x["y0"] for x in scene["shapes"] if x["type"]=="rect"].count(sid)==1
        assert list(scene["beam"])[1][1]==sid and scene["bounds"][3]>sid


def test_grid_downloads_widgets_and_sessions(monkeypatch):
    managers={}; original=st.download_button
    def capture(*args,**kwargs):
        managers[kwargs["key"]]=get_instance().media_file_mgr
        return original(*args,**kwargs)
    monkeypatch.setattr(st,"download_button",capture)
    app=str(Path(__file__).resolve().parents[1]/"app.py")
    a,b=[AppTest.from_file(app,default_timeout=15).run() for _ in range(2)]
    for page in (a,b):
        page.session_state["lab_tab"]="集束グリッド"
        page.run()
    run=a.session_state["_run"]
    a.number_input(key="grid_photon").set_value(87).run()
    a.number_input(key="grid_focus").set_value(70).run()
    assert a.number_input(key="grid_photon").value==87 and b.number_input(key="grid_focus").value==100
    assert a.session_state["_run"] is run and not a.exception and not b.exception
    a.selectbox(key="grid_limit").set_value(400).run()
    def download(name):
        button=next(d for d in a.get("download_button") if d.proto.id.endswith("-"+name))
        manager=managers[name]
        url=manager.execute_deferred(button.proto.deferred_file_id) if button.proto.deferred_file_id else button.proto.url
        return manager._storage.get_file(url.rsplit("/",1)[-1]).content
    frame=pd.read_csv(BytesIO(download("grid_movie_csv")))
    assert len(frame)==400 and frame.iloc[86].with_grid==OUTCOMES[LEAD_HIT]
    summary=pd.read_csv(BytesIO(download("grid_summary_csv")))
    pair=a.session_state["_grid_projection"][1]
    assert summary.lead_absorbed.tolist()==pair.counts().lead_absorbed.tolist()
    assert download("grid_all_csv")==grid_csv(run,pair)
    assert pair.geometry.focus==70 and b.session_state["_grid_projection"][1].geometry.focus==100
