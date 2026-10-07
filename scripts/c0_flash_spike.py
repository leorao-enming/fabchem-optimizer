"""ADR 0001 / Gate C0 feasibility spike: IPA/water isothermal flash, IDAES + IPOPT.

PURPOSE: prove the solver stack (IDAES activity-coefficient property package,
Pyomo, IPOPT) builds, initializes, and solves a nonlinear NRTL VLE problem
reliably, and that the answer agrees with an independent numpy/scipy
implementation of the same equations. This is NOT a thermodynamic
validation of IPA/water.

NRTL PARAMETERS BELOW ARE PLACEHOLDERS: order-of-magnitude plausible
(infinite-dilution activity coefficients of roughly 10 for IPA in water and 4
for water in IPA), unsourced, not fitted to any data. Real parameter
selection (two independent literature sources, applicability-range check,
VLE comparison) is Gate C1 - see docs/model-basis-memo.md section 4. No
number produced by this script may be quoted as IPA/water VLE behavior.

Wagner vapor-pressure coefficients and critical constants are McGarry (1983)
/ Reid-Prausnitz-Poling 4th ed. values (tau, tau^1.5, tau^3, tau^6 form -
the form IDAES implements), read from `chemicals` 1.5.2
`Psat_data_WagnerMcGarry`. Sanity check: water Psat(373.15 K) = 101.28 kPa,
IPA Psat(355 K) = 99.9 kPa (normal boiling point ~355.4 K).

Writes evidence/c0-spike-result.json (gitignored - regenerate, don't commit).
"""

from __future__ import annotations

import json
import platform
import re
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "evidence" / "c0-spike-result.json"

COMPONENTS = ("ipa", "water")
TC = {"ipa": 508.3, "water": 647.35}
PC = {"ipa": 4742440.0, "water": 22122300.0}
MW = {"ipa": 60.09502e-3, "water": 18.01528e-3}
WAGNER = {
    ("ipa", "A"): -8.16927,
    ("ipa", "B"): -0.0943213,
    ("ipa", "C"): -8.1004,
    ("ipa", "D"): 7.85,
    ("water", "A"): -7.76451,
    ("water", "B"): 1.45838,
    ("water", "C"): -2.7758,
    ("water", "D"): -1.23303,
}
NRTL_ALPHA = 0.3  # PLACEHOLDER
NRTL_TAU = {("ipa", "water"): 0.3, ("water", "ipa"): 2.0}  # PLACEHOLDER
PRESSURE_PA = 101325.0

# --------------------------------------------------------------------------
# Independent reference implementation (numpy/scipy only, no IDAES/Pyomo).
# --------------------------------------------------------------------------


def psat_ref(T: float) -> np.ndarray:
    out = []
    for c in COMPONENTS:
        tau = 1.0 - T / TC[c]
        a, b, cc, d = (WAGNER[(c, k)] for k in "ABCD")
        out.append(PC[c] * np.exp((a * tau + b * tau**1.5 + cc * tau**3 + d * tau**6) / (1 - tau)))
    return np.array(out)


def gamma_ref(x: np.ndarray) -> np.ndarray:
    n = len(COMPONENTS)
    t = np.zeros((n, n))
    for i, ci in enumerate(COMPONENTS):
        for j, cj in enumerate(COMPONENTS):
            if i != j:
                t[i, j] = NRTL_TAU[(ci, cj)]
    g = np.exp(-NRTL_ALPHA * t)
    lng = np.zeros(n)
    for i in range(n):
        a_term = sum(x[j] * t[j, i] * g[j, i] for j in range(n)) / sum(
            x[k] * g[k, i] for k in range(n)
        )
        b_term = 0.0
        for j in range(n):
            denom = sum(x[k] * g[k, j] for k in range(n))
            b_term += (x[j] * g[i, j] / denom) * (
                t[i, j] - sum(x[m] * t[m, j] * g[m, j] for m in range(n)) / denom
            )
        lng[i] = a_term + b_term
    return np.exp(lng)


