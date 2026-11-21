"""IDAES property package for IPA/water with temperature-dependent NRTL tau.

Why this exists: in IDAES 2.13 the activity-coefficient package's NRTL `tau` is a single
`Var` on the parameter block, fixed by the user and read by three groups of equations - the
flash liquid (`eq_Gij_coeff`, `eq_A`, `eq_B`), the bubble-point expressions and the
dew-point expressions. All three sourced parameter sets for this system are of the form
tau_ij = a_ij + b_ij/T (docs/model-basis-memo.md section 4), and freezing tau at one
temperature shifts bubble temperatures by roughly the sets' own fit quality (measured in
scripts/c1_tdep_nrtl_check.py), so a constant tau is not acceptable.

How: a state block subclass builds IDAES's own equations unchanged, but while each group is
being constructed `self.params.tau` resolves to tau(T) evaluated at the temperature that
group belongs to:

- flash liquid: the equilibrium temperature. IDAES builds the NRTL equations before the
  flash equations that create `_temperature_equilibrium`, so the block gets its own
  variable `_T_nrtl` plus the equality `_T_nrtl == _temperature_equilibrium`;
- bubble point: `temperature_bubble`;
- dew point: `temperature_dew`.

No IDAES source is modified. `params.tau` itself is left unused (and fixed to 0) - a test
checks that no constraint references it.

Domain bounds (ADR 0001 Finding 1) are applied when each variable is built, not afterwards:
IDAES's unbounded temperatures let IPOPT step past the critical temperature, where the
Wagner term raises a negative number to the power 1.5.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from idaes.core import Component, declare_process_block_class
from idaes.core.util.misc import extract_data
from idaes.models.properties.activity_coeff_models.activity_coeff_prop_pack import (
    ActivityCoeffParameterData,
    ActivityCoeffStateBlockData,
    _ActivityCoeffStateBlock,
)
from pyomo.common.config import ConfigValue
from pyomo.environ import Constraint, NonNegativeReals, Param, Set, Var
from pyomo.environ import units as pyunits

from fabchem.ipa_water import COMPONENTS, MW, PC, TC, WAGNER, NRTLSet

T_LOWER = 200.0  # K, far below any state this package is used for
T_UPPER = 0.99 * min(TC.values())  # K, keeps (Tc - T)/Tc positive for the Wagner equation


def _nrtl_set(value: Any) -> NRTLSet:
    if not isinstance(value, NRTLSet):
        raise TypeError(f"nrtl_set must be a fabchem.ipa_water.NRTLSet, got {type(value)}")
    return value


@declare_process_block_class("IPAWaterTdepParameterBlock")
class IPAWaterTdepParameterData(ActivityCoeffParameterData):
    """IPA/water, ideal vapor + NRTL liquid, tau_ij = tau_a[i,j] + tau_b[i,j]/T."""

    CONFIG = ActivityCoeffParameterData.CONFIG()
    CONFIG.declare(
        "nrtl_set",
        ConfigValue(domain=_nrtl_set, description="Sourced NRTL parameter set (required)"),
    )

    def build(self):
        self.component_list_master = Set(initialize=list(COMPONENTS))
        self.ipa = Component()
        self.water = Component()
        super().build()  # also processes self.config
        if self.config.activity_coeff_model != "NRTL":
            raise ValueError("IPAWaterTdepParameterBlock supports activity_coeff_model='NRTL'")
        if self.config.nrtl_set is None:
            raise ValueError("nrtl_set is required (a fabchem.ipa_water.NRTLSet)")
        nrtl: NRTLSet = self.config.nrtl_set
        self._state_block_class = IPAWaterTdepStateBlock  # noqa: F821

        self.phase_equilibrium_idx_master = Set(initialize=[1, 2])
        self.phase_equilibrium_idx = Set(initialize=[1, 2])
        self.phase_equilibrium_list_master = {
            1: ["ipa", ("Vap", "Liq")],
            2: ["water", ("Vap", "Liq")],
        }
        self.phase_equilibrium_list = dict(self.phase_equilibrium_list_master)

        self.pressure_reference = Param(mutable=True, default=101325, units=pyunits.Pa)
        self.temperature_reference = Param(mutable=True, default=298.15, units=pyunits.K)
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

        pairs = {("ipa", "water"): 0, ("water", "ipa"): 1}
        self.tau_a = Param(
            self.component_list,
            self.component_list,
            mutable=True,
            initialize={
                (i, j): nrtl.a[pairs[i, j]] if i != j else 0.0
                for i in COMPONENTS
                for j in COMPONENTS
            },
            doc="tau_ij = tau_a + tau_b/T, dimensionless part",
        )
        self.tau_b = Param(
            self.component_list,
            self.component_list,
            mutable=True,
            initialize={
                (i, j): nrtl.b[pairs[i, j]] if i != j else 0.0
                for i in COMPONENTS
                for j in COMPONENTS
            },
            units=pyunits.K,
            doc="tau_ij = tau_a + tau_b/T, temperature part",
        )
        for i in COMPONENTS:
            for j in COMPONENTS:
                self.alpha[i, j].fix(nrtl.alpha)
                # Not used by any equation of IPAWaterTdepStateBlock (tested); fixed so it
                # can never become a degree of freedom.
                self.tau[i, j].fix(0.0)


class _TauAt:
    """Indexable stand-in for `params.tau`: tau_ij at a (lazily resolved) temperature."""

    def __init__(self, params: Any, temperature: Callable[[], Any]):
        self._params = params
        self._temperature = temperature

    def __getitem__(self, ij: tuple[str, str]) -> Any:
        i, j = ij
        if i == j:
            return 0.0
        return self._params.tau_a[i, j] + self._params.tau_b[i, j] / self._temperature()


class _ParamsWithTau:
    """Delegates every attribute to the real parameter block except `tau`."""

    def __init__(self, params: Any, tau: _TauAt):
        self._real = params
        self.tau = tau

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def _bound_temperature(var: Any) -> None:
    var.setlb(T_LOWER)
    var.setub(T_UPPER)


@declare_process_block_class("IPAWaterTdepStateBlock", block_class=_ActivityCoeffStateBlock)
class IPAWaterTdepStateBlockData(ActivityCoeffStateBlockData):
    """ActivityCoeffStateBlockData with tau evaluated at each equation group's temperature."""

    @property
    def params(self):
        proxy = self.__dict__.get("_tau_proxy")
        return proxy if proxy is not None else self._params

    @contextmanager
    def _tau_at(self, temperature: Callable[[], Any]) -> Iterator[None]:
        self.__dict__["_tau_proxy"] = _ParamsWithTau(
            self._params, _TauAt(self._params, temperature)
        )
        try:
            yield
        finally:
            self.__dict__["_tau_proxy"] = None

    def _make_NRTL_eq(self):
        self._T_nrtl = Var(
            initialize=self.temperature.value if self.temperature.value is not None else 350.0,
            bounds=(T_LOWER, T_UPPER),
            units=pyunits.K,
            doc="Equilibrium temperature as seen by the flash NRTL equations",
        )
        with self._tau_at(lambda: self._T_nrtl):
            super()._make_NRTL_eq()
        for c in self.params.component_list:
            self.activity_coeff_comp[c].setlb(1e-6)

    def _make_flash_eq(self):
        super()._make_flash_eq()
        _bound_temperature(self._temperature_equilibrium)
        _bound_temperature(self._t1)
        for p in self.params.phase_list:
            self.flow_mol_phase[p].setlb(0.0)
        if hasattr(self, "_T_nrtl"):
            self._T_nrtl_link = Constraint(expr=self._T_nrtl == self._temperature_equilibrium)

    def _pressure_sat_comp(self):
        super()._pressure_sat_comp()
        for c in self.params.component_list:
            self.pressure_sat_comp[c].setlb(1.0)

    def _temperature_bubble(self):
        with self._tau_at(lambda: self.temperature_bubble):
            super()._temperature_bubble()
        _bound_temperature(self.temperature_bubble)

    def _temperature_dew(self):
        with self._tau_at(lambda: self.temperature_dew):
            super()._temperature_dew()
        _bound_temperature(self.temperature_dew)


