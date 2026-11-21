"""Structure of the T-dependent NRTL package: each equation group sees its own temperature.

These tests build the IDAES model but never call a solver, so they run in the fast CI job
(which installs idaes-pse but not the IPOPT binary).
"""

import pytest
from pyomo.core.expr.visitor import identify_variables
from pyomo.environ import Constraint

from fabchem import ipa_water as w
from fabchem.nrtl_tdep import IPAWaterTdepStateBlockData, build_flash_model

TEMPERATURE_NAMES = ("temperature", "_T_nrtl", "temperature_bubble", "temperature_dew")


def temperatures_in(expr) -> set[str]:
    """Which of the state block's temperature variables an expression contains."""
    return {
        v.parent_component().local_name
        for v in identify_variables(expr)
        if v.parent_component().local_name in TEMPERATURE_NAMES
    }


@pytest.fixture(scope="module")
def flash():
    return build_flash_model(w.BARBIERI_2024, 345.0, 60e3, 0.5)


def test_fully_specified(flash):
    from idaes.core.util.model_statistics import degrees_of_freedom

    m, _ = flash
    assert degrees_of_freedom(m) == 0


def test_params_tau_is_not_used_anywhere(flash):
    m, _ = flash
    taus = {id(m.fs.props.tau[i, j]) for i in w.COMPONENTS for j in w.COMPONENTS}
    for c in m.component_data_objects(Constraint, active=True):
        assert not taus & {id(v) for v in identify_variables(c.body)}, c.name


def test_flash_nrtl_uses_equilibrium_temperature(flash):
    _, st = flash
    for i, j in (("ipa", "water"), ("water", "ipa")):
        assert temperatures_in(st.eq_Gij_coeff[i, j].body) == {"_T_nrtl"}
    for c in w.COMPONENTS:
        assert "_T_nrtl" in temperatures_in(st.eq_A[c].body)
        assert "_T_nrtl" in temperatures_in(st.eq_B[c].body)
    link = temperatures_in(st._T_nrtl_link.body)
    assert link == {"_T_nrtl"}  # the other side is _temperature_equilibrium
    assert "_temperature_equilibrium" in {
        v.parent_component().local_name for v in identify_variables(st._T_nrtl_link.body)
    }


def test_bubble_uses_bubble_temperature(flash):
    _, st = flash
    for c in w.COMPONENTS:
        assert temperatures_in(st.A_bubble[c]) == {"temperature_bubble"}
        assert temperatures_in(st.B_bubble[c]) == {"temperature_bubble"}


def test_dew_uses_dew_temperature(flash):
    _, st = flash
    for c in w.COMPONENTS:
        assert temperatures_in(st.A_dew[c]) == {"temperature_dew"}
        assert temperatures_in(st.B_dew[c]) == {"temperature_dew"}


def test_wrong_temperature_would_be_caught(monkeypatch):
    """Mutation check: build the bubble expressions with tau at the flash temperature."""

    def mutant(self):
        with self._tau_at(lambda: self.temperature):
            super(IPAWaterTdepStateBlockData, self)._temperature_bubble()

    monkeypatch.setattr(IPAWaterTdepStateBlockData, "_temperature_bubble", mutant)
    _, st = build_flash_model(w.BARBIERI_2024, 345.0, 60e3, 0.5)
    assert temperatures_in(st.A_bubble["ipa"]) != {"temperature_bubble"}


def test_domain_bounds_applied_at_build(flash):
    _, st = flash
    for var in (
        st.temperature_bubble,
        st.temperature_dew,
        st._temperature_equilibrium,
        st._t1,
        st._T_nrtl,
    ):
        assert var.lb is not None and var.ub is not None
        assert var.ub < min(w.TC.values())
    for p in ("Liq", "Vap"):
        assert st.flow_mol_phase[p].lb == 0.0


def test_rejects_missing_parameter_set():
    from idaes.core import FlowsheetBlock
    from pyomo.environ import ConcreteModel

    from fabchem.nrtl_tdep import IPAWaterTdepParameterBlock

    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    with pytest.raises(ValueError, match="nrtl_set"):
        m.fs.props = IPAWaterTdepParameterBlock(
            activity_coeff_model="NRTL", state_vars="FTPz", valid_phase=("Liq", "Vap")
        )
