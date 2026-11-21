"""C1: is the T-dependent NRTL in fabchem.nrtl_tdep right? (Overview 5.1 / 5.6)

For each sourced parameter set at the pressure it was fitted at, and a 3 x 3 grid of feed
compositions x temperatures inside the two-phase window, the IDAES flash
(`fabchem.nrtl_tdep` + `fabchem.nrtl_start`) is solved twice:

- from the reference start, and
- from a perturbed start (T_bubble/T_dew/T_eq +2 K, gamma +10 %, vapor fraction +0.1),
  so the check does not only confirm the point it started from;

and V, x, y and T_bubble are compared with the independent numpy reference
(`fabchem.ipa_water`), tolerance 1e-5. A point passes only if IPOPT reports optimal AND the
state is physical AND it agrees (ADR 0001 Finding 2).

Counter-example (no solver needed): bubble temperatures with tau frozen at 341 K instead of
tau(T), to show whether the T dependence matters at the size of the sets' own fit quality.

Writes evidence/c1-tdep-nrtl-check.json (gitignored). Exit 0 only if every point passes.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

from fabchem import ipa_water as w
from fabchem.nrtl_start import (
    AGREEMENT_TOL,
    Perturbation,
    agreement,
    initialize_flash,
    is_valid,
    state_summary,
)
from fabchem.nrtl_tdep import build_flash_model

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "evidence" / "c1-tdep-nrtl-check.json"

CASES = (  # (parameter set, pressure in Pa): each set at a pressure it was fitted at
    (w.BARBIERI_2024, 60e3),
    (w.BARBIERI_2024, 80e3),
    (w.MARZAL_1996_60, 60e3),
    (w.LIN_TU_2014, 101.325e3),
)
Z_GRID = (0.17, 0.50, 0.80)
WINDOW_FRACTIONS = (0.25, 0.50, 0.75)
PERTURBED = Perturbation(temperature_k=2.0, gamma_rel=0.10, vapor_fraction=0.10)
FROZEN_T = 341.0


def frozen(nrtl: w.NRTLSet, T: float) -> w.NRTLSet:
    t12, t21 = nrtl.tau(T)
    return replace(nrtl, key=f"{nrtl.key}_frozen{T:g}K", a=(t12, t21), b=(0.0, 0.0))


def solve_point(nrtl: w.NRTLSet, P: float, z: float, frac: float) -> dict:
    t_bub, _ = w.bubble(z, P, nrtl)
    t_dew, _ = w.dew(z, P, nrtl)
    T = t_bub + frac * (t_dew - t_bub)
    out: dict = {"set": nrtl.key, "P_Pa": P, "z_ipa": z, "window_fraction": frac, "T": T}
    for label, pert in (("reference_start", None), ("perturbed_start", PERTURBED)):
        try:
            m, st = build_flash_model(nrtl, T, P, z)
            r = initialize_flash(m, st, nrtl, pert)
            solved = state_summary(st)
            out[label] = {
                "termination": r["termination_condition"],
                "ipopt_iterations": r["ipopt_iterations"],
                "agreement": agreement(solved, r["reference"]),
                "valid": is_valid(r["termination_condition"], solved, r["reference"]),
            }
        except Exception as exc:  # record, don't hide
            out[label] = {"valid": False, "error": f"{type(exc).__name__}: {exc}"}
    return out


def main() -> int:
    logging.disable(logging.WARNING)
    points = [
        solve_point(nrtl, P, z, f) for nrtl, P in CASES for z in Z_GRID for f in WINDOW_FRACTIONS
    ]
    runs = [p[k] for p in points for k in ("reference_start", "perturbed_start")]
    n_valid = sum(r["valid"] for r in runs)
    worst = max(
        (max(r["agreement"].values()) for r in runs if "agreement" in r), default=float("nan")
    )

    counter = []
    for nrtl, P in CASES:
        fz = frozen(nrtl, FROZEN_T)
        diffs = [
            w.bubble(z, P, fz)[0] - w.bubble(z, P, nrtl)[0] for z in np.linspace(0.02, 0.98, 49)
        ]
        counter.append(
            {
                "set": nrtl.key,
                "P_kPa": P / 1e3,
                "max_abs_bubble_shift_K": float(np.max(np.abs(diffs))),
            }
        )

    report = {
        "agreement_tolerance": AGREEMENT_TOL,
        "perturbation": PERTURBED.__dict__,
        "n_points": len(points),
        "n_runs": len(runs),
        "n_valid": n_valid,
        "worst_agreement": worst,
        "frozen_tau_counterexample": counter,
        "points": points,
    }
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(f"points: {len(points)} ({len(CASES)} set/pressure cases x 3 z x 3 T)")
    print(f"valid runs: {n_valid}/{len(runs)} (reference start + perturbed start)")
    print(f"worst |IDAES - reference| over V, x, y, T_bubble: {worst:.1e}")
    for c in counter:
        print(
            f"  tau frozen at {FROZEN_T:g} K, {c['set']} @ {c['P_kPa']:g} kPa: "
            f"bubble T shifts up to {c['max_abs_bubble_shift_K']:.2f} K"
        )
    print(f"wrote {OUTPUT}")
    return 0 if n_valid == len(runs) else 1


if __name__ == "__main__":
    sys.exit(main())