def bubble_T_ref(z: np.ndarray, P: float) -> float:
    return brentq(lambda T: float(np.sum(z * gamma_ref(z) * psat_ref(T)) - P), 300.0, 420.0)


def _x1_roots(f, n: int = 4000) -> list[float]:
    """All roots of f on (0,1), by sign-change scan + brentq (binary system)."""
    grid = np.linspace(1e-9, 1.0 - 1e-9, n)
    vals = [f(g) for g in grid]
    return [
        brentq(f, grid[i], grid[i + 1], xtol=1e-15)
        for i in range(n - 1)
        if vals[i] == 0.0 or vals[i] * vals[i + 1] < 0.0
    ]


def dew_T_ref(z: np.ndarray, P: float) -> float:
    """Dew temperature: outer root in T, inner root in the equilibrium liquid x1."""

    def residual(T: float) -> float:
        ps = psat_ref(T)

        def inner(x1: float) -> float:
            x = np.array([x1, 1.0 - x1])
            return x1 - z[0] * P / (gamma_ref(x)[0] * ps[0])

        roots = _x1_roots(inner, 800)
        if not roots:
            return float("nan")
        x1 = roots[0]
        x = np.array([x1, 1.0 - x1])
        return float(np.sum(z * P / (gamma_ref(x) * ps)) - 1.0)

    lo = bubble_T_ref(z, P) + 1e-4
    ts = np.linspace(lo, 460.0, 400)
    vals = [residual(t) for t in ts]
    for i in range(len(ts) - 1):
        if not (np.isnan(vals[i]) or np.isnan(vals[i + 1])) and vals[i] * vals[i + 1] < 0:
            return brentq(residual, ts[i], ts[i + 1], xtol=1e-12)
    raise RuntimeError("dew point not bracketed")


def flash_ref(T: float, P: float, z: np.ndarray) -> dict:
    """Isothermal flash by solving sum(K_i(x) x_i) = 1 for the liquid x1, then V from the
    material balance. Unlike successive substitution it makes no early single-phase
    decision from the feed composition (that shortcut was a bug in the first version of
    this reference: it declared z=0.5 superheated vapor at T inside the two-phase window).
    """
    ps = psat_ref(T)

    def closure(x1: float) -> float:
        x = np.array([x1, 1.0 - x1])
        return float(np.sum(gamma_ref(x) * ps / P * x) - 1.0)

    candidates = []
    for x1 in _x1_roots(closure):
        x = np.array([x1, 1.0 - x1])
        y = gamma_ref(x) * ps / P * x
        if abs(y[0] - x[0]) < 1e-12:
            continue
        v = (z[0] - x[0]) / (y[0] - x[0])
        if -1e-9 <= v <= 1.0 + 1e-9:
            candidates.append({"V": float(v), "x": x.tolist(), "y": y.tolist()})
    if len(candidates) != 1:
        raise RuntimeError(f"reference flash has {len(candidates)} physical roots at T={T}")
    return candidates[0]


# --------------------------------------------------------------------------
# IDAES model.
# --------------------------------------------------------------------------


