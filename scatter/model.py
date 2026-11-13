"""First collision in prescribed plane layers; all coordinates in cm, energies in keV."""
import csv
import json
from dataclasses import dataclass
from functools import lru_cache
from numbers import Integral
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[1] / "data"
ENERGIES = (30, 40, 50, 60, 70, 80, 85, 90, 100, 120, 150)
SID, RAW_FIELD, TABLE_TOP, TABLE_BOTTOM = 100., 40., 93., 94.
MEC2 = 511.
GROUPS = ("被写体", "撮影台", "コリメータ周辺", "空気")
AIR, BODY, TABLE, BLADE, MIRROR, COVER, FILTER = range(7)
PARTS = ("空気", "被写体", "撮影台", "絞り羽根", "照射野ミラー", "出口カバー", "付加フィルタ")
MATERIAL = ("air", "water", "pc", "pb", "al", "pmma", "al")
GROUP = np.array([3, 0, 1, 2, 2, 2, 2])
ENERGY_NAMES = ("無相互作用", "コンプトン", "光電吸収", "干渉性散乱")
NO_HIT, COMPTON, PHOTO, COHERENT = range(4)


@lru_cache(maxsize=1)
def material_data():
    return json.loads((DATA / "materials.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _data():
    with (DATA / "xcom.csv").open(encoding="utf-8") as f:
        return {(r["material"], int(r["energy_keV"])): tuple(float(r[k]) for k in (
            "incoherent_cm2_g", "photoelectric_cm2_g", "coherent_cm2_g", "total_cm2_g"))
            for r in csv.DictReader(f)}


def coefficients(material, energy):
    """Process order: Compton, photoelectric, coherent, total incl. coherent."""
    if energy not in ENERGIES:
        raise ValueError("XCOMの収録エネルギーを指定してください。")
    return _data()[material, energy]


@dataclass(frozen=True)
class Settings:
    energy: int = 80
    thickness: float = 12.
    field: float = 24.
    count: int = 20_000
    seed: int = 42

    def __post_init__(self):
        if self.energy not in ENERGIES or not (0 <= self.thickness <= 30 and 6 <= self.field <= 36):
            raise ValueError("エネルギー・被写体厚・照射野がモデル範囲外です。")
        if any(isinstance(x, bool) or not isinstance(x, Integral) for x in (self.seed, self.count)):
            raise ValueError("シードと光子数は整数です。")
        if not 0 <= self.seed <= 2**32-1 or not 1 <= self.count <= 100_000:
            raise ValueError("シードまたは光子数が許容範囲外です。")


def energy_after(energy, cosine):
    return energy / (1. + (energy / MEC2) * (1. - np.asarray(cosine)))


def kn_weight(energy, cosine):
    """Density proportional to dσ/dΩ and to dP/dcosθ (not dP/dθ)."""
    c = np.asarray(cosine)
    r = energy_after(energy, c) / energy
    return r*r*(r+1./r-(1.-c*c))


def sample_kn(energy, n, rng):
    # The free-electron weight is <= 2: r^3+r-r²sin²θ <= 2 for r <= 1.
    out = np.empty(n)
    pending = np.arange(n)
    while pending.size:
        c = rng.uniform(-1., 1., pending.size)
        ok = 2*rng.random(pending.size) < kn_weight(energy, c)
        out[pending[ok]] = c[ok]
        pending = pending[~ok]
    return out


def rotate(incident, cosine, azimuth):
    # incident is always downward; cross with the y axis gives a stable local basis.
    e1 = np.stack([incident[:, 2], np.zeros(len(incident)), -incident[:, 0]], axis=1)
    e1 /= np.linalg.norm(e1, axis=1)[:, None]
    e2 = np.cross(incident, e1)
    sine = np.sqrt(np.maximum(0., 1.-cosine**2))
    return (incident*cosine[:, None] +
            sine[:, None]*(e1*np.cos(azimuth)[:, None] + e2*np.sin(azimuth)[:, None]))


def layers(p, outside):
    """Primary paths. In the blade span the aperture is air; other sections are uniform."""
    blade = np.where(outside, BLADE, AIR)
    return ((0., 5., AIR), (5., 5.1, FILTER), (5.1, 8., AIR), (8., 8.04, MIRROR),
            (8.04, 11., AIR), (11., 11.3, blade), (11.3, 15., AIR), (15., 15.2, COVER),
            (15.2, TABLE_TOP-p.thickness, AIR), (TABLE_TOP-p.thickness, TABLE_TOP, BODY),
            (TABLE_TOP, TABLE_BOTTOM, TABLE), (TABLE_BOTTOM, SID, AIR))


@dataclass(frozen=True, eq=False)
class Run:
    settings: Settings
    incident: np.ndarray
    position: np.ndarray  # first event; uncollided rows end at the detector plane
    part: np.ndarray      # -1 if uncollided
    process: np.ndarray
    entered: np.ndarray   # flags by particle and component, even across repeated air segments
    cosine: np.ndarray
    azimuth: np.ndarray
    outgoing: np.ndarray
    scattered_energy: np.ndarray

    @property
    def groups(self):
        return np.where(self.part >= 0, GROUP[self.part], -1)


def probability(mass_attenuation, density, path_cm):
    return -np.expm1(-mass_attenuation*density*path_cm)


def simulate(p):
    rng = np.random.Generator(np.random.PCG64(p.seed))
    n = p.count
    # Incident distribution is uniform in area on the detector plane before collimation.
    # Draw directions and two independent uniforms per photon before applying any material.
    u = rng.random((n, 4))
    target = (u[:, :2]-.5)*RAW_FIELD
    direction = np.column_stack((target, np.full(n, SID)))
    direction /= np.linalg.norm(direction, axis=1)[:, None]
    outside = np.max(np.abs(target), axis=1) > p.field/2
    tau, choose = -np.log1p(-u[:, 2]), u[:, 3]
    cs = np.array([coefficients(k, p.energy) for k in MATERIAL])
    mu = cs[:, 3]*np.array([material_data()[k]["density"] for k in MATERIAL])
    branching = cs[:, :3]/cs[:, :3].sum(axis=1, keepdims=True)
    part = np.full(n, -1, np.int8)
    entered = np.zeros((n, len(PARTS)), dtype=bool)
    z = np.full(n, SID)
    for a, b, comp in layers(p, outside):
        if b <= a:
            continue
        idx = np.flatnonzero(part < 0)
        if not idx.size:
            break
        k = comp if np.isscalar(comp) else comp[idx]
        entered[idx, k] = True
        depth = (b-a)*mu[k]/direction[idx, 2]
        hit = tau[idx] < depth
        which = idx[hit]
        part[which] = k if np.isscalar(k) else k[hit]
        z[which] = a + tau[which]*direction[which, 2]/mu[part[which]]
        tau[idx[~hit]] -= depth[~hit]
    process = np.zeros(n, dtype=np.int8)
    k = part[part >= 0]
    v = choose[part >= 0]
    process[part >= 0] = np.where(v < branching[k, 0], COMPTON,
                                  np.where(v < branching[k, 0]+branching[k, 1], PHOTO, COHERENT))
    position = direction*(z/direction[:, 2])[:, None]
    scatter = process == COMPTON
    c, phi, e = np.full(n,np.nan), np.full(n,np.nan), np.full(n,np.nan)
    out = np.full((n,3), np.nan)
    c[scatter] = sample_kn(p.energy, int(scatter.sum()), rng)
    phi[scatter] = rng.uniform(0, 2*np.pi, scatter.sum())
    e[scatter] = energy_after(p.energy, c[scatter])
    out[scatter] = rotate(direction[scatter], c[scatter], phi[scatter])
    for arr in (direction, position, part, process, entered, c, phi, out, e):
        arr.setflags(write=False)
    return Run(p, direction, position, part, process, entered, c, phi, out, e)


def session_run(state, settings):
    old = state.get("_run")
    if old is None or old.settings != settings:
        old = state["_run"] = simulate(settings)
    return old
