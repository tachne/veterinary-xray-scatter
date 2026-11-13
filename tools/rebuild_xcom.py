"""Extract the offline first-interaction tables from the official NIST HTML.

Run with --fetch to download fresh composition and XCOM responses. Without
--fetch, only the files in --raw are read. No network is used by the app.
"""
import argparse
import csv
import html
import json
import re
import subprocess
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode


MATERIALS = {
    "air": ("104", "乾燥空気"),
    "water": ("276", "液体水"),
    "al": ("013", "アルミニウム"),
    "pb": ("082", "鉛"),
    "pmma": ("223", "ポリメタクリル酸メチル（PMMA）"),
    "pc": ("219", "ポリカーボネート（PC）"),
}
SYMBOL = {1: "H", 6: "C", 7: "N", 8: "O", 13: "Al", 18: "Ar", 82: "Pb"}
ENERGIES = (30, 40, 50, 60, 70, 80, 85, 90, 100, 120, 150)
COLUMNS = ("material", "energy_keV", "coherent_cm2_g", "incoherent_cm2_g",
           "photoelectric_cm2_g", "total_cm2_g")
COMPOSITION = "https://physics.nist.gov/cgi-bin/Star/compos.pl?matno={}"
XCOM = "https://physics.nist.gov/cgi-bin/Xcom/xcom3_3"


def fetch(url, path, fields=None):
    args = ["curl", "--fail", "--silent", "--show-error", "--max-time", "40"]
    if fields:
        args.extend(["--data", urlencode(fields)])
    path.write_bytes(subprocess.check_output([*args, url]))


def composition_from(page):
    numbers = re.findall(r"<td>(\d+)</td>\s*<td>([\d.]+)</td>", page)
    density = re.search(r"Density .*?<td align=left>([\d.E+-]+)</td>", page)
    if not numbers or not density:
        raise ValueError("NIST composition table is missing")
    weights = {SYMBOL[int(z)]: float(w) for z, w in numbers}
    if abs(sum(weights.values()) - 1) > 2e-6:
        raise ValueError(f"Invalid NIST mass fractions: {weights}")
    return float(density[1]), weights


def extract_rows(page, fractions):
    returned = {SYMBOL[int(z)]: float(w) for z, w in
                re.findall(r"Z=\s*(\d+)\s*:\s*([\d.]+)", page)}
    if set(returned) != set(fractions) or any(
        abs(returned[element] - weight) > 2e-6 for element, weight in fractions.items()
    ):
        raise ValueError("XCOM composition differs from NIST material definition")
    rows = {}
    for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", page, re.I | re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", x)).strip()
                 for x in re.findall(r"<td\b[^>]*>(.*?)</td>", tr, re.I | re.S)]
        if len(cells) != 9 or not re.fullmatch(r"[.\d]+E[+-]\d+", cells[1]):
            continue
        energy = Decimal(cells[1]) * 1000
        if energy not in ENERGIES:
            continue
        if energy in rows or cells[0]:
            raise ValueError(f"Ambiguous energy / absorption edge at {energy} keV")
        coh, inc, phot, pair_n, pair_e, total, _ = map(Decimal, cells[2:])
        if pair_n != 0 or pair_e != 0 or min(coh, inc, phot, total) <= 0:
            raise ValueError(f"Unexpected interaction terms at {energy} keV")
        # The HTML rounds each of the four coefficients independently.
        allowance = sum(Decimal(1).scaleb(v.as_tuple().exponent) for v in
                        (coh, inc, phot, total)) / 2
        if abs(coh + inc + phot - total) > allowance:
            raise ValueError(f"XCOM partial/total discrepancy at {energy} keV")
        rows[int(energy)] = (cells[2], cells[3], cells[4], cells[7])
    if set(rows) != set(ENERGIES):
        raise ValueError(f"Missing NIST energy: {set(ENERGIES) - rows.keys()}")
    return rows


def rebuild(raw, out, download):
    raw.mkdir(parents=True, exist_ok=True)
    materials, output_rows = {}, []
    for key, (material_id, name) in MATERIALS.items():
        comp_path = raw / f"{key}_comp.html"
        data_path = raw / f"{key}_xcom.html"
        url = COMPOSITION.format(material_id)
        if download:
            fetch(url, comp_path)
        density, fractions = composition_from(comp_path.read_text(encoding="latin-1"))
        materials[key] = dict(name=name, density=density, fractions=fractions, url=url)
        if download:
            fields = {
                "Name": key, "Formulae": "\r\n".join(f"{s} {v:.6f}" for s, v in fractions.items()),
                "NumAdd": "1", "Graph0": "on", "ResizeFlag": "on", "WindowXmin": "0.03",
                "WindowXmax": "0.15", "Energies": "\r\n".join(f"{e/1000:g}" for e in ENERGIES),
            }
            fetch(XCOM, data_path, fields)
        rows = extract_rows(data_path.read_text(encoding="latin-1"), fractions)
        output_rows.extend((key, e, *rows[e]) for e in ENERGIES)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "xcom.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(COLUMNS)
        writer.writerows(output_rows)
    (out / "materials.json").write_text(
        json.dumps(materials, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--raw", type=Path, required=True, help="directory with NIST HTML responses")
    cli.add_argument("--out", type=Path, required=True, help="destination for the CSV and JSON")
    cli.add_argument("--fetch", action="store_true", help="download the twelve public NIST responses")
    args = cli.parse_args()
    rebuild(args.raw, args.out, args.fetch)
