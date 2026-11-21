"""Initializer for `fabchem.nrtl_tdep` flash states that knows about T-dependent NRTL.

IDAES's own `initialize()` is not used. ADR 0001 (addendum) found that its steps 2-3 solve
the flash with gamma = 1 at an NRTL-derived bubble temperature where the ideal liquid is
subcooled, so they are infeasible in every case, and the outcome then depends on whether
step 4 recovers from a leftover infeasible point. It also knows nothing about tau(T).

Instead, for each state block:

1. solve the same flash with the independent numpy reference (`fabchem.ipa_water.flash`);
2. load that solution, including gamma, the NRTL intermediates A/B/G at the equilibrium
   temperature and the bubble/dew temperatures, as the IPOPT starting point;
3. set the smooth-flash parameters relative to the local two-phase window (ADR 0001
   Finding 4: IDAES's default eps_1 = 0.01 K is larger than the window near the azeotrope
   and distorts the answer);
4. solve once with IPOPT.

T_bubble and T_dew are functions of the feed composition only, so they are always taken
from the feed, whatever the phase state; vapor pressures are evaluated at the equilibrium
temperature. (A first version of this module guessed T-1 / T-0.5 K for single-phase
points; that was wrong and is recorded in the CHANGELOG.)

The starting point comes from the same reference that the C1 check scripts compare
against, so a check that only starts from it would be weak. `perturb` exists so the checks
can also start IPOPT away from the reference answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import brentq

from fabchem.ipa_water import COMPONENTS, NRTLSet, flash, psat

DEFAULT_SOLVER_OPTIONS = {"tol": 1e-10, "max_iter": 200}


def smoothing_for_window(window_k: float) -> tuple[float, float]:
    """(eps_1, eps_2) for IDAES's smooth flash, well below the two-phase window [K]."""
    eps1 = min(0.01, max(window_k, 1e-9) / 1000.0)
    return eps1, eps1 / 20.0


def nrtl_terms(x: np.ndarray, T: float, nrtl: NRTLSet) -> dict[str, np.ndarray]:
    """IDAES's NRTL intermediates (G, A, B) in its general multicomponent form."""
    t12, t21 = nrtl.tau(T)
    tau = np.array([[0.0, t12], [t21, 0.0]])
    G = np.exp(-nrtl.alpha * tau)
    n = len(COMPONENTS)
    A = np.zeros(n)
    B = np.zeros(n)
    for i in range(n):
        A[i] = sum(x[j] * tau[j, i] * G[j, i] for j in range(n)) / sum(
            x[k] * G[k, i] for k in range(n)
        )
        for j in range(n):
            den = sum(x[k] * G[k, j] for k in range(n))
            B[i] += (x[j] * G[i, j] / den) * (
                tau[i, j] - sum(x[m] * tau[m, j] * G[m, j] for m in range(n)) / den
            )
    return {"G": G, "A": A, "B": B}


@dataclass(frozen=True)
class Perturbation:
    """Offsets applied to the reference start (for checks, not for normal use)."""

    temperature_k: float = 0.0  # added to T_bubble, T_dew, T_eq
    gamma_rel: float = 0.0  # gamma multiplied by (1 + gamma_rel)
    vapor_fraction: float = 0.0  # added to V, clipped to [0.01, 0.99] if nonzero


def load_reference_start(st: Any, nrtl: NRTLSet, perturb: Perturbation | None = None) -> dict:
    """Set every unfixed variable of a flash state block from the reference solution.

    Returns the reference state (as a dict) so callers can compare against it.
    """
    T = float(st.temperature.value)
    P = float(st.pressure.value)
    z = float(st.mole_frac_comp["ipa"].value)
    ref = flash(T, P, z, nrtl)
    p = perturb or Perturbation()

    eps1, eps2 = smoothing_for_window(ref.T_dew - ref.T_bubble)
    st.eps_1.set_value(eps1)
    st.eps_2.set_value(eps2)

    v = ref.V
    if p.vapor_fraction:
        v = min(max(v + p.vapor_fraction, 0.01), 0.99)
    t_eq = ref.T_eq + p.temperature_k
    x = np.array(ref.x)
    terms = nrtl_terms(x, t_eq, nrtl)
    g = np.exp(terms["A"] + terms["B"]) * (1.0 + p.gamma_rel)
    ps = psat(t_eq)

    flow = float(st.flow_mol.value)
    st.flow_mol_phase["Vap"].set_value(v * flow)
    st.flow_mol_phase["Liq"].set_value((1.0 - v) * flow)
    for i, c in enumerate(COMPONENTS):
        st.mole_frac_phase_comp["Liq", c].set_value(ref.x[i])
        st.mole_frac_phase_comp["Vap", c].set_value(ref.y[i])
        st.pressure_sat_comp[c].set_value(ps[i])
        st.activity_coeff_comp[c].set_value(g[i])
        st.A[c].set_value(terms["A"][i])
        st.B[c].set_value(terms["B"][i])
        for j, cj in enumerate(COMPONENTS):
            if c != cj:
                st.Gij_coeff[c, cj].set_value(terms["G"][i, j])
    # IDAES's dew equation uses the flash liquid's gamma, not gamma at the incipient dew
    # liquid (ADR 0001 Finding 7), so its T_dew equals the true dew point only when the state
    # is at or above it. Start from the value IDAES's own equation gives.
    zz = np.array([z, 1.0 - z])
    t_dew_idaes = brentq(
        lambda t: float(np.sum(zz * P / (g * psat(t)))) - 1.0, ref.T_bubble - 30.0, ref.T_dew + 30.0
    )
    st.temperature_bubble.set_value(ref.T_bubble + p.temperature_k)
    st.temperature_dew.set_value(t_dew_idaes + p.temperature_k)
    st._temperature_equilibrium.set_value(t_eq)
    st._t1.set_value(max(T, ref.T_bubble) + p.temperature_k)
    st._T_nrtl.set_value(t_eq)
    return {
        "V": ref.V,
        "x": list(ref.x),
        "y": list(ref.y),
        "T_eq": ref.T_eq,
        "T_bubble": ref.T_bubble,
        "T_dew": ref.T_dew,
    }