def _define_property_package():
    from idaes.core import Component, declare_process_block_class
    from idaes.core.util.misc import extract_data
    from idaes.models.properties.activity_coeff_models.activity_coeff_prop_pack import (
        ActivityCoeffParameterData,
    )
    from pyomo.environ import NonNegativeReals, Param, Set
    from pyomo.environ import units as pyunits

    @declare_process_block_class("IPAWaterParameterBlock")
    class IPAWaterParameterData(ActivityCoeffParameterData):
        def build(self):
            self.component_list_master = Set(initialize=list(COMPONENTS))
            self.ipa = Component()
            self.water = Component()
            super().build()

            self.phase_equilibrium_idx_master = Set(initialize=[1, 2])
            self.phase_equilibrium_idx = Set(initialize=[1, 2])
            self.phase_equilibrium_list_master = {
                1: ["ipa", ("Vap", "Liq")],
                2: ["water", ("Vap", "Liq")],
            }
            self.phase_equilibrium_list = dict(self.phase_equilibrium_list_master)

            self.pressure_reference = Param(
                mutable=True, default=101325, units=pyunits.Pa, doc="Reference pressure"
            )
            self.temperature_reference = Param(
                mutable=True, default=298.15, units=pyunits.K, doc="Reference temperature"
            )
            self.pressure_critical = Param(
                self.component_list,
                within=NonNegativeReals,
                mutable=True,
                initialize=extract_data(PC),
                units=pyunits.Pa,
            )
            self.temperature_critical = Param(
                self.component_list,
                within=NonNegativeReals,
                mutable=True,
                initialize=extract_data(TC),
                units=pyunits.K,
            )
            self.mw_comp = Param(
                self.component_list,
                mutable=True,
                initialize=extract_data(MW),
                units=pyunits.kg / pyunits.mol,
            )
            self.pressure_sat_coeff = Param(
                self.component_list,
                ["A", "B", "C", "D"],
                mutable=False,
                initialize=extract_data(WAGNER),
            )

    # declare_process_block_class injects the *Block class into this module's globals
    return IPAWaterParameterBlock  # noqa: F821


def harden_state_block(st) -> None:
    """Domain-safe bounds on the variables that feed Wagner/NRTL expressions.

    Found necessary by this spike: with IDAES's default (unbounded) variables,
    IPOPT's first Newton step on the Psat/T_bubble/T_dew sub-problem overshoots
    T above the critical temperature, so (Tc-T)/Tc**1.5 is evaluated on a
    negative base and the solve aborts with "can't evaluate pow(-0.07,1.5)".
    Phase flows are also unbounded below, which let IPOPT "solve" to spurious
    points with negative vapor flow. Bounds are far outside the physical
    solution (T ~ 354-368 K here) so they are inactive at the answer; they only
    keep iterates inside the domain of the equations.
    """
    t_ceiling = 0.99 * min(TC.values())
    for var in (st.temperature_bubble, st.temperature_dew, st._temperature_equilibrium, st._t1):
        var.setlb(200.0)
        var.setub(t_ceiling)
    for c in COMPONENTS:
        st.pressure_sat_comp[c].setlb(1.0)
        st.activity_coeff_comp[c].setlb(1e-6)
    for p in ("Liq", "Vap"):
        st.flow_mol_phase[p].setlb(0.0)


def raoult_initial_guess(st, T: float, P: float, z: np.ndarray) -> None:
    """Generic ideal-solution (Raoult's law) starting point - no knowledge of the
    NRTL answer. Sets phase split, compositions, Psat, and bubble/dew temperatures.
    """
    ps = psat_ref(T)
    k = ps / P

    def rr(v: float) -> float:
        return float(np.sum(z * (k - 1.0) / (1.0 + v * (k - 1.0))))

    v = 0.0 if rr(0.0) <= 0 else 1.0 if rr(1.0) >= 0 else brentq(rr, 0.0, 1.0)
    v = min(max(v, 0.05), 0.95)  # stay strictly inside the two-phase region
    x = z / (1.0 + v * (k - 1.0))
    x = x / x.sum()
    y = k * x
    y = y / y.sum()
    t_bub = brentq(lambda tt: float(np.sum(z * psat_ref(tt)) - P), 250.0, 500.0)
    t_dew = brentq(lambda tt: float(P * np.sum(z / psat_ref(tt)) - 1.0), 250.0, 500.0)
    flow = st.flow_mol.value
    st.flow_mol_phase["Vap"].value = v * flow
    st.flow_mol_phase["Liq"].value = (1 - v) * flow
    for i, c in enumerate(COMPONENTS):
        st.mole_frac_phase_comp["Liq", c].value = x[i]
        st.mole_frac_phase_comp["Vap", c].value = y[i]
        st.pressure_sat_comp[c].value = ps[i]
    st.temperature_bubble.value = t_bub
    st.temperature_dew.value = t_dew
    st._temperature_equilibrium.value = T
    st._t1.value = T