def build_flash_model(nrtl: NRTLSet, T: float, P: float, z_ipa: float, flow_mol: float = 1.0):
    """A one-state-block flowsheet: isothermal flash of a binary feed, all states fixed.

    Returns (model, state). Bubble and dew temperatures are built (they are part of the
    smooth flash formulation). Nothing is initialized or solved here.
    """
    from idaes.core import FlowsheetBlock
    from pyomo.environ import ConcreteModel

    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    # declare_process_block_class injects IPAWaterTdepParameterBlock into this module
    m.fs.props = IPAWaterTdepParameterBlock(  # type: ignore[name-defined]  # noqa: F821
        activity_coeff_model="NRTL",
        state_vars="FTPz",
        valid_phase=("Liq", "Vap"),
        nrtl_set=nrtl,
    )
    m.fs.state = m.fs.props.build_state_block(m.fs.time, defined_state=True)
    st = m.fs.state[0]
    st.flow_mol.fix(flow_mol)
    st.temperature.fix(T)
    st.pressure.fix(P)
    st.mole_frac_comp["ipa"].fix(z_ipa)
    st.mole_frac_comp["water"].fix(1.0 - z_ipa)
    st.temperature_bubble, st.temperature_dew, st.pressure_sat_comp  # noqa: B018
    return m, st