def initialize_flash(
    m: Any,
    st: Any,
    nrtl: NRTLSet,
    perturb: Perturbation | None = None,
    solver_options: dict | None = None,
) -> dict:
    """Load the reference start into `st` and solve `m` once with IPOPT.

    Returns {"termination_condition", "ipopt_iterations", "reference"}. Does not raise on a
    non-optimal termination: the caller decides, and a check must also compare the answer
    against the reference (an IPOPT "optimal" alone is not a pass, ADR 0001 Finding 2).
    """
    import re

    from pyomo.common.tee import capture_output
    from pyomo.environ import SolverFactory

    reference = load_reference_start(st, nrtl, perturb)
    solver = SolverFactory("ipopt")
    solver.options.update(solver_options or DEFAULT_SOLVER_OPTIONS)
    with capture_output() as log:
        results = solver.solve(m, tee=True, load_solutions=False)
    term = str(results.solver.termination_condition)
    if term == "optimal":
        m.solutions.load_from(results)
    match = re.search(r"Number of Iterations\.*:\s*(\d+)", log.getvalue())
    return {
        "termination_condition": term,
        "ipopt_iterations": int(match.group(1)) if match else None,
        "reference": reference,
    }


def state_summary(st: Any) -> dict:
    """The comparable outputs of a solved flash state block."""
    from pyomo.environ import value

    return {
        "V": value(st.flow_mol_phase["Vap"]) / value(st.flow_mol),
        "x": [value(st.mole_frac_phase_comp["Liq", c]) for c in COMPONENTS],
        "y": [value(st.mole_frac_phase_comp["Vap", c]) for c in COMPONENTS],
        "T_eq": value(st._temperature_equilibrium),
        "T_bubble": value(st.temperature_bubble),
        "T_dew": value(st.temperature_dew),
    }


AGREEMENT_TOL = 1e-5


def agreement(solved: dict, reference: dict) -> dict:
    """Max absolute differences in V, x, y (mole fraction) and T_bubble (K).

    T_dew is deliberately not compared: IDAES's T_dew is the true dew point only for states
    at or above it (ADR 0001 Finding 7); see `dew_offset`.
    """
    return {
        "dV": abs(solved["V"] - reference["V"]),
        "dx": max(abs(a - b) for a, b in zip(solved["x"], reference["x"], strict=True)),
        "dy": max(abs(a - b) for a, b in zip(solved["y"], reference["y"], strict=True)),
        "dT_bubble": abs(solved["T_bubble"] - reference["T_bubble"]),
    }


def dew_offset(solved: dict, reference: dict) -> float:
    """IDAES T_dew minus the true dew temperature [K] (informational, Finding 7)."""
    return float(solved["T_dew"] - reference["T_dew"])


PHYSICAL_SLACK = 1e-9


def is_valid(termination: str, solved: dict, reference: dict) -> bool:
    """optimal AND physically sane AND agrees with the independent reference (V, x, y, T_bubble).

    "Physically sane" allows PHYSICAL_SLACK, the same slack the reference flash uses: a
    superheated state solves to V = 1 + ~1e-11 (liquid flow ~1e-23, total balance satisfied
    to IPOPT's tolerance), which is not a wrong answer. Added after the first run of
    scripts/c1_tdep_init_check.py failed 3/140 states for exactly this reason (CHANGELOG).
    """
    if termination != "optimal":
        return False
    lo, hi = -PHYSICAL_SLACK, 1.0 + PHYSICAL_SLACK
    if not lo <= solved["V"] <= hi:
        return False
    if not all(lo <= v <= hi for v in solved["x"] + solved["y"]):
        return False
    return max(agreement(solved, reference).values()) < AGREEMENT_TOL
