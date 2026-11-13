import csv
from dataclasses import replace
import io
import json
from pathlib import Path

import numpy as np
import pytest
import streamlit as st
from streamlit.runtime import get_instance
from streamlit.testing.v1 import AppTest

from scatter import playback as film
from scatter.model import Settings, simulate, GROUPS, PARTS, COMPTON, NO_HIT, session_run
from scatter.plots import ARROW_CM, room_figure, COLORS
from scatter.results import photon_csv, indices_for_display, summary_csv

def decode(b):
    return list(csv.DictReader(io.StringIO(b.decode("utf-8-sig"))))


@pytest.mark.parametrize("examples,sources,limit",[(False,range(4),100),(True,(3,2,0,1),64),
                                                  (False,(),32),(True,(),8),(True,(2,),100)])
def test_film_ids_and_csv_exactly_match_static_selection(examples,sources,limit):
    r=simulate(Settings(count=17000))
    pools=film.pools_for({},r,False)
    chosen=film.selections(pools,limit,sources,examples)
    original=indices_for_display(r,limit,sources,examples)
    assert chosen[0][1]==(original+1).tolist()
    assert film.selection_csv(chosen)==photon_csv(r,original)
    assert len(pools[0].frame)<=500
    assert len(film.tracks_payload(chosen))<=limit


def test_every_outcome_uses_only_defined_geometry_and_angles():
    r=simulate(Settings())
    selections=film.selections(film.pools_for({},r,False),100,range(4),False)
    event=film.tracks_payload(selections)
    assert set(e["process"] for e in event)==set(range(4))
    for e in event:
        i=e["id"]-1
        np.testing.assert_array_equal(e["end"],r.position[i])
        if e["process"]==COMPTON:
            np.testing.assert_array_equal(e["direction"],r.outgoing[i])
            assert e["energy"]==r.scattered_energy[i] and e["theta"]==np.degrees(np.arccos(r.cosine[i]))
            tip=np.array(e["end"])+ARROW_CM*np.array(e["direction"])
            assert np.linalg.norm(tip-r.position[i])==pytest.approx(18)
        else:
            assert e["direction"] is e["theta"] is e["energy"] is None
            if e["process"]==NO_HIT: assert e["end"][2]==100 and e["part"]==e["group"]==-1
    json.dumps(event,allow_nan=False)


def test_auxiliary_seeds_prepared_once_then_views_read_only(monkeypatch):
    p=Settings(seed=2,count=17000)
    ss={};run=session_run(ss,p); frozen=summary_csv(run)
    calls=[]
    def sample(s):calls.append((s.seed,s.count));return simulate(s)
    monkeypatch.setattr(film,"simulate",sample)
    assert [b.seed for b in film.pools_for(ss,run,False)]==[2] and not calls
    pools=film.pools_for(ss,run,True);assert calls==[(1,17000),(3,17000)]
    ch=film.selections(pools,100,range(4),False)
    records=film.tracks_payload(ch)
    assert len(records)==300 and len({(e["seed"],e["id"]) for e in records})==300
    for s,chunk in enumerate((records[:100],records[100:200],records[200:]),1):
        native=simulate(replace(p,seed=s))
        assert [e["id"] for e in chunk]==list(range(1,101))
        np.testing.assert_array_equal([e["end"] for e in chunk],native.position[:100])
    assert records[0]["end"]!=records[100]["end"]
    again=film.pools_for(ss,run,True)
    assert all(x is y for x,y in zip(again,pools))
    for zoom in (False,True):
        film.make_playlist(run,ch,zoom,100,range(4),False,True)
    assert not any(isinstance(value,type(run)) for bank in pools for value in vars(bank).values())
    assert calls==[(1,17000),(3,17000)] and summary_csv(run)==frozen and ss["_run"] is run
    shifted=session_run(ss,replace(p,thickness=20))
    new=film.pools_for(ss,shifted,True)
    assert calls[2:]==calls[:2] and new[0] is not pools[0]


