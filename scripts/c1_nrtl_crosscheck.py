"""Cross-lab check of the two sourced IPA/water NRTL parameter sets (C1, Overview 5.5/5.6).

Criteria were frozen in docs/model-basis-memo.md BEFORE this script was first run:
Gate A  Barbieri 2024 parameters on Marzal 1996 @ 60 kPa
Gate B  Marzal 1996 parameters (60 kPa set) on Barbieri 2024 @ 60 kPa
pass if MAD(T) <= 0.6 K and MAD(y_IPA) <= 0.03, using the project's Wagner vapor
pressures. Everything else printed is informational.

Bubble-temperature model: sum_i x_i gamma_i(T, x) Psat_i(T) = P, y_i = x_i gamma_i Psat_i / P
(ideal vapor phase, Poynting factor 1 - Marzal reports fugacity coefficients 0.96-0.9985).
Pure end points are excluded from MAD (they only test the vapor-pressure correlation).

Conventions (verified against the papers' own reported infinite-dilution gammas):
- Barbieri: tau_ij = a_ij + b_ij/T, alpha = 0.47, component 1 = IPA.
- Marzal:   tau_ij = A_ij/(R T) with A in J/mol, alpha = 0.30, component 1 = WATER.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

sys.path.insert(0, str(Path(__file__).resolve().parent))
import c0_flash_spike as s  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data" / "vle"
R = 8.314462618

MAD_T_LIMIT = 0.6
MAD_Y_LIMIT = 0.03

# Component order everywhere below: [IPA, water]
BARBIERI = {"a12": -1.39470283, "a21": 4.50009825, "b12": 627.160288, "b21": -791.079743}
BARBIERI_ALPHA = 0.47
MARZAL_A = {  # J/mol, component 1 = water: (A12, A21)
    30: (6726.08, 111.46),
    60: (6899.21, 106.99),
    100: (6900.81, 77.49),
}
MARZAL_ALPHA = 0.30
# Lin & Tu, Fluid Phase Equilib. 368 (2014) 104-111, Table 5, 2-propanol (1) + water (2),
# 101.3 kPa only: tau_ij = A_ij/T with A in K, alpha = 0.3. Added after the gates were frozen
# and run, so it is informational only.
LIN_TU = (-6.2261, 850.77)
LIN_TU_ALPHA = 0.30
ANTOINE = {  # ln(P/kPa) = A - B/(C + T/K), Marzal 1996 Table 2: [IPA, water]
    "ipa": (16.4089, 3439.60, -63.417),
    "water": (16.5700, 3984.92, -39.724),
}


def tau_barbieri(T: float) -> tuple[float, float]:
    """(tau_IPA,water, tau_water,IPA)"""
    return (
        BARBIERI["a12"] + BARBIERI["b12"] / T,
        BARBIERI["a21"] + BARBIERI["b21"] / T,
    )


def tau_marzal(P_kpa: int):
    a12, a21 = MARZAL_A[P_kpa]  # water-IPA, IPA-water

    def f(T: float) -> tuple[float, float]:
        return a21 / (R * T), a12 / (R * T)  # (tau_IPA,water, tau_water,IPA)

    return f


def tau_lin_tu(T: float) -> tuple[float, float]:
    return LIN_TU[0] / T, LIN_TU[1] / T


def gamma(x_ipa: float, T: float, tau_fn, alpha: float) -> np.ndarray:
    t12, t21 = tau_fn(T)  # 1 = IPA, 2 = water
    g12, g21 = np.exp(-alpha * t12), np.exp(-alpha * t21)
    x1, x2 = x_ipa, 1.0 - x_ipa
    ln1 = x2**2 * (t21 * (g21 / (x1 + x2 * g21)) ** 2 + t12 * g12 / (x2 + x1 * g12) ** 2)
    ln2 = x1**2 * (t12 * (g12 / (x2 + x1 * g12)) ** 2 + t21 * g21 / (x1 + x2 * g21) ** 2)
    return np.exp([ln1, ln2])


def psat_wagner(T: float) -> np.ndarray:
    return s.psat_ref(T)


def psat_antoine(T: float) -> np.ndarray:
    return np.array([1e3 * np.exp(a - b / (c + T)) for a, b, c in ANTOINE.values()])


def bubble(x_ipa: float, P_pa: float, tau_fn, alpha: float, psat) -> tuple[float, float]:
    def f(T: float) -> float:
        x = np.array([x_ipa, 1 - x_ipa])
        return float(np.sum(x * gamma(x_ipa, T, tau_fn, alpha) * psat(T)) - P_pa)

    T = brentq(f, 300.0, 400.0)
    x = np.array([x_ipa, 1 - x_ipa])
    y_ipa = float(x[0] * gamma(x_ipa, T, tau_fn, alpha)[0] * psat(T)[0] / P_pa)
    return T, y_ipa


def load(name: str) -> list[tuple[float, float, float, float]]:
    """rows of (P_kPa, T_K, x_ipa, y_ipa), pure end points removed"""
    rows = []
    with open(DATA / name, newline="") as fh:
        for r in csv.DictReader(fh):
            if "x_ipa" in r:
                x, y = float(r["x_ipa"]), float(r["y_ipa"])
            else:
                x, y = 1 - float(r["x_water"]), 1 - float(r["y_water"])
            if 0.0 < x < 1.0:
                rows.append((float(r["P_kPa"]), float(r["T_K"]), x, y))
    return rows


def evaluate(rows, tau_fn, alpha, psat) -> tuple[float, float]:
    dts, dys = [], []
    for p, t_exp, x, y_exp in rows:
        t_calc, y_calc = bubble(x, p * 1e3, tau_fn, alpha, psat)
        dts.append(abs(t_calc - t_exp))
        dys.append(abs(y_calc - y_exp))
    return float(np.mean(dts)), float(np.mean(dys))


def main() -> int:
    marzal = {p: load(f"marzal1996_{p}kpa.csv") for p in (30, 60, 100)}
    barb = {p: load(f"barbieri2024_{p}kpa.csv") for p in (60, 80)}

    cases = [
        # (label, kind, rows, tau_fn, alpha)
        ("A  Barbieri params on Marzal 60 kPa", "gate", marzal[60], tau_barbieri, BARBIERI_ALPHA),
        ("B  Marzal(60) params on Barbieri 60 kPa", "gate", barb[60], tau_marzal(60), MARZAL_ALPHA),
        ("Barbieri params on Barbieri 60 kPa", "in-sample", barb[60], tau_barbieri, BARBIERI_ALPHA),
        ("Barbieri params on Barbieri 80 kPa", "in-sample", barb[80], tau_barbieri, BARBIERI_ALPHA),
        (
            "Marzal(30) params on Marzal 30 kPa",
            "in-sample",
            marzal[30],
            tau_marzal(30),
            MARZAL_ALPHA,
        ),
        (
            "Marzal(60) params on Marzal 60 kPa",
            "in-sample",
            marzal[60],
            tau_marzal(60),
            MARZAL_ALPHA,
        ),
        (
            "Marzal(100) params on Marzal 100 kPa",
            "in-sample",
            marzal[100],
            tau_marzal(100),
            MARZAL_ALPHA,
        ),
        (
            "Barbieri params on Marzal 30 kPa",
            "extrapolation",
            marzal[30],
            tau_barbieri,
            BARBIERI_ALPHA,
        ),
        (
            "Barbieri params on Marzal 100 kPa",
            "extrapolation",
            marzal[100],
            tau_barbieri,
            BARBIERI_ALPHA,
        ),
        (
            "Marzal(60) params on Barbieri 80 kPa",
            "extrapolation",
            barb[80],
            tau_marzal(60),
            MARZAL_ALPHA,
        ),
        (
            "Marzal(100) params on Barbieri 80 kPa",
            "extrapolation",
            barb[80],
            tau_marzal(100),
            MARZAL_ALPHA,
        ),
    ]
    third = [
        ("Lin&Tu(101.3) params on Marzal 100 kPa", marzal[100]),
        ("Lin&Tu(101.3) params on Marzal 60 kPa", marzal[60]),
        ("Lin&Tu(101.3) params on Barbieri 60 kPa", barb[60]),
        ("Lin&Tu(101.3) params on Barbieri 80 kPa", barb[80]),
    ]
    print(f"{'case':46s} {'kind':14s} {'MAD(T)/K':>9s} {'MAD(y_IPA)':>11s}  gate")
    ok = True
    for label, kind, rows, tau_fn, alpha in cases:
        mt, my = evaluate(rows, tau_fn, alpha, psat_wagner)
        verdict = ""
        if kind == "gate":
            passed = mt <= MAD_T_LIMIT and my <= MAD_Y_LIMIT
            ok &= passed
            verdict = "PASS" if passed else "FAIL"
        print(f"{label:46s} {kind:14s} {mt:9.3f} {my:11.4f}  {verdict}")

    print("\nThird set, informational only (added after the gates were frozen and run):")
    for label, rows in third:
        mt, my = evaluate(rows, tau_lin_tu, LIN_TU_ALPHA, psat_wagner)
        print(f"  {label:46s} MAD(T)={mt:.3f} K  MAD(y_IPA)={my:.4f}")

    print("\nPOST-HOC diagnostic (chosen after seeing the gate results; NOT a gate):")
    print("  MAD over x_IPA >= 0.10 only, where the published x uncertainty is small vs x")
    for label, rows, tau_fn, alpha in (
        ("A  Barbieri params on Marzal 60 kPa", marzal[60], tau_barbieri, BARBIERI_ALPHA),
        ("B  Marzal(60) params on Barbieri 60 kPa", barb[60], tau_marzal(60), MARZAL_ALPHA),
        ("Barbieri params on Barbieri 60 kPa", barb[60], tau_barbieri, BARBIERI_ALPHA),
    ):
        mt, my = evaluate([r for r in rows if r[2] >= 0.10], tau_fn, alpha, psat_wagner)
        print(f"  {label:46s} MAD(T)={mt:.3f} K  MAD(y_IPA)={my:.4f}")

    print("\nSensitivity to the vapor-pressure correlation (not a gate):")
    for p in (30, 60, 100):
        w = evaluate(marzal[p], tau_marzal(p), MARZAL_ALPHA, psat_wagner)
        a = evaluate(marzal[p], tau_marzal(p), MARZAL_ALPHA, psat_antoine)
        print(
            f"  Marzal({p}) on own data: Wagner MAD(T)={w[0]:.3f} K, "
            f"paper Antoine MAD(T)={a[0]:.3f} K (paper reports in-sample MAD(T) 0.28/0.36/0.31)"
        )
    print(f"\nGates A and B both pass: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
