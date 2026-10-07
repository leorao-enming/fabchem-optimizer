# fabchem-optimizer

Equation-oriented IPA/water recovery-and-dehydration flowsheet (IDAES + Pyomo),
optimized for minimum total annualized cost, with a screening-level TEA layer.
Built to demonstrate chemical process modeling, thermodynamics, and
techno-economic analysis competency.

**Status: P0 skeleton.** No property model, flowsheet, or optimization exists
yet. Nothing in this repo should be treated as a working result until a
`v1.0.0` tag exists.

## What this project demonstrates

- Staged-fidelity modeling: NRTL property model validated against public VLE
  data *before* any flowsheet/optimization work is allowed to start
- Equation-oriented flowsheeting (IDAES) and NLP optimization (Pyomo/IPOPT)
  with independent re-verification of every "optimal" result — solver
  termination status is never treated as engineering validation on its own
- Screening-level TEA with honest cost-basis provenance
- Rigorous parameter provenance: multi-source NRTL comparison + sensitivity
  analysis, cross-check against a newly published (2024) VLE dataset,
  Monte Carlo uncertainty quantification instead of point-estimate cost
  numbers, and independent cross-validation against DWSIM — see
  `FabChem 差异化维度选择.md` in the planning vault for why

## C0 feasibility spike: done (GO) — read its findings before writing flowsheet code

Per the Overview doc's risk table, IDAES/IPOPT environment stability is the
single highest-risk item in this project and was validated *first*.
`docs/adr/0001-c0-feasibility-spike.md` records **GO** (2026-10-07): the stack
solves an NRTL flash reliably on Windows 11 and a Debian 12 container. It also
records seven findings that C1/C2 must respect — notably that IDAES's default
initialization and default smoothing are not safe near the IPA/water azeotrope,
and that an IPOPT `optimal` status must always be re-checked independently. The
spike used placeholder NRTL parameters, so it says nothing about IPA/water
thermodynamics; that is Gate C1. To re-run it: `idaes get-extensions` then
`python scripts/c0_flash_spike.py`.

## Repository layout

```text
src/fabchem/      # property package config, flowsheet builders, service layer — no UI logic
app/              # Streamlit dashboard; calls simulate()/optimize() only, never touches Pyomo vars directly
configs/          # feed scenarios, cost_basis, NRTL parameter sets (versioned)
tests/unit/       # fast, no network — single function / formula tests
tests/validation/ # VLE dataset comparison, balance/residual checks, solver-availability checks
cases/            # frozen case-study inputs, results, figures, short conclusions
docs/             # architecture notes, ADRs, model-basis memo, report source, interview pack
evidence/         # machine-readable validation-summary + run manifests
scripts/          # reproduce_cases, export_figures, build_report
```

## Commands

```bash
make setup     # create venv, install project + dev deps (does NOT install IDAES binary extensions — see docs/adr/0001)
make test      # fast unit tests, no network — PR gate
make validate  # run engineering validation, write evidence/validation-summary.json
make cases     # rebuild all frozen case tables/figures from configs
make app       # run the Streamlit dashboard
make report    # build the technical report from evidence + cases only
```

Docker/Linux is the reference runtime for anything solver-related; macOS/Windows
are development-only environments and IDAES binary extension availability is
not guaranteed there (section 5.6 of the Overview doc).

## Status against the roadmap

| Gate | Deliverable | Status |
|---|---|---|
| P0 | Repo skeleton, ADR template, CI empty-run | ✅ this commit |
| C1 | Thermo spike: IPA/water VLE match, NRTL provenance, solver smoke test | ⬜ not started (solver smoke test already done early via ADR 0001; VLE match and NRTL provenance still open) |
| C2 | Baseline flowsheet, mass/energy closure | ⬜ not started |
| C3 | Optimization + TEA | ⬜ not started |
| C4 | Scenarios + demo + 3 cases | ⬜ not started |
| C5 | v1.0.0 release | ⬜ not started |

## Non-goals (v1)

Rigorous adsorption/membrane design for the dehydration stage (uses a
reduced-order separator, explicitly labeled as such), integer tray-count
optimization, Class 3/industrial-grade cost estimates. See the risk table in
the Overview doc for what gets cut first if a gate slips.

## License

MIT — see `LICENSE`.
