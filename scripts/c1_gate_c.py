"""C1 Gate C: sourced NRTL sets on an independent laboratory's 101.3 kPa data.

Criteria were frozen in docs/model-basis-memo.md ("Gate C: frozen criteria", committed in
aa4f772) BEFORE data/vle/lintu2014_101kpa.csv was transcribed or compared:

Gate C1  Marzal 1996 parameters fitted at 100 kPa, on Lin & Tu 2014 at 101.3 kPa
Gate C2  Barbieri 2024 parameters (fitted at 60-80 kPa), same data - extrapolation
pass if MAD(T) <= 0.6 K and MAD(y_IPA) <= 0.03 with the project's Wagner vapor pressures,
pure end points excluded, every other published point included.
Informational: Lin & Tu's own parameters on their own data (in-sample).

The data were transcribed by hand from Lin & Tu (2014) Table 2 and checked by recomputing
the paper's printed activity coefficients from its own Table 4 vapor pressures: gamma_1
matches on all 15 points, gamma_2 within 0.4 %.

Also prints a post-hoc, uncertainty-aware look at Gate B (labelled as such; it is not a
gate and cannot change Gate B's result).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import c1_nrtl_crosscheck as cc  # noqa: E402

MAD_T_LIMIT = 0.6
MAD_Y_LIMIT = 0.03


def main() -> int:
    data = cc.load("lintu2014_101kpa.csv")
    gates = [
        ("C1 Marzal(100) params on Lin&Tu 101.3 kPa", cc.tau_marzal(100), cc.MARZAL_ALPHA),
        ("C2 Barbieri params on Lin&Tu 101.3 kPa (extrapolation)", cc.tau_barbieri, 0.47),
    ]
    print(f"{len(data)} interior points (end points excluded, nothing else excluded)")
    print(f"{'case':58s} {'MAD(T)/K':>9s} {'MAD(y_IPA)':>11s}  gate")
    ok = True
    for label, tau_fn, alpha in gates:
        mt, my = cc.evaluate(data, tau_fn, alpha, cc.psat_wagner)
        passed = mt <= MAD_T_LIMIT and my <= MAD_Y_LIMIT
        ok &= passed
        print(f"{label:58s} {mt:9.3f} {my:11.4f}  {'PASS' if passed else 'FAIL'}")
    mt, my = cc.evaluate(data, cc.tau_lin_tu, cc.LIN_TU_ALPHA, cc.psat_wagner)
    print(f"{'Lin&Tu params on own data (in-sample, informational)':58s} {mt:9.3f} {my:11.4f}")

    print("\nPOST-HOC, not a gate: Gate B residuals measured against the data's own stated")
    print("uncertainty. u(T_calc) from u(x) = U(x)/2 propagated through dT_bubble/dx, combined")
    print("with u(T) = U(T)/2 (Barbieri 60 kPa: U(x_ipa) 0.0215, U(T) 0.073 K).")
    barb60 = cc.load("barbieri2024_60kpa.csv")
    tau, alpha = cc.tau_marzal(60), cc.MARZAL_ALPHA
    z = []
    for p, t_exp, x, _ in barb60:
        t0, _ = cc.bubble(x, p * 1e3, tau, alpha, cc.psat_wagner)
        h = 1e-4
        lo, hi = max(x - h, 1e-9), min(x + h, 1 - 1e-9)
        dtdx = (
            cc.bubble(hi, p * 1e3, tau, alpha, cc.psat_wagner)[0]
            - cc.bubble(lo, p * 1e3, tau, alpha, cc.psat_wagner)[0]
        ) / (hi - lo)
        u = np.hypot(dtdx * 0.0215 / 2, 0.073 / 2)
        z.append((x, (t_exp - t0) / u))
    zs = np.array([abs(v) for _, v in z])
    print(f"  Marzal(60) on Barbieri 60 kPa: |residual|/u median {np.median(zs):.2f}, "
          f"max {zs.max():.2f}, points beyond 2u: {int((zs > 2).sum())}/{len(zs)}")
    print(f"\nGates C1 and C2 both pass: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
