import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from scatter import playback
from scatter.model import Settings, simulate
from scatter.results import indices_for_display, photon_csv, summary_csv


@pytest.mark.parametrize("limit", [16, 32, 50, 100])
def test_each_seed_has_requested_real_photons_in_reproducible_order(limit):
    settings = Settings()
    run = simulate(settings)
    pools = playback.pools_for({}, run, True)
    selected = playback.selections(pools, limit, range(4), True, fill_ordered=True)
    expected = []
    for pool, ids in selected:
        source = simulate(replace(settings, seed=pool.seed))
        indices = indices_for_display(source, limit, range(4), True)
        assert len(ids) == len(set(ids)) == limit
        assert ids == (indices + 1).tolist()
        expected.extend((pool.seed, i) for i in ids)
    payload = playback.tracks_payload(selected)
    assert [(e["seed"], e["id"]) for e in payload] == expected
    assert len(expected) == 3 * limit


def test_count_and_source_changes_reuse_samples_and_preserve_totals(monkeypatch):
    run = simulate(Settings())
    state = {}
    pools = playback.pools_for(state, run, False)
    sequence = playback.pools_for(state, run, True)
    original = summary_csv(run)
    original_frame = pools[0].frame
    def unexpected_call(*_):
        pytest.fail("Changing the playlist must reuse the prepared samples")
    monkeypatch.setattr(playback, "simulate", unexpected_call)
    for limit in (16, 32, 50, 100, 16):
        selected = playback.selections(playback.pools_for(state, run, False), limit, [0, 3],
                                       False, fill_ordered=True)
        expected = np.flatnonzero(np.isin(run.groups, [0, 3, -1]))[:limit]
        assert selected[0][1] == (expected + 1).tolist()
        assert len(expected) == limit
        assert playback.selection_csv(selected) == photon_csv(run, expected)
        assert len(playback.tracks_payload(selected)) == limit
        assert all(a is b for a, b in zip(sequence, playback.pools_for(state, run, True)))
    assert pools[0].frame is original_frame
    assert summary_csv(run) == original


def test_real_shortfall_and_seed42_mirror_precision():
    tiny = simulate(Settings(count=7))
    tiny_pools = playback.pools_for({}, tiny, True)
    small = playback.selections(tiny_pools, 100, range(4), False, fill_ordered=True)
    assert [ids for _, ids in small] == [list(range(1, 8))] * 3
    run = simulate(Settings())
    selected = playback.selections(playback.pools_for({}, run, False), 100, range(4), True)
    event = next(e for e in playback.tracks_payload(selected) if e["id"] == 19)
    assert event["energy"] == run.scattered_energy[18]
    assert event["theta"] == np.degrees(np.arccos(run.cosine[18]))
    assert f'{event["theta"]:.1f}' == "81.3" and f'{event["energy"]:.2f}' == "70.62"
    np.testing.assert_array_equal(event["end"], run.position[18])


def test_large_sample_cache_and_wire_size_remain_bounded():
    run = simulate(Settings(count=100_000))
    pools = playback.pools_for({}, run, True)
    for pool in pools:
        cached_ids = set(pool.frame.index) | set(pool.extra_rows.index)
        assert not (set(pool.frame.index) & set(pool.extra_rows.index))
        assert set(pool.endpoints) == cached_ids
        assert len(cached_ids) <= 1000
    for examples in (True, False):
        selected = playback.selections(pools, 100, [2], examples, fill_ordered=True)
        data = playback.make_playlist(run, selected, False, 100, [2], examples, True)
        assert len(data["events"]) == 300
        assert len(json.dumps(data).encode()) < 128 * 1024


def test_streamlit_keeps_independent_counts_per_view_and_session():
    app_path = str(Path(__file__).resolve().parents[1] / "app.py")
    a = AppTest.from_file(app_path, default_timeout=15).run()
    b = AppTest.from_file(app_path, default_timeout=15).run()
    original, metrics = a.session_state["_run"], [m.value for m in a.metric]
    a.selectbox(key="limit").set_value(64).run()
    for app in (a, b):
        app.radio(key="view_mode").set_value("連続再生").run()
        widget = app.selectbox(key="film_limit")
        assert widget.options == ["16", "32", "50", "100", "200", "400"] and widget.value == 16
    for limit in (32, 50, 100):
        a.selectbox(key="film_limit").set_value(limit).run()
        assert any(f"再生対象 {limit} 本" in m.value for m in a.markdown)
        assert a.session_state["_run"] is original and [m.value for m in a.metric] == metrics
    assert b.selectbox(key="film_limit").value == 16
    a.radio(key="view_mode").set_value("静止図").run()
    assert a.selectbox(key="limit").value == 64
    a.radio(key="view_mode").set_value("連続再生").run()
    assert a.selectbox(key="film_limit").value == 100
    assert not a.exception and not b.exception
