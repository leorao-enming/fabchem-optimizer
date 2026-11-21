"""Unit tests for fabchem.ipa_water: parameter transcription/conventions and the reference.

The conventions are checked against numbers the papers print themselves, not against this
implementation: a component-order or unit mix-up in a parameter set changes these numbers
by far more than the tolerances used here.
"""

import numpy as np
import pytest

from fabchem import ipa_water as w


@pytest.mark.parametrize(
    ("nrtl", "t_water_boil", "gamma_water_inf", "gamma_ipa_inf"),
    [
        # Marzal 1996 Table 7 (NRTL rows): gamma_1^inf (water) and gamma_2^inf (2-propanol).
        # The paper does not state the temperature; evaluating both at the pure-water boiling
        # point it reports (Tables 3-5) reproduces all six values to 0.3 %. Evaluating at the
        # IPA boiling point instead misses gamma_ipa_inf by ~12 %, so the test discriminates.
        (w.MARZAL_1996_30, 342.33, 3.33, 11.06),
        (w.MARZAL_1996_60, 359.14, 3.30, 10.46),
        (w.MARZAL_1996_100, 372.78, 3.22, 9.51),
    ],
)
def test_marzal_infinite_dilution_gammas_match_paper(
    nrtl, t_water_boil, gamma_water_inf, gamma_ipa_inf
):
    g_ipa, g_water = w.gamma_infinite_dilution(t_water_boil, nrtl)
    assert g_ipa == pytest.approx(gamma_ipa_inf, rel=0.01)
    assert g_water == pytest.approx(gamma_water_inf, rel=0.01)


def test_component_swap_would_be_caught():
    """Mutation check for the test above: swapping Marzal's component order fails it."""
    s = w.MARZAL_1996_60
    swapped = w.NRTLSet(s.key, s.citation, s.alpha, s.a, (s.b[1], s.b[0]), (60, 60), "")
    g_ipa, g_water = w.gamma_infinite_dilution(359.14, swapped)
    assert g_ipa != pytest.approx(10.46, rel=0.01)
    assert g_water != pytest.approx(3.30, rel=0.01)


@pytest.mark.parametrize(("p_kpa", "t_azeo_paper"), [(60.0, 340.9), (80.0, 347.6)])
def test_barbieri_azeotrope_temperature_matches_paper(p_kpa, t_azeo_paper):
    """Barbieri 2024 reports minimum-boiling azeotropes near 340.9 K and 347.6 K."""
    xs = np.linspace(0.4, 0.95, 221)
    t_min = min(w.bubble(x, p_kpa * 1e3, w.BARBIERI_2024)[0] for x in xs)
    assert t_min == pytest.approx(t_azeo_paper, abs=0.3)


def test_barbieri_tau_form():
    t12, t21 = w.BARBIERI_2024.tau(350.0)
    assert t12 == pytest.approx(-1.39470283 + 627.160288 / 350.0)
    assert t21 == pytest.approx(4.50009825 - 791.079743 / 350.0)


def test_pure_component_vapor_pressures():
    """Wagner constants: water boils at 373.15 K (101.3 kPa), IPA near 355.4 K."""
    assert w.psat(373.15)[1] == pytest.approx(101325.0, rel=0.002)
    assert w.psat(355.4)[0] == pytest.approx(101325.0, rel=0.01)


@pytest.mark.parametrize("z", [0.05, 0.3, 0.7, 0.95])
@pytest.mark.parametrize("nrtl", [w.BARBIERI_2024, w.MARZAL_1996_60, w.LIN_TU_2014])
def test_reference_flash_is_consistent(nrtl, z):
    P = 80e3
    t_bub, y_bub = w.bubble(z, P, nrtl)
    t_dew, x_dew = w.dew(z, P, nrtl)
    assert t_bub < t_dew

    mid = w.flash(0.5 * (t_bub + t_dew), P, z, nrtl)
    assert 0.0 < mid.V < 1.0
    # component balance
    assert (1 - mid.V) * mid.x[0] + mid.V * mid.y[0] == pytest.approx(z, abs=1e-10)
    # equilibrium: y_i P = x_i gamma_i Psat_i
    g = w.gamma(mid.x[0], mid.T_eq, nrtl)
    ps = w.psat(mid.T_eq)
    for i in range(2):
        assert mid.y[i] * P == pytest.approx(mid.x[i] * g[i] * ps[i], rel=1e-8)

    # continuity at the phase boundaries (offset relative to the window: near the azeotrope
    # the window is a few mK wide and V moves very fast with T)
    eps = 1e-7 * (t_dew - t_bub)
    near_bub = w.flash(t_bub + eps, P, z, nrtl)
    near_dew = w.flash(t_dew - eps, P, z, nrtl)
    assert near_bub.V == pytest.approx(0.0, abs=1e-4)
    assert near_bub.y[0] == pytest.approx(y_bub, abs=1e-4)
    assert near_dew.V == pytest.approx(1.0, abs=1e-4)
    assert near_dew.x[0] == pytest.approx(x_dew, abs=1e-4)


def test_single_phase_states_report_incipient_phase():
    P, z, s = 60e3, 0.5, w.BARBIERI_2024
    t_bub, y_bub = w.bubble(z, P, s)
    t_dew, x_dew = w.dew(z, P, s)
    sub = w.flash(t_bub - 5.0, P, z, s)
    sup = w.flash(t_dew + 5.0, P, z, s)
    assert (sub.V, sub.x[0], sub.y[0], sub.T_eq) == (0.0, z, y_bub, t_bub)
    assert (sup.V, sup.y[0], sup.x[0], sup.T_eq) == (1.0, z, x_dew, t_dew)