def nrtl_aware_start(st, T: float, P: float, z: np.ndarray) -> None:
    """Non-ideality-aware starting point: phase split, compositions, activity
    coefficients, Psat, bubble/dew temperatures all taken from an independent
    1-D flash solve, then handed straight to IPOPT (IDAES's built-in staged
    initialize() is skipped - it assumes ideal gamma=1 in step 2, which is
    infeasible when the real two-phase window sits far below the ideal one).
    """
    ref = flash_ref(T, P, z)
    x, y, v = np.array(ref["x"]), np.array(ref["y"]), ref["V"]
    g = gamma_ref(x)
    ps = psat_ref(T)
    st.flow_mol_phase["Vap"].value = v * st.flow_mol.value
    st.flow_mol_phase["Liq"].value = (1 - v) * st.flow_mol.value
    for i, c in enumerate(COMPONENTS):
        st.mole_frac_phase_comp["Liq", c].value = x[i]
        st.mole_frac_phase_comp["Vap", c].value = y[i]
        st.pressure_sat_comp[c].value = ps[i]
        st.activity_coeff_comp[c].value = g[i]
        st.A[c].value = float(np.log(g[i]))
        st.B[c].value = 0.0
        for cj in COMPONENTS:
            if c != cj:
                st.Gij_coeff[c, cj].value = float(np.exp(-NRTL_ALPHA * NRTL_TAU[(c, cj)]))
    st.temperature_bubble.value = bubble_T_ref(z, P)
    st.temperature_dew.value = dew_T_ref(z, P)
    st._temperature_equilibrium.value = T
    st._t1.value = T


def solve_idaes_flash(
    property_block_cls,
    T: float,
    P: float,
    z_ipa: float,
    harden: bool = True,
    init: str = "idaes",
    eps: tuple[float, float] | None = None,
) -> dict:
    from idaes.core import FlowsheetBlock
    from idaes.core.util.model_statistics import degrees_of_freedom
    from pyomo.common.tee import capture_output
    from pyomo.environ import ConcreteModel, SolverFactory, value

    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    m.fs.props = property_block_cls(
        activity_coeff_model="NRTL", state_vars="FTPz", valid_phase=("Liq", "Vap")
    )
    for i in COMPONENTS:
        for j in COMPONENTS:
            m.fs.props.alpha[i, j].fix(NRTL_ALPHA)
            m.fs.props.tau[i, j].fix(0.0 if i == j else NRTL_TAU[(i, j)])

    m.fs.state = m.fs.props.build_state_block(m.fs.time, defined_state=True)
    st = m.fs.state[0]
    st.flow_mol.fix(1.0)
    st.temperature.fix(T)
    st.pressure.fix(P)
    st.mole_frac_comp["ipa"].fix(z_ipa)
    st.mole_frac_comp["water"].fix(1.0 - z_ipa)

    if harden:
        # force construction of on-demand properties so their variables exist to bound
        st.temperature_bubble, st.temperature_dew, st.pressure_sat_comp  # noqa: B018
        harden_state_block(st)
    if eps is not None:
        st.eps_1.set_value(eps[0])
        st.eps_2.set_value(eps[1])
    zz = np.array([z_ipa, 1.0 - z_ipa])
    if init == "raoult":
        raoult_initial_guess(st, T, P, zz)
    elif init == "nrtl_direct":
        nrtl_aware_start(st, T, P, zz)

    dof = degrees_of_freedom(m)
    t0 = time.perf_counter()
    if init != "nrtl_direct":
        m.fs.state.initialize()
    solver = SolverFactory("ipopt")
    with capture_output() as log:
        results = solver.solve(m, tee=True)
    wall = time.perf_counter() - t0

    match = re.search(r"Number of Iterations\.*:\s*(\d+)", log.getvalue())
    return {
        "dof": dof,
        "status": str(results.solver.status),
        "termination_condition": str(results.solver.termination_condition),
        "ipopt_iterations": int(match.group(1)) if match else None,
        "wall_time_s": wall,
        "V": value(st.flow_mol_phase["Vap"]) / value(st.flow_mol),
        "x": [value(st.mole_frac_phase_comp["Liq", c]) for c in COMPONENTS],
        "y": [value(st.mole_frac_phase_comp["Vap", c]) for c in COMPONENTS],
        "T_bubble": value(st.temperature_bubble),
        "T_dew": value(st.temperature_dew),
    }


