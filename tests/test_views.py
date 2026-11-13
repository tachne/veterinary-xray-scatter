import csv
import io
from pathlib import Path
import numpy as np
import streamlit as st
from streamlit.runtime import get_instance
from streamlit.testing.v1 import AppTest

from scatter.model import COMPTON, ENERGY_NAMES, GROUPS, MATERIAL, PARTS, Settings, simulate
from scatter.plots import ARROW_CM, distribution_figure, room_figure
from scatter.results import indices_for_display, photon_csv, summary, summary_csv

APP=Path(__file__).resolve().parents[1]/"app.py"


def decode(data):
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))


def test_examples_ordinal_filter_and_no_mutation():
    r=simulate(Settings())
    before=photon_csv(r,np.arange(500))
    examples=indices_for_display(r,16,[0,1,2,3],True)
    assert len(set(examples))==16
    np.testing.assert_array_equal(r.groups[examples],np.tile(np.arange(4),4))
    assert (r.process[examples]==COMPTON).all()
    np.testing.assert_array_equal(indices_for_display(r,16,[0,1,2,3],False),np.arange(16))
    empty=indices_for_display(r,64,[],True)
    assert not len(empty)
    assert (r.part[indices_for_display(r,64,[],False)]<0).all()
    histogram=distribution_figure(r,True)
    for jj, layer in enumerate(histogram.data):
        assert sum(layer.y)==summary(r)[jj]["compton"]
    for selected in (empty,examples):
        for close in (True,False):
            room_figure(r,selected,close)
    assert photon_csv(r,np.arange(500))==before


def test_glyphs_on_projected_real_coordinates_and_angle_and_energy_from_csv():
    r=simulate(Settings()); ids=indices_for_display(r,32,range(4),True)
    fig=room_figure(r,ids)
    exported={int(row["photon_id"]):row for row in decode(photon_csv(r,ids))}
    found=set()
    for name in GROUPS:
        starts=next(tr for tr in fig.data if tr.name==name+" · 発生点")
        ends=next(tr for tr in fig.data if tr.name==name+" · 矢印")
        for idx,info in enumerate(starts.customdata):
            pid=int(info[0]); found.add(pid)
            row=exported[pid]
            assert row["source"]==name and row["component"]==info[1]
            np.testing.assert_allclose([starts.x[idx], starts.y[idx],info[2],info[3]],
                [float(row[k]) for k in ("x_cm","z_cm","theta_deg","scattered_keV")])
            dx,dz=float(row["outgoing_x"]),float(row["outgoing_z"])
            np.testing.assert_allclose([ends.x[idx],ends.y[idx]],
                [starts.x[idx]+ARROW_CM*dx,starts.y[idx]+ARROW_CM*dz])
            assert ends.marker.size[idx] == 6+.065*float(row["scattered_keV"])
            a=np.radians(ends.marker.angle[idx])
            np.testing.assert_allclose([np.sin(a),-np.cos(a)],np.array([dx,dz])/np.hypot(dx,dz),atol=1e-12)
    assert found==set(exported)


def test_all_outcomes_and_source_summaries_in_csv():
    r=simulate(Settings(count=9000))
    all_rows=decode(photon_csv(r))
    assert [int(z["photon_id"]) for z in all_rows]==list(range(1,9001))
    assert set(z["process"] for z in all_rows)==set(ENERGY_NAMES)
    for row in all_rows:
        i=int(row["photon_id"])-1; k=r.part[i]
        assert row["model_version"] and row["seed_PCG64"]=="42" and row["object_cm"]=="12.0"
        assert row["component"]==(PARTS[k] if k>=0 else "") and row["material"]==(MATERIAL[k] if k>=0 else "")
        if k==-1: assert row["z_cm"]==row["source"]==row["density_g_cm3"]==""
        if r.process[i]==COMPTON:
            assert abs(float(row["scattered_keV"])+float(row["recoil_keV"])-80)<1e-11
        else: assert row["theta_deg"]==row["azimuth_local_deg"]==row["scattered_keV"]==row["outgoing_z"]==""
    agg=decode(summary_csv(r))
    for row in agg:
        key="source" if row["aggregation"]=="source" else "component"
        found=[z for z in all_rows if z[key]==row["source"]]
        assert int(row["interactions"])==len(found)
        assert int(row["compton"])==sum(z["process"]=="コンプトン" for z in found)
    assert sum(int(z["interactions"]) for z in agg[:4])+int(agg[0]["uncollided_to_plane"])==9000


def test_streamlit_display_filters_reuse_cached_sample_and_sessions_are_independent(monkeypatch):
    captured={}
    original=st.download_button
    def capture(*args,**kw):
        captured[kw["key"]]=(kw["data"],get_instance().media_file_mgr)
        return original(*args,**kw)
    monkeypatch.setattr(st,"download_button",capture)
    a=AppTest.from_file(str(APP),default_timeout=12).run()
    a.number_input(key="count").set_value(600).run()
    orig=a.session_state["_run"]
    a.selectbox(key="limit").set_value(32).run()
    a.multiselect(key="sources").set_value([GROUPS[2]]).run()
    a.toggle(key="close").set_value(True).run()
    assert not a.exception and a.session_state["_run"] is orig
    ids=indices_for_display(orig,32,[2],True)
    table=next(df.value for df in a.dataframe if "光子番号" in df.value.columns)
    assert list(table["光子番号"])==list(ids+1)
    dbuttons={b.proto.id.split("-")[-1]:b for b in a.get("download_button")}
    for key,selection in (("view_csv",ids),("all_csv",np.arange(600))):
        _,mgr=captured[key]
        url=mgr.execute_deferred(dbuttons[key].proto.deferred_file_id)
        file=mgr._storage.get_file(url.rsplit("/",1)[-1])
        assert file.content==photon_csv(orig,selection)
    assert captured["summary_csv"][0]==summary_csv(orig)
    b=AppTest.from_file(str(APP),default_timeout=12).run()
    a.radio(key="pick").set_value("入射番号順").run()
    a.multiselect(key="sources").set_value([]).run()
    a.number_input(key="seed").set_value(7).run()
    assert b.number_input(key="seed").value==42 and b.multiselect(key="sources").value==list(GROUPS)
    assert a.session_state["_run"] is not orig and not a.exception


def test_no_events_controls_one_photon_export():
    a=AppTest.from_file(str(APP),default_timeout=12).run()
    a.number_input(key="count").set_value(1)
    a.slider(key="thick").set_value(0)
    a.select_slider(key="energy").set_value(30)
    a.multiselect(key="sources").set_value(["被写体"]).run()
    assert not a.exception and a.info
    r=a.session_state["_run"]
    assert summary(r)[0]["entered"]==0 and r.settings.energy==30
    out=photon_csv(r,indices_for_display(r,8,[0],True))
    assert not decode(out) and "photon_id" in out.decode("utf-8-sig").splitlines()[0]