def test_same_seed_new_session_same_film_and_isolated_banks():
    p=Settings(count=750); states=[{},{}]; samples=[session_run(s,p) for s in states]
    pools=[film.pools_for(s,r,True) for s,r in zip(states,samples)]
    def render(j):
        return film.make_playlist(samples[j],film.selections(pools[j],32,range(4),True),True,32,range(4),True,True)
    assert json.dumps(render(0),allow_nan=False)==json.dumps(render(1),allow_nan=False)
    assert states[0]["_film_bank"] is not states[1]["_film_bank"] and pools[0][0] is not pools[1][0]
    for seed in range(10,20):
        run=session_run(states[0],replace(p,seed=seed))
        film.pools_for(states[0],run,False)
    assert set(states[0]["_film_bank"]["pools"])=={1,2,3,19}
    assert set(states[1]["_film_bank"]["pools"])=={1,2,3}


def test_seed_sequence_csv_and_room_match_v01_even_when_zoomed():
    r=simulate(Settings(count=8000)); selected=film.selections(film.pools_for({},r,True),16,(2,),True)
    rows=decode(film.selection_csv(selected)); normal=film.make_playlist(r,selected,False,16,(2,),True,True)
    zoom=film.make_playlist(r,selected,True,16,(2,),True,True)
    assert normal["signature"]==zoom["signature"] and normal["events"]==zoom["events"]
    assert zoom["colors"]==COLORS and {label["text"] for label in zoom["scene"]["labels"]}>=set(PARTS[3:])
    fig=room_figure(r,np.array([],dtype=int),True)
    assert zoom["scene"]["shapes"]==[s.to_plotly_json() for s in fig.layout.shapes]
    for e,row in zip(zoom["events"],rows,strict=True):
        assert (e["seed"],e["id"])==(int(row["seed_PCG64"]),int(row["photon_id"]))
        assert row["component"]==PARTS[e["part"]] and GROUPS[e["group"]]=="コリメータ周辺"
        assert float(row["scattered_keV"])==e["energy"]
        np.testing.assert_allclose(e["end"],[float(row[k]) for k in ("x_cm","y_cm","z_cm")])


def test_max_sample_size_does_not_increase_browser_payload():
    r=simulate(Settings(count=100000))
    pools=film.pools_for({},r,True); selected=film.selections(pools,100,range(4),True)
    view=film.make_playlist(r,selected,False,100,range(4),True,True)
    assert len(view["events"])==300 and all(len(p.frame)<=500 for p in pools)
    assert len(json.dumps(view,allow_nan=False).encode("utf-8")) < 128*1024


def test_empty_selection_is_not_filled_with_made_up_photons():
    r=simulate(Settings(thickness=0,count=1));sel=film.selections(film.pools_for({},r,True),8,[0],True)
    assert all(not ids for _,ids in sel) and not film.tracks_payload(sel) and not decode(film.selection_csv(sel))


def test_app_modes_and_streamlit_download_match_each_seed(monkeypatch):
    original=st.download_button; managers={}
    def capture(*args,**kwargs):
        managers[kwargs["key"]]=get_instance().media_file_mgr
        return original(*args,**kwargs)
    monkeypatch.setattr(st,"download_button",capture)
    a=AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py"),default_timeout=15).run()
    a.number_input(key="count").set_value(203).run()
    orig=a.session_state["_run"];metrics=[m.value for m in a.metric]
    a.radio(key="view_mode").set_value("連続再生").run()
    assert a.radio(key="film_mode").value=="固定シード"
    a.radio(key="film_mode").set_value("シード連続（1 → 2 → 3）").run()
    a.toggle(key="close").set_value(True).run()
    assert not a.exception and a.session_state["_run"] is orig and [m.value for m in a.metric]==metrics
    button=next(b for b in a.get("download_button") if b.label=="再生対象の光子をCSV保存")
    manager=managers["film_csv"]; url=manager.execute_deferred(button.proto.deferred_file_id)
    downloaded=decode(manager._storage.get_file(url.rsplit("/",1)[-1]).content)
    expected=[]
    for seed in (1,2,3):
        run=simulate(replace(orig.settings,seed=seed))
        idx=indices_for_display(run,16,range(4),True)
        expected.extend(decode(photon_csv(run,idx)))
    assert downloaded==expected