def compare(idaes: dict, ref: dict) -> dict:
    return {
        "dV": abs(idaes["V"] - ref["V"]),
        "dx_max": float(np.max(np.abs(np.array(idaes["x"]) - np.array(ref["x"])))),
        "dy_max": float(np.max(np.abs(np.array(idaes["y"]) - np.array(ref["y"])))),
    }


AGREEMENT_TOL = 1e-5


def is_valid(idaes: dict, ref: dict) -> bool:
    """A run only counts as a success if IPOPT says optimal AND the answer is
    physically sane AND it matches the independent reference. IPOPT's
    termination status alone is not evidence (see ADR 0001 result)."""
    if idaes["termination_condition"] != "optimal":
        return False
    if not (0.0 <= idaes["V"] <= 1.0):
        return False
    if not all(0.0 <= v <= 1.0 for v in idaes["x"] + idaes["y"]):
        return False
    return max(compare(idaes, ref).values()) < AGREEMENT_TOL


def run_case(prop_cls, T, P, z_ipa, ref, **kwargs) -> dict:
    try:
        r = solve_idaes_flash(prop_cls, T, P, z_ipa, **kwargs)
    except Exception as exc:  # record failures, don't hide them
        return {"z_ipa": z_ipa, "T": T, "valid": False, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "z_ipa": z_ipa,
        "T": T,
        "valid": is_valid(r, ref),
        "idaes": r,
        "agreement": compare(r, ref),
    }


def smoothing_for_window(window: float) -> tuple[float, float]:
    """IDAES smooth-flash parameters eps_1/eps_2 must be << the two-phase window
    T_dew - T_bubble or the smoothing itself distorts the answer (measured in this
    spike: 7% error in vapor fraction when eps_1 = 0.01 K and the window is 0.017 K)."""
    eps1 = min(0.01, window / 1000.0)
    return eps1, eps1 / 20.0


