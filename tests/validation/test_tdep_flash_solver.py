"""Solver-dependent checks of the T-dependent flash (skipped when IPOPT is unavailable).

A small subset of scripts/c1_tdep_nrtl_check.py and scripts/c1_tdep_init_check.py, so that
the manual solver workflow (.github/workflows/solver.yml) exercises them on every run.
"""

import logging

import pytest

from fabchem import ipa_water as w


def _ipopt_runs() -> bool:
    try:
        import idaes  # noqa: F401  (puts the IDAES extensions directory on PATH)
        from pyomo.environ import SolverFactory

        s = SolverFactory("ipopt")
        return bool(s.available(exception_flag=False)) and s.version() is not None
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _ipopt_runs(), reason="IPOPT not available")


@pytest.mark.parametrize("state", ["subcooled", "window_50", "superheated"])
@pytest.mark.parametrize(
    ("nrtl", "P"), [(w.BARBIERI_2024, 60e3), (w.MARZAL_1996_60, 60e3), (w.LIN_TU_2014, 101325.0)]
)
@pytest.mark.parametrize("perturbed", [False, True])
def test_flash_agrees_with_reference(nrtl, P, state, perturbed):
    from fabchem.nrtl_start import Perturbation, initialize_flash, is_valid, state_summary
    from fabchem.nrtl_tdep import build_flash_model

    logging.disable(logging.WARNING)
    z = 0.4
    t_bub, _ = w.bubble(z, P, nrtl)
    t_dew, _ = w.dew(z, P, nrtl)
    T = {"subcooled": t_bub - 5.0, "window_50": 0.5 * (t_bub + t_dew), "superheated": t_dew + 5.0}[
        state
    ]
    m, st = build_flash_model(nrtl, T, P, z)
    pert = Perturbation(temperature_k=2.0, gamma_rel=0.1, vapor_fraction=0.1) if perturbed else None
    r = initialize_flash(m, st, nrtl, pert)
    assert is_valid(r["termination_condition"], state_summary(st), r["reference"])
