# Validation tests

VLE dataset comparisons, mass/energy balance residual checks, solver
availability/termination checks — not ordinary unit tests. Each test in this
directory should be traceable to a specific acceptance-criterion bullet in
`FabTwin & FabChem Overview.md` section 5.6.

Empty at P0 by design. First real content lands at Gate C1 (property model vs
public VLE data, multi-source NRTL sensitivity, 2024 dataset cross-check —
see section 5.5, the differentiator) and Gate C2 (balance closure).
