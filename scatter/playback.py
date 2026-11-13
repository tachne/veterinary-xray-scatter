"""Bounded, session-local read-only projections of v0.1 samples for browser playback."""
from dataclasses import dataclass, replace
from heapq import merge
from itertools import zip_longest, islice

import numpy as np
import pandas as pd

from .model import COMPTON, ENERGY_NAMES, GROUPS, PARTS, simulate
from .plots import ARROW_CM, COLORS, room_figure
from .results import encode, indices_for_display, particles

SEEDS = (1, 2, 3)
MAX_SHOW = 400
PLAYBACK_LIMITS = (16, 32, 50, 100, 200, 400)


@dataclass(frozen=True, eq=False)
class Pool:
    seed: int
    count: int
    front: tuple
    groups: tuple
    frame: pd.DataFrame
    endpoints: dict
    ordered: tuple
    extra_rows: pd.DataFrame

    @classmethod
    def from_run(cls, run, capacity=100):
        n = run.settings.count
        first = tuple(range(1, min(n, capacity) + 1))
        groups = tuple(tuple((indices_for_display(run, capacity, [g], True) + 1).tolist())
                       for g in range(len(GROUPS)))
        ids = sorted(set(first).union(*groups))
        rows = np.asarray(ids) - 1
        frame = particles(run, rows).set_index("photon_id", drop=False)
        # For filtered, numbered playback, the first capacity rows of each category suffice
        # for every combination of sources. The final category is the uncollided beam.
        source = run.groups
        ordered = tuple(tuple((np.flatnonzero(source == g)[:capacity] + 1).tolist())
                        for g in (*range(len(GROUPS)), -1))
        extra = sorted(set().union(*ordered).difference(ids))
        extra_rows = particles(run, np.asarray(extra, dtype=int) - 1).set_index("photon_id", drop=False)
        # No-hit rows have blank interaction coordinates in the CSV. Retain their
        # computed detector endpoints for the drawing, too.
        all_ids = ids + extra
        return cls(run.settings.seed, n, first, groups, frame,
                   dict(zip(all_ids, run.position[np.asarray(all_ids) - 1].tolist())), ordered, extra_rows)

    def rows(self, ids):
        if self.frame.index.isin(ids).sum() == len(ids):
            return self.frame.loc[ids]
        return pd.concat([self.frame, self.extra_rows]).loc[ids]

    def choose(self, limit, sources, examples, *, fill_ordered=False):
        if not 1 <= limit <= MAX_SHOW:
            raise ValueError("再生本数は1〜400本です。")
        if examples:
            by_source = [self.groups[g] for g in sources]
            it = (i for group in zip_longest(*by_source) for i in group if i is not None)
            return list(islice(it, limit))
        if fill_ordered:
            categories = [self.ordered[g] for g in sources] + [self.ordered[-1]]
            return list(islice(merge(*categories), limit))
        names = {GROUPS[g] for g in sources}
        return [i for i in self.front[:limit] if self.frame.at[i,"source"] in names|{""}]


def pools_for(state, run, sequence, *, capacity=100):
    """Do not retain three large Runs. Prepare each seed once per physical setup."""
    p = run.settings
    key = (p.energy, p.thickness, p.field, p.count, capacity)
    bank = state.get("_film_bank")
    if bank is None or bank["key"] != key:
        bank = state["_film_bank"] = {"key": key, "pools": {}}
    pools = bank["pools"]
    # Keep at most the auxiliary triplet and the currently selected sidebar seed.
    for old in set(pools) - {*SEEDS, p.seed}:
        del pools[old]
    seeds = SEEDS if sequence else (p.seed,)
    for seed in seeds:
        if seed not in pools:
            sample = run if seed == p.seed else simulate(replace(p, seed=seed))
            pools[seed] = Pool.from_run(sample, capacity)
            del sample
    return [pools[s] for s in seeds]


def selections(pools, limit, sources, examples, *, fill_ordered=False):
    return [(pool, pool.choose(limit, sources, examples, fill_ordered=fill_ordered)) for pool in pools]


def selected_frame(selections):
    return pd.concat([pool.rows(ids) for pool, ids in selections], ignore_index=True)


def selection_csv(selections):
    # Original particle-CSV schema; (seed_PCG64, photon_id) is the compound key.
    return encode(selected_frame(selections))


def tracks_payload(selections):
    events = []
    for pool, ids in selections:
        for row in pool.rows(ids).itertuples(index=False):
            kind = ENERGY_NAMES.index(row.process)
            events.append(dict(seed=pool.seed, id=row.photon_id, process=kind,
                               part=PARTS.index(row.component) if row.component else -1,
                               group=GROUPS.index(row.source) if row.source else -1,
                               end=pool.endpoints[row.photon_id],
                               direction=[row.outgoing_x,row.outgoing_y,row.outgoing_z] if kind==COMPTON else None,
                               theta=row.theta_deg if kind==COMPTON else None,
                               energy=row.scattered_keV if kind==COMPTON else None))
    return events


def scene(run, close):
    """Reuse the actual backdrop, labels and field outline of the original room plot."""
    fig = room_figure(run, np.array([], dtype=int), close)
    bounds = [*fig.layout.xaxis.range, *sorted(fig.layout.yaxis.range)]
    shapes = [s.to_plotly_json() for s in fig.layout.shapes]
    labels = [dict(x=a.x, z=a.y, text=a.text, anchor=a.xanchor) for a in fig.layout.annotations]
    beam = next(t for t in fig.data if t.name=="開口の幾何学的境界")
    return dict(close=close, bounds=bounds, shapes=shapes, labels=labels, beam=list(zip(beam.x,beam.y)))


def make_playlist(run, selected, close, limit, sources, examples, sequence):
    p = run.settings
    # Zoom is a camera change, not a different sample. The auxiliary mode is
    # independent of the sidebar seed, which still belongs to all-sample totals.
    signature = [p.energy,p.thickness,p.field,p.count,[s.seed for s,_ in selected],
                 sequence,limit,list(sources),examples]
    return dict(signature=signature, events=tracks_payload(selected), scene=scene(run,close),
                samples=[dict(seed=s.seed,count=s.count,shown=len(ids)) for s,ids in selected],
                colors=COLORS, groups=GROUPS, parts=PARTS, processes=ENERGY_NAMES,
                length=ARROW_CM, incidentEnergy=p.energy)
