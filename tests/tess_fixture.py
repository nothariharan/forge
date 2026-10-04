"""Synthetic TOI-table fixture for tools/tess_bias_run.py. NOT real data.

Shaped like the archive table: tfopwg_disp codes, tid hosts with several TOIs,
pl_*/st_* measurements, *err*/symerr/lim columns, timestamps. Resolution depends
only on the features (the covariate-shift assumption in bench/PROTOCOL_TESS.md),
so the fixture checks the runner's logic, not any property of real TESS data.
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import numpy as np

COLUMNS = ["toi", "tid", "tfopwg_disp", "toi_created", "rowupdate", "release_date",
           "pl_orbper", "pl_trandurh", "pl_trandep", "pl_rade", "pl_raderr1", "pl_eqt", "pl_insol",
           "pl_eqtlim", "pl_insolsymerr", "st_tmag", "st_teff", "st_rad", "st_logg", "st_dist"]


def make_fixture(path: Path, n_hosts: int = 2600, seed: int = 7, easy_selection: float = 0.0) -> str:
    """Write the fixture CSV and return its sha256.

    easy_selection > 0 makes resolution favor objects whose transit depth sits far from the
    planet/false-positive boundary, i.e. easy cases. Selection is still on observed features
    only, but it makes the resolved set easier to classify, so resolved-set AUC overstates.
    """
    rng = np.random.default_rng(seed)
    rows = []
    toi = 100.0
    for h in range(n_hosts):
        tid = 1_000_000 + h
        tmag = rng.normal(11.0, 1.6)
        teff = rng.normal(5600, 900)
        srad = abs(rng.lognormal(0.0, 0.35))
        logg = rng.normal(4.4, 0.25)
        dist = abs(rng.lognormal(5.2, 0.6))
        n_toi = rng.choice([1, 2, 3], p=[0.88, 0.09, 0.03])
        for _ in range(n_toi):
            toi += 1
            planet = rng.random() < 0.45
            depth = float(np.exp(rng.normal(7.0 + 1.1 * (not planet), 1.0)))
            dur = float(np.exp(rng.normal(1.0 + 0.35 * (not planet), 0.4)))
            per = float(np.exp(rng.normal(2.0 - 0.3 * (not planet), 1.1)))
            rade = float(srad * 109.2 * np.sqrt(depth * 1e-6) * rng.lognormal(0, 0.1))
            eqt = float(teff * np.sqrt(srad * 0.00465 / (2 * (per / 365.25) ** (2 / 3))))
            # Resolution depends only on observed features (brighter, deeper, shorter period -> resolved sooner).
            logit = -0.6 + 0.55 * (11.0 - tmag) + 0.45 * (np.log(depth) - 7.5) - 0.25 * (np.log(per) - 2.0)
            logit += easy_selection * (abs(np.log(depth) - 7.55) - 0.8)
            resolved = rng.random() < 1 / (1 + np.exp(-logit))
            if rng.random() < 0.07 and tmag < 10.5:
                disp = "KP"
            elif resolved:
                disp = "CP" if planet else ("FA" if rng.random() < 0.07 else "FP")
            else:
                disp = "APC" if rng.random() < 0.09 else "PC"
            missing = lambda v: "" if rng.random() < 0.04 else f"{v:.6g}"  # noqa: E731  ~4% missing cells
            rows.append({
                "toi": f"{toi:.2f}", "tid": str(tid), "tfopwg_disp": disp,
                "toi_created": f"20{rng.integers(19, 26)}-0{rng.integers(1, 9)}-1{rng.integers(0, 9)} 12:00:00",
                "rowupdate": "2026-08-01 00:00:00", "release_date": "2026-08-01",
                "pl_orbper": missing(per), "pl_trandurh": missing(dur), "pl_trandep": missing(depth),
                "pl_rade": missing(rade), "pl_raderr1": missing(rade * 0.1), "pl_eqt": missing(eqt),
                "pl_insol": missing((eqt / 278.0) ** 4), "pl_eqtlim": "0", "pl_insolsymerr": "1",
                "st_tmag": missing(tmag), "st_teff": missing(teff), "st_rad": missing(srad),
                "st_logg": missing(logg), "st_dist": missing(dist),
            })
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return hashlib.sha256(path.read_bytes()).hexdigest()