def evaluate_strategy(prop_cls, scale_eps: bool = False, **kwargs) -> dict:
    """Baseline + 10x cold start + 8-point composition sweep for one strategy."""
    P = PRESSURE_PA

    def case(zi: float, frac: float) -> dict:
        zz = np.array([zi, 1 - zi])
        tbi, tdi = bubble_T_ref(zz, P), dew_T_ref(zz, P)
        Ti = tbi + frac * (tdi - tbi)
        kw = dict(kwargs)
        if scale_eps:
            kw["eps"] = smoothing_for_window(tdi - tbi)
        out = run_case(prop_cls, Ti, P, zi, flash_ref(Ti, P, zz), **kw)
        out["window_K"] = tdi - tbi
        return out

    baseline = case(0.17, 0.4)
    z = np.array([0.17, 0.83])
    baseline["reference"] = flash_ref(baseline["T"], P, z)
    baseline["reference_T_bubble"] = bubble_T_ref(z, P)
    baseline["reference_T_dew"] = dew_T_ref(z, P)

    cold = [case(0.17, 0.4) for _ in range(10)]
    sweep = [case(zi, 0.5) for zi in (0.02, 0.05, 0.10, 0.17, 0.30, 0.50, 0.65, 0.80)]

    walls = [c["idaes"]["wall_time_s"] for c in cold if "idaes" in c]
    return {
        "baseline": baseline,
        "cold_start_x10": {
            "n_valid": sum(c["valid"] for c in cold),
            "n_runs": len(cold),
            "wall_time_s": [round(w, 4) for w in walls],
            "ipopt_iterations": [c["idaes"]["ipopt_iterations"] for c in cold if "idaes" in c],
        },
        "sweep": sweep,
        "summary": {
            "baseline_valid": baseline["valid"],
            "cold_start_valid": f"{sum(c['valid'] for c in cold)}/10",
            "sweep_valid": f"{sum(s['valid'] for s in sweep)}/{len(sweep)}",
            "ipopt_optimal_but_invalid": sum(
                1
                for s in cold + sweep
                if "idaes" in s
                and s["idaes"]["termination_condition"] == "optimal"
                and not s["valid"]
            ),
            "all_valid": bool(
                baseline["valid"]
                and all(c["valid"] for c in cold)
                and all(s["valid"] for s in sweep)
            ),
        },
    }


def main() -> int:
    import idaes
    import pyomo
    from pyomo.environ import SolverFactory

    ipopt = SolverFactory("ipopt")
    # available() only checks that the file exists; version() actually launches it, so a
    # binary with missing shared libraries (seen on Debian 12 slim) is caught here.
    if not ipopt.available(exception_flag=False) or ipopt.version() is None:
        print(
            "ipopt is not available or cannot run - run `idaes get-extensions` "
            "(and on Linux install libgfortran5 liblapack3 libblas3 libgomp1)",
            file=sys.stderr,
        )
        return 2

    prop_cls = _define_property_package()
    report: dict = {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "idaes": idaes.__version__,
            "pyomo": pyomo.version.version,
            "ipopt_version": ".".join(str(v) for v in ipopt.version()),
        },
        "placeholders": "NRTL alpha/tau are unsourced placeholders - solver feasibility only",
        "agreement_tolerance": AGREEMENT_TOL,
    }

    # Strategy 0: IDAES defaults, no bounds - the reproducible failure record.
    P, z = PRESSURE_PA, np.array([0.17, 0.83])
    tb, td = bubble_T_ref(z, P), dew_T_ref(z, P)
    T = tb + 0.4 * (td - tb)
    report["strategy_default_unbounded"] = run_case(
        prop_cls, T, P, 0.17, flash_ref(T, P, z), harden=False
    )
    # Strategy 1: add domain bounds only. Strategy 2: bounds + Raoult's-law start.
    report["strategy_bounds_only"] = evaluate_strategy(prop_cls, harden=True, init="idaes")
    report["strategy_bounds_plus_raoult_init"] = evaluate_strategy(
        prop_cls, harden=True, init="raoult"
    )
    report["strategy_bounds_plus_nrtl_direct"] = evaluate_strategy(
        prop_cls, harden=True, init="nrtl_direct"
    )
    report["strategy_final_nrtl_direct_scaled_eps"] = evaluate_strategy(
        prop_cls, scale_eps=True, harden=True, init="nrtl_direct"
    )

    final = report["strategy_final_nrtl_direct_scaled_eps"]["summary"]
    report["summary"] = {
        "default_unbounded_valid": report["strategy_default_unbounded"]["valid"],
        "bounds_only": report["strategy_bounds_only"]["summary"],
        "bounds_plus_raoult_init": report["strategy_bounds_plus_raoult_init"]["summary"],
        "bounds_plus_nrtl_direct": report["strategy_bounds_plus_nrtl_direct"]["summary"],
        "final_nrtl_direct_scaled_eps": final,
        "passed": bool(final["all_valid"]),
    }
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"wrote {OUTPUT_PATH}")
    return 0 if report["summary"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
