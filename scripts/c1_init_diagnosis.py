"""Why does IDAES's built-in initialize() fail at x_IPA = 0.5? (ADR 0001, Finding 3)

Reproduces two observations with the C0 spike's placeholder NRTL parameters:

1. Per-step IPOPT termination of ActivityCoeffStateBlock.initialize() across a
   composition x temperature grid. Steps 2 and 3 (activity coefficients fixed at
   gamma = 1) are infeasible in EVERY case, including the cases where
   initialize() succeeds overall - IDAES only checks the last step.
2. Why steps 2-3 cannot be feasible: T_bubble is built from NRTL activity
   coefficients at the feed composition, but step 2 flashes with gamma = 1. At
   that NRTL T_bubble the gamma = 1 liquid is subcooled (sum z_i Psat_i / P < 1
   at V = 0), so no solution exists for any composition.

Not diagnosed: why step 4 (NRTL restored) recovers from the leftover iterate for
most (z, T) but not in a band around x_IPA = 0.5. Placeholder parameters only -
re-run with the sourced NRTL sets in C1 before drawing any conclusion about
IPA/water itself.

Usage: python scripts/c1_init_diagnosis.py
"""

from __future__ import annotations

import contextlib
import io
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import c0_flash_spike as s  # noqa: E402

GRID_Z = (0.17, 0.30, 0.40, 0.50, 0.60)
GRID_F = (0.25, 0.50, 0.90)  # fraction of the way from T_bubble to T_dew


def build(T: float, z: float, prop_cls):
    from idaes.core import FlowsheetBlock
    from pyomo.environ import ConcreteModel

    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    m.fs.props = prop_cls(
        activity_coeff_model="NRTL", state_vars="FTPz", valid_phase=("Liq", "Vap")
    )
    for i in s.COMPONENTS:
        for j in s.COMPONENTS:
            m.fs.props.alpha[i, j].fix(s.NRTL_ALPHA)
            m.fs.props.tau[i, j].fix(0.0 if i == j else s.NRTL_TAU[(i, j)])
    m.fs.state = m.fs.props.build_state_block(m.fs.time, defined_state=True)
    st = m.fs.state[0]
    st.flow_mol.fix(1.0)
    st.temperature.fix(T)
    st.pressure.fix(s.PRESSURE_PA)
    st.mole_frac_comp["ipa"].fix(z)
    st.mole_frac_comp["water"].fix(1.0 - z)
    st.temperature_bubble, st.temperature_dew, st.pressure_sat_comp  # noqa: B018
    s.harden_state_block(st)
    return m


def init_step_statuses(z: float, frac: float, prop_cls) -> list[str]:
    import idaes.models.properties.activity_coeff_models.activity_coeff_prop_pack as mod

    zz = np.array([z, 1.0 - z])
    t_bub, t_dew = s.bubble_T_ref(zz, s.PRESSURE_PA), s.dew_T_ref(zz, s.PRESSURE_PA)
    m = build(t_bub + frac * (t_dew - t_bub), z, prop_cls)

    record: list[str] = []
    original = mod.solve_indexed_blocks

    def recording(*args, **kwargs):
        result = original(*args, **kwargs)
        record.append(str(result.solver.termination_condition))
        return result

    mod.solve_indexed_blocks = recording
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                m.fs.state.initialize()
            except Exception:  # InitializationError is the expected failure; steps are recorded
                pass
    finally:
        mod.solve_indexed_blocks = original
    return record


def main() -> int:
    logging.disable(logging.CRITICAL)
    prop_cls = s._define_property_package()

    print("Per-step IPOPT termination of initialize() (steps 1..5):")
    always_infeasible_2_3 = True
    for z in GRID_Z:
        for f in GRID_F:
            steps = init_step_statuses(z, f, prop_cls)
            overall = "OK" if steps and steps[-1] == "optimal" else "FAIL"
            always_infeasible_2_3 &= steps[1:3] == ["infeasible", "infeasible"]
            short = ["opt" if x == "optimal" else "INF" for x in steps]
            print(f"  x_IPA={z:.2f} frac={f:.2f}: {' '.join(short)} -> initialize {overall}")
    print(f"Steps 2 and 3 infeasible in every case: {always_infeasible_2_3}")

    print("\nIdeal-gamma flash at the NRTL T_bubble (feasible at V=0 only if sum >= 1):")
    for z in GRID_Z:
        zz = np.array([z, 1.0 - z])
        t_bub = s.bubble_T_ref(zz, s.PRESSURE_PA)
        total = float(np.sum(zz * s.psat_ref(t_bub)) / s.PRESSURE_PA)
        print(f"  x_IPA={z:.2f}: T_bubble(NRTL)={t_bub:.2f} K  sum(z*Psat)/P={total:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
