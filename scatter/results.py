"""Read-only views and CSVs from exactly the same primary sample."""
import numpy as np
import pandas as pd

from . import MODEL_VERSION
from .model import (COMPTON, COHERENT, PHOTO, GROUPS, GROUP, MATERIAL, PARTS, ENERGY_NAMES,
                    SID, RAW_FIELD, BLADE, BODY, COVER, MIRROR, FILTER, AIR, TABLE,
                    coefficients, material_data)

LABELS = ("入射（実光路）", "初回相互作用", "コンプトン", "光電吸収", "干渉性", "平均 E′ (keV)")
SOURCE_URL = "https://physics.nist.gov/PhysRefData/Xcom/html/xcom1.html"


def summary(run, components=False):
    result = []
    for j, name in enumerate(PARTS if components else GROUPS):
        sub = np.array([j]) if components else np.flatnonzero(GROUP == j)
        hits = np.isin(run.part, sub)
        com = hits & (run.process == COMPTON)
        result.append(dict(source=name, entered=int(run.entered[:, sub].any(axis=1).sum()),
                           interactions=int(hits.sum()), compton=int(com.sum()),
                           photoelectric=int(np.sum(hits & (run.process == PHOTO))),
                           coherent=int(np.sum(hits & (run.process == COHERENT))),
                           mean_scatter_keV=float(run.scattered_energy[com].mean()) if com.any() else None))
    return result


def indices_for_display(run, limit, sources, examples):
    """Deterministic view; examples cycle through sources without altering full-sample weights."""
    groups = run.groups
    if not examples:
        idx = np.arange(min(limit, run.settings.count))
        return idx[np.isin(groups[idx], sources) | (groups[idx] == -1)]
    rows = [np.flatnonzero((groups == j) & (run.process == COMPTON)) for j in sources]
    picks = []
    for k in range(limit):
        wave = [r[k] for r in rows if r.size > k]
        if not wave:
            break
        picks.extend(wave)
        if len(picks) >= limit:
            break
    return np.asarray(picks[:limit], dtype=int)


def conditions(p):
    return dict(model_version=MODEL_VERSION, energy_keV=p.energy, object_cm=p.thickness,
                square_field_at_detector_cm=p.field, detector_plane_z_cm=SID,
                raw_square_at_detector_cm=RAW_FIELD, incident_photons=p.count, seed_PCG64=p.seed,
                coefficient_source=SOURCE_URL)


def particles(run, idx, metadata=True):
    idx = np.asarray(idx, dtype=int)
    kinds = run.process[idx]
    where = run.part[idx]
    com = kinds == COMPTON
    h = where >= 0
    coords = np.where(h[:, None], run.position[idx], np.nan)
    mat = np.where(h, np.asarray(MATERIAL)[where], "")
    src = np.where(h, np.asarray(GROUPS)[run.groups[idx]], "")
    f = pd.DataFrame(dict(photon_id=idx+1, source=src, component=np.where(h,np.asarray(PARTS)[where],""),
                          material=mat, process=np.asarray(ENERGY_NAMES)[kinds],
                          x_cm=coords[:,0], y_cm=coords[:,1], z_cm=coords[:,2],
                          theta_deg=np.degrees(np.arccos(run.cosine[idx])),
                          azimuth_local_deg=np.degrees(run.azimuth[idx]),
                          scattered_keV=run.scattered_energy[idx],
                          recoil_keV=np.where(com, run.settings.energy-run.scattered_energy[idx], np.nan)))
    if metadata:
        density = {k:v["density"] for k, v in material_data().items()}
        f["density_g_cm3"] = f.material.map(density)
        for k, v in conditions(run.settings).items():
            f[k] = v
        for axis, col in enumerate("xyz"):
            f["incident_"+col] = run.incident[idx, axis]
            f["outgoing_"+col] = run.outgoing[idx, axis]
    return f


def encode(frame):
    return frame.to_csv(index=False, lineterminator="\n", na_rep="").encode("utf-8-sig")


def photon_csv(run, idx=None):
    if idx is None:
        idx = np.arange(run.settings.count)
    return encode(particles(run, idx))


def summary_csv(run):
    frames = []
    for is_part in (False, True):
        f = pd.DataFrame(summary(run, is_part))
        f.insert(0, "aggregation", "component" if is_part else "source")
        frames.append(f)
    f = pd.concat(frames, ignore_index=True)
    for k, v in conditions(run.settings).items():
        f[k] = v
    f["uncollided_to_plane"] = (run.part < 0).sum()
    return encode(f)


def materials_frame(p):
    widths = {AIR:"各層の間", BODY:f"{p.thickness:g} cm", TABLE:"1.00 cm", BLADE:"0.30 cm",
              MIRROR:"0.04 cm（Al等価）", COVER:"0.20 cm", FILTER:"0.10 cm"}
    results = []
    for j, (part, k) in enumerate(zip(PARTS, MATERIAL)):
        m = material_data()[k]
        co, ph, ra, total = coefficients(k, p.energy)
        results.append({"部位":part,"物質":m["name"],"密度 (g/cm³)":m["density"],"軸方向厚":widths[j],
                        "元素質量分率":"・".join(f"{s} {w:g}" for s,w in m["fractions"].items()),
                        "全減弱":total,"非干渉性":co,"光電":ph,"干渉性":ra})
    return pd.DataFrame(results)
