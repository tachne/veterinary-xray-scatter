"""Paired, deterministic x–z ray intersections for an ideal focused linear grid (cm)."""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .model import NO_HIT, COMPTON, COHERENT
from .results import encode, particles


GRID_VERSION = "focused-xz-0.2.0"
GAP = 0.020       # clear width at the detector-side reference plane
LEAD = 0.005      # lead width at that plane
PITCH = GAP + LEAD
HALF_WIDTH = 22.0
RATIOS = (5, 8, 10, 12)

ABSORBED, UNRESOLVED, BACK, MISS, PASS, LEAD_HIT, SIDE = range(7)
OUTCOMES = ("光電吸収で終了", "干渉性散乱・方向未計算", "上向き・平面に向かわず",
            "入口幅外", "検出器面に到達（直線外挿）", "鉛箔で吸収", "グリッド側方へ退出")
KINDS = ("対象外", "一次線", "散乱線")


@dataclass(frozen=True)
class Grid:
    ratio: int = 8
    focus: float = 100.
    sid: float = 100.

    def __post_init__(self):
        if self.ratio not in RATIOS or not 70 <= self.focus <= 180 or not 96 <= self.sid <= 180:
            raise ValueError("グリッドの許容範囲を確認してください。")

    @property
    def height(self):
        return self.ratio * GAP

    @property
    def top(self):
        return self.sid - self.height

    def scale(self, z):
        # All edges intersect x=0 at z=sid-focus.
        return 1. + (z - self.sid) / self.focus

    def foil_edges(self, strip, z):
        center = (strip + .5) * PITCH
        return (center - LEAD/2) * self.scale(z), (center + LEAD/2) * self.scale(z)


@dataclass(frozen=True)
class Paired:
    geometry: Grid
    primary: np.ndarray          # arrival at grid would be as a primary
    scattered: np.ndarray        # direction of a Compton event is defined above the grid
    entered: np.ndarray
    without: np.ndarray          # outcomes without / with lead strips
    with_grid: np.ndarray
    entry_x: np.ndarray
    clear_x: np.ndarray          # geometric intersection at detector depth
    end_x: np.ndarray            # actual endpoint with the grid, if entered
    end_z: np.ndarray

    def counts(self):
        rows = []
        for enabled, codes in ((False, self.without), (True, self.with_grid)):
            passed = codes == PASS
            hit = codes == LEAD_HIT
            rows.append(dict(grid_enabled=enabled,
                             primary_incident=int((self.primary & self.entered).sum()),
                             primary_passed=int((self.primary & passed).sum()),
                             scatter_incident=int((self.scattered & self.entered).sum()),
                             scatter_passed=int((self.scattered & passed).sum()),
                             primary_lead_absorbed=int((self.primary & hit).sum()),
                             scatter_lead_absorbed=int((self.scattered & hit).sum()),
                             lead_absorbed=int(hit.sum()), side_exit=int((codes == SIDE).sum())))
        return pd.DataFrame(rows)


def project_grid(run, grid):
    """No RNG. Only the upper face admits rays; y is infinite in this 2D section."""
    return project_rays(run.position, run.incident, run.outgoing, run.process, grid)


