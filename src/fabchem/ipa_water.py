"""IPA/water constants, sourced NRTL parameter sets, and an independent numpy VLE reference.

Nothing in this module imports IDAES or Pyomo. The functions here are the *independent*
reference that IDAES results are checked against (ADR 0001: an IPOPT "optimal" status is
not evidence on its own), and the source of the non-ideality-aware starting point used by
`fabchem.nrtl_start`.

Component order everywhere: (ipa, water). The vapor phase is ideal and the Poynting factor
is 1, as in the IDAES activity-coefficient package and in the papers' own regressions.

Pure-component data: Wagner vapor-pressure constants and critical constants are McGarry
(1983) / Reid-Prausnitz-Poling 4th ed. values (the tau, tau^1.5, tau^3, tau^6 form IDAES
implements), the same numbers as `scripts/c0_flash_spike.py`.

NRTL sets: every published form is mapped onto one convention,

    tau_ij(T) = a_ij + b_ij / T,   G_ij = exp(-alpha * tau_ij),

with i, j in (ipa, water). The mapping from each paper's own notation is spelled out next to
each set below; the parameter values are transcriptions of the papers' tables
(see docs/model-basis-memo.md section 4 for how each was checked).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import brentq

COMPONENTS = ("ipa", "water")
R_GAS = 8.314462618  # J/(mol K)

TC = {"ipa": 508.3, "water": 647.35}  # K
PC = {"ipa": 4742440.0, "water": 22122300.0}  # Pa
MW = {"ipa": 60.09502e-3, "water": 18.01528e-3}  # kg/mol
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


@dataclass(frozen=True)
class NRTLSet:
    """One published NRTL parameter set, in the tau_ij = a_ij + b_ij/T convention.

    `a` and `b` are (ipa->water, water->ipa), i.e. (tau_12, tau_21) with 1 = IPA.
    `fitted_pressure_kpa` is the isobaric pressure range the authors regressed on; use
    outside it is extrapolation and must be labelled as such.
    """

    key: str
    citation: str
    alpha: float
    a: tuple[float, float]
    b: tuple[float, float]
    fitted_pressure_kpa: tuple[float, float]
    note: str

    def tau(self, T: float) -> tuple[float, float]:
        """(tau_ipa_water, tau_water_ipa) at temperature T [K]."""
        return self.a[0] + self.b[0] / T, self.a[1] + self.b[1] / T


# Barbieri, De Guido, Moioli, J. Chem. Thermodyn. 198 (2024) 107342, Table 7.
# Paper: tau_ij = a_ij + b_ij/T, alpha = 0.47 fixed, component 1 = 2-propanol. b printed with
# unit "1/K"; with this functional form it must be K (inferred, see memo).
BARBIERI_2024 = NRTLSet(
    key="barbieri2024",
    citation="Barbieri, De Guido, Moioli, J. Chem. Thermodyn. 198 (2024) 107342, Table 7",
    alpha=0.47,
    a=(-1.39470283, 4.50009825),
    b=(627.160288, -791.079743),
    fitted_pressure_kpa=(60.0, 80.0),
    note="Aspen Plus V14 regression on the authors' own 60/80 kPa data (~341-367 K).",
)


def _marzal(p_kpa: float, a12_water_ipa: float, a21_ipa_water: float) -> NRTLSet:
    # Paper: tau_ij = A_ij/(R T), A in J/mol, alpha = 0.30 fixed, component 1 = WATER.
    # So tau_ipa,water = A21/(R T) and tau_water,ipa = A12/(R T).
    return NRTLSet(
        key=f"marzal1996_{int(p_kpa)}kpa",
        citation="Marzal, Monton, Rodrigo, J. Chem. Eng. Data 41 (1996) 608, Table 7 (NRTL)",
        alpha=0.30,
        a=(0.0, 0.0),
        b=(a21_ipa_water / R_GAS, a12_water_ipa / R_GAS),
        fitted_pressure_kpa=(p_kpa, p_kpa),
        note=f"Fitted to the authors' {int(p_kpa)} kPa isobaric data only.",
    )


MARZAL_1996_30 = _marzal(30.0, 6726.08, 111.46)
MARZAL_1996_60 = _marzal(60.0, 6899.21, 106.99)
MARZAL_1996_100 = _marzal(100.0, 6900.81, 77.49)

# Lin & Tu, Fluid Phase Equilib. 368 (2014) 104-111, Table 5, 2-propanol (1) + water (2).
# Paper: tau_ij = A_ij/T, A in K, alpha = 0.3, 101.3 kPa only. Read after the C1 cross-lab
# gates were frozen and run, so it is informational there, not a gate.
LIN_TU_2014 = NRTLSet(
    key="lintu2014",
    citation="Lin & Tu, Fluid Phase Equilib. 368 (2014) 104-111, Table 5",
    alpha=0.30,
    a=(0.0, 0.0),
    b=(-6.2261, 850.77),
    fitted_pressure_kpa=(101.3, 101.3),
    note="Fitted at 101.3 kPa only.",
)

NRTL_SETS: dict[str, NRTLSet] = {
    s.key: s for s in (BARBIERI_2024, MARZAL_1996_30, MARZAL_1996_60, MARZAL_1996_100, LIN_TU_2014)
}


# --------------------------------------------------------------------------------------
# Independent reference (numpy/scipy only).
# --------------------------------------------------------------------------------------


def psat(T: float) -> np.ndarray:
    """Wagner vapor pressures [Pa] of (ipa, water) at T [K]."""
    out = []
    for c in COMPONENTS:
        tau = 1.0 - T / TC[c]
        a, b, cc, d = (WAGNER[(c, k)] for k in "ABCD")
        out.append(PC[c] * np.exp((a * tau + b * tau**1.5 + cc * tau**3 + d * tau**6) / (1 - tau)))
    return np.array(out)


def gamma(x_ipa: float, T: float, nrtl: NRTLSet) -> np.ndarray:
    """Binary NRTL activity coefficients (ipa, water), closed form."""
    t12, t21 = nrtl.tau(T)
    g12, g21 = np.exp(-nrtl.alpha * t12), np.exp(-nrtl.alpha * t21)
    x1, x2 = x_ipa, 1.0 - x_ipa
    ln1 = x2**2 * (t21 * (g21 / (x1 + x2 * g21)) ** 2 + t12 * g12 / (x2 + x1 * g12) ** 2)
    ln2 = x1**2 * (t12 * (g12 / (x2 + x1 * g12)) ** 2 + t21 * g21 / (x1 + x2 * g21) ** 2)
    return np.exp([ln1, ln2])


def gamma_infinite_dilution(T: float, nrtl: NRTLSet) -> tuple[float, float]:
    """(gamma_ipa in water, gamma_water in IPA) at infinite dilution, both at T."""
    t12, t21 = nrtl.tau(T)
    g12, g21 = np.exp(-nrtl.alpha * t12), np.exp(-nrtl.alpha * t21)
    return float(np.exp(t21 + t12 * g12)), float(np.exp(t12 + t21 * g21))


def _bracket_root(f: Callable[[Any], Any], lo: float, hi: float, n: int) -> list[float]:
    """All roots of f on [lo, hi] found by a sign-change scan, each refined with brentq.

    `f` must accept a numpy array (vectorized scan) as well as a float (refinement).
    """
    grid = np.linspace(lo, hi, n)
    vals = np.asarray(f(grid), dtype=float)
    idx = np.nonzero((vals[:-1] == 0.0) | (vals[:-1] * vals[1:] < 0.0))[0]
    return [brentq(lambda t: float(f(t)), grid[i], grid[i + 1], xtol=1e-14) for i in idx]


def bubble(z_ipa: float, P: float, nrtl: NRTLSet) -> tuple[float, float]:
    """Bubble temperature [K] and incipient vapor y_ipa of liquid z at pressure P [Pa]."""
    x = np.array([z_ipa, 1.0 - z_ipa])

    def f(T: float) -> float:
        return float(np.sum(x * gamma(z_ipa, T, nrtl) * psat(T)) - P)

    T = brentq(f, 250.0, 0.99 * min(TC.values()), xtol=1e-12)
    y_ipa = float(x[0] * gamma(z_ipa, T, nrtl)[0] * psat(T)[0] / P)
    return T, y_ipa


def dew(z_ipa: float, P: float, nrtl: NRTLSet) -> tuple[float, float]:
    """Dew temperature [K] and incipient liquid x_ipa of vapor z at pressure P [Pa].

    Solved as two equations in (x1, T): x_i gamma_i(x, T) Psat_i(T) = z_i P. The outer root
    is in T; the inner one finds the liquid x1 that satisfies the IPA equation at that T.
    """
    z = np.array([z_ipa, 1.0 - z_ipa])

    def liquid_x1(T: float) -> float | None:
        # x1 * gamma_1(x1) is increasing in x1 for this fully miscible pair, so the root is
        # unique when it exists.
        ps = psat(T)

        def inner(x1: Any) -> Any:
            return x1 * gamma(x1, T, nrtl)[0] * ps[0] - z[0] * P

        roots = _bracket_root(inner, 1e-12, 1.0 - 1e-12, 2000)
        return roots[0] if roots else None

    def residual(T: float) -> float:
        x1 = liquid_x1(T)
        if x1 is None:
            return float("nan")
        return float((1.0 - x1) * gamma(x1, T, nrtl)[1] * psat(T)[1] - z[1] * P)

    t_bub, _ = bubble(z_ipa, P, nrtl)
    ts = np.linspace(t_bub + 1e-6, t_bub + 60.0, 241)
    vals = [residual(t) for t in ts]
    for i in range(len(ts) - 1):
        a, b = vals[i], vals[i + 1]
        if not (np.isnan(a) or np.isnan(b)) and a * b <= 0.0:
            T = brentq(residual, ts[i], ts[i + 1], xtol=1e-12)
            x1 = liquid_x1(T)
            assert x1 is not None
            return T, x1
    raise RuntimeError(f"dew point not bracketed for z_ipa={z_ipa}, P={P}")


@dataclass(frozen=True)
class FlashState:
    """Equilibrium state of an isothermal flash, in the form IDAES reports it.

    For a single-phase feed IDAES's smooth formulation puts the equilibrium temperature at
    the bubble (subcooled) or dew (superheated) point and still reports the incipient
    second phase's composition; this reference does the same so the two are comparable.
    """

    V: float
    x: tuple[float, float]
    y: tuple[float, float]
    T_eq: float
    T_bubble: float
    T_dew: float


def flash(T: float, P: float, z_ipa: float, nrtl: NRTLSet) -> FlashState:
    """Isothermal flash at T [K], P [Pa] of feed z_ipa, without any early phase decision.

    Inside the two-phase window it solves sum_i K_i(x, T) x_i = 1 for the liquid x1 (a 1-D
    root problem) and takes V from the material balance; the first version of the C0
    reference made a phase decision from the feed composition and was wrong (ADR 0001).
    """
    t_bub, y_bub = bubble(z_ipa, P, nrtl)
    t_dew, x_dew = dew(z_ipa, P, nrtl)
    if T <= t_bub:
        return FlashState(0.0, (z_ipa, 1 - z_ipa), (y_bub, 1 - y_bub), t_bub, t_bub, t_dew)
    if T >= t_dew:
        return FlashState(1.0, (x_dew, 1 - x_dew), (z_ipa, 1 - z_ipa), t_dew, t_bub, t_dew)

    ps = psat(T)

    def closure(x1: Any) -> Any:
        g = gamma(x1, T, nrtl)
        return (g[0] * ps[0] * x1 + g[1] * ps[1] * (1.0 - x1)) / P - 1.0

    candidates = []
    for x1 in _bracket_root(closure, 1e-12, 1.0 - 1e-12, 4000):
        y1 = float(x1 * gamma(x1, T, nrtl)[0] * ps[0] / P)
        if abs(y1 - x1) < 1e-12:
            continue
        v = (z_ipa - x1) / (y1 - x1)
        if -1e-9 <= v <= 1.0 + 1e-9:
            candidates.append(FlashState(float(v), (x1, 1 - x1), (y1, 1 - y1), T, t_bub, t_dew))
    if len(candidates) != 1:
        raise RuntimeError(f"reference flash has {len(candidates)} physical roots at T={T}")
    return candidates[0]
