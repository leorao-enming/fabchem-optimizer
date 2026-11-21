"""C1: does `fabchem.nrtl_start` initialize T-dependent NRTL flashes reliably?

Grid: 4 set/pressure cases x 7 feed compositions x 5 temperatures (subcooled liquid 5 K below
T_bubble; 25 / 50 / 75 % of the two-phase window; superheated vapor 5 K above T_dew) = 140
states. Nothing is set by hand: each state is built at its (T, P, z) and handed to

- `nrtl_start.initialize_flash` (the new initializer), and, for comparison,
- IDAES's own `initialize()` followed by one IPOPT solve, with IDAES's default smoothing
  (what someone using the package as shipped would get).

A run counts as valid only if IPOPT says optimal AND the state is physical AND V, x, y and
T_bubble agree with the independent reference to 1e-5 (ADR 0001 Finding 2).

Note: the new initializer starts from the reference solution, so this check is about
whether IPOPT converges and stays there for every phase state; scripts/c1_tdep_nrtl_check.py
is the one that starts away from the answer.

Writes evidence/c1-tdep-init-check.json (gitignored). Exit 0 only if the new initializer
is valid on all 140 states.
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import sys
from collections import Counter
from pathlib import Path

from pyomo.environ import SolverFactory

from fabchem import ipa_water as w
from fabchem.nrtl_start import (
    AGREEMENT_TOL,
    agreement,
    initialize_flash,
    is_valid,
    state_summary,
)
from fabchem.nrtl_tdep import build_flash_model

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "evidence" / "c1-tdep-init-check.json"

CASES = (
    (w.BARBIERI_2024, 60e3),
    (w.BARBIERI_2024, 80e3),
    (w.MARZAL_1996_60, 60e3),
    (w.LIN_TU_2014, 101.325e3),
)
Z_GRID = (0.02, 0.10, 0.17, 0.30, 0.50, 0.70, 0.90)
STATES = ("subcooled", "window_25", "window_50", "window_75", "superheated")
MARGIN_K = 5.0


def temperature(state: str, t_bub: float, t_dew: float) -> float:
    if state == "subcooled":
        return t_bub - MARGIN_K
    if state == "superheated":
        return t_dew + MARGIN_K
    return t_bub + int(state.split("_")[1]) / 100.0 * (t_dew - t_bub)


def run_new(nrtl: w.NRTLSet, T: float, P: float, z: float) -> dict:
    m, st = build_flash_model(nrtl, T, P, z)
    r = initialize_flash(m, st, nrtl)
    solved = state_summary(st)
    return {
        "termination": r["termination_condition"],
        "valid": is_valid(r["termination_condition"], solved, r["reference"]),
        "agreement": agreement(solved, r["reference"]),
    }


def run_idaes_default(nrtl: w.NRTLSet, T: float, P: float, z: float, reference: dict) -> dict:
    m, st = build_flash_model(nrtl, T, P, z)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            m.fs.state.initialize()
    except Exception as exc:  # InitializationError is an expected outcome here
        return {"termination": "initialize_failed", "valid": False, "error": type(exc).__name__}
    results = SolverFactory("ipopt").solve(m, load_solutions=False)
    term = str(results.solver.termination_condition)
    if term != "optimal":
        return {"termination": term, "valid": False}
    m.solutions.load_from(results)
    solved = state_summary(st)
    return {
        "termination": term,
        "valid": is_valid(term, solved, reference),
        "agreement": agreement(solved, reference),
    }


def main() -> int:
    logging.disable(logging.CRITICAL)
    rows = []
    for nrtl, P in CASES:
        for z in Z_GRID:
            t_bub, _ = w.bubble(z, P, nrtl)
            t_dew, _ = w.dew(z, P, nrtl)
            for state in STATES:
                T = temperature(state, t_bub, t_dew)
                ref = w.flash(T, P, z, nrtl)
                reference = {"V": ref.V, "x": list(ref.x), "y": list(ref.y), "T_bubble": t_bub}
                row = {"set": nrtl.key, "P_Pa": P, "z_ipa": z, "state": state, "T": T}
                for label, fn in (
                    ("new", lambda: run_new(nrtl, T, P, z)),  # noqa: B023
                    ("idaes_default", lambda: run_idaes_default(nrtl, T, P, z, reference)),  # noqa: B023
                ):
                    try:
                        row[label] = fn()
                    except Exception as exc:
                        row[label] = {"valid": False, "error": f"{type(exc).__name__}: {exc}"}
                rows.append(row)

    def tally(label: str) -> dict:
        valid = sum(r[label]["valid"] for r in rows)
        fails = Counter(
            (r["state"], r[label].get("termination", r[label].get("error", "?")))
            for r in rows
            if not r[label]["valid"]
        )
        optimal_but_wrong = sum(
            1 for r in rows if r[label].get("termination") == "optimal" and not r[label]["valid"]
        )
        return {
            "valid": valid,
            "n": len(rows),
            "optimal_but_wrong": optimal_but_wrong,
            "failures_by_state": {f"{s}: {t}": n for (s, t), n in sorted(fails.items())},
        }

    summary = {"new": tally("new"), "idaes_default": tally("idaes_default")}
    report = {"agreement_tolerance": AGREEMENT_TOL, "summary": summary, "rows": rows}
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"wrote {OUTPUT}")
    return 0 if summary["new"]["valid"] == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