def project_rays(position, incident, outgoing, process, grid):
    z = position[:, 2]
    primary = (process == NO_HIT) | (z >= grid.top)
    scattered = ~primary & (process == COMPTON)
    x0 = np.where(primary, 0., position[:, 0])
    z0 = np.where(primary, 0., z)
    ux = np.where(primary, incident[:, 0], outgoing[:, 0])
    uz = np.where(primary, incident[:, 2], outgoing[:, 2])
    forward = (primary | scattered) & (uz > 0.)
    slope = np.divide(ux, uz, out=np.zeros_like(z), where=forward)
    x_top = x0 + (grid.top - z0)*slope
    entered = forward & (np.abs(x_top) <= HALF_WIDTH)
    status = np.full(len(z), ABSORBED, dtype=np.int8)
    status[~primary & (process == COHERENT)] = UNRESOLVED
    status[scattered & ~forward] = BACK
    status[forward] = MISS
    indices = np.flatnonzero(entered)
    entry_x, clear_x, end_x, end_z = np.full((4, len(z)), np.nan)
    entry_x[indices] = xt = x_top[indices]
    ray_slope = slope[indices]
    clear_x[indices] = xb = xt + grid.height*ray_slope

    # Intersect the finite outside edge, too. A side exit is not a lead absorption.
    side = np.abs(xb) > HALF_WIDTH
    length = np.full(len(xt), grid.height)
    length[side] = (np.copysign(HALF_WIDTH, xb[side])-xt[side])/ray_slope[side]
    status[indices] = np.where(side, SIDE, PASS)
    with_grid = status.copy()

    # In detector-plane coordinates, each clear channel is centered on k*pitch.
    # u(z)=x(z)/scale(z) is monotone on the short slab, so the first possible
    # foil is the adjacent channel wall, even if the ray crosses many strips.
    u = xt / grid.scale(grid.top)
    middle = np.floor(u / PITCH + .5)*PITCH
    offset = u - middle
    tolerance = 2e-12  # cm, a grazing contact belongs to lead
    front_hit = np.abs(offset) >= GAP/2 - tolerance
    u_last = (xt + ray_slope*length)/grid.scale(grid.top + length)
    right = u_last >= middle + GAP/2 - tolerance
    left = u_last <= middle - GAP/2 + tolerance
    wall_hit = ~front_hit & (right | left)
    wall = middle + np.where(right, GAP/2, -GAP/2)
    distance = length.copy()
    distance[front_hit] = 0.
    distance[wall_hit] = ((wall[wall_hit]*grid.scale(grid.top)-xt[wall_hit]) /
                          (ray_slope[wall_hit]-wall[wall_hit]/grid.focus))
    distance = np.clip(distance, 0., length)
    with_grid[indices[front_hit | wall_hit]] = LEAD_HIT
    end_x[indices] = xt + ray_slope*distance
    end_z[indices] = grid.top + distance
    return Paired(grid, primary, scattered, entered, status, with_grid, entry_x, clear_x, end_x, end_z)


def session_projection(state, run, grid):
    previous = state.get("_grid_projection")
    if previous is None or previous[0] != run.settings or previous[1].geometry != grid:
        previous = state["_grid_projection"] = (run.settings, project_grid(run, grid))
    return previous[1]


def grid_frame(run, pair, ids):
    ids = np.asarray(ids, dtype=int)  # zero-based Run index; exported photon_id is one-based
    return add_grid_columns(particles(run, ids), pair, ids)


def add_grid_columns(frame, pair, ids):
    frame = frame.copy()
    grid = pair.geometry
    frame["grid_model"] = GRID_VERSION
    frame["grid_sid_cm"] = grid.sid
    frame["grid_focus_cm"] = grid.focus
    frame["grid_ratio"] = grid.ratio
    frame["clear_width_cm"], frame["foil_width_cm"] = GAP, LEAD
    frame["grid_entry_z_cm"] = grid.top
    frame["grid_half_width_cm"] = HALF_WIDTH
    frame["ray_kind"] = np.asarray(KINDS)[pair.primary[ids].astype(int) + 2*pair.scattered[ids]]
    frame["entered"] = pair.entered[ids]
    frame["entry_x_cm"] = pair.entry_x[ids]
    frame["without_grid"] = np.asarray(OUTCOMES)[pair.without[ids]]
    frame["with_grid"] = np.asarray(OUTCOMES)[pair.with_grid[ids]]
    frame["without_end_x_cm"], frame["without_end_z_cm"] = off_endpoints(pair, ids)
    frame["with_end_x_cm"], frame["with_end_z_cm"] = pair.end_x[ids], pair.end_z[ids]
    return frame


def off_endpoints(pair, ids):
    x = pair.clear_x[ids].copy()
    z = np.where(pair.entered[ids], pair.geometry.sid, np.nan)
    side = pair.without[ids] == SIDE
    edge = np.copysign(HALF_WIDTH, x[side])
    top = pair.entry_x[ids][side]
    z[side] = pair.geometry.top + pair.geometry.height*(edge-top)/(x[side]-top)
    x[side] = edge
    return x, z


def grid_csv(run, pair, ids=None):
    if ids is None:
        ids = np.arange(run.settings.count)
    return encode(grid_frame(run, pair, ids))
