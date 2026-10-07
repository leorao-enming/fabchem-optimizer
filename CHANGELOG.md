# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); this project uses `vX.Y.Z` tags
only at real release Gates (C5 = v1.0.0), not for intermediate work.

## [Unreleased]

### Added

- P0 repo skeleton: directory layout, Makefile command surface, CI (ruff + mypy +
  pytest + validation smoke), ADR template, issue templates, evidence schema.
- ADR 0001: C0 feasibility spike plan for IDAES/IPOPT environment stability
  (pulled forward from Gate C1 to the first two weeks — see risk table in the
  Overview doc). Still `proposed`, not yet executed.
- `docs/model-basis-memo.md`: locked feed definition, purity/recovery targets,
  the distillation-vs-dehydration boundary at the IPA/water azeotrope
  (87.4–87.7 wt% IPA, 80.3–80.4 °C at 1 atm), two independent NRTL parameter
  literature candidates (JCED 2021 atmospheric; J. Chem. Thermodynamics 2024
  60/80 kPa dataset), and the cost-basis-as-distribution structure.
- `evidence/case-manifest.schema.json` plus a hand-written fixture and pytest
  checks, proving the case-run evidence pipeline ahead of Gate C4.
- Published to GitHub (`github.com/leorao-enming/fabchem-optimizer`, public)
  with all 5 gate milestones (C1–C5).

### Fixed

- P0 `scripts/validate.py`: `datetime.UTC` alias, line-length lint findings,
  `git_sha()` formatting.
- CI push trigger watched `branches: [main]`; the actual default branch is
  `master`, so no CI run had ever fired since the repo was created. Corrected
  to `branches: [master]` — first real GitHub Actions run passed green.

## [ADR 0001 executed] — 2026-10-07

### Added

- `scripts/c0_flash_spike.py`: the ADR 0001 solver-feasibility spike. IPA/water
  isothermal flash with the IDAES activity-coefficient property package
  (ideal vapor + NRTL liquid), solved with IPOPT, checked against an independent
  numpy/scipy implementation of the same equations. **NRTL parameters are
  unsourced placeholders** — this validates the solver stack, not IPA/water
  thermodynamics. Wagner vapor-pressure constants and critical constants are
  sourced (McGarry/Reid 4th ed.).
- `scripts/validate.py` now runs the spike when IPOPT is available and records
  `solver: {name, version, termination_condition}` as ADR 0001 requires. The
  check is non-mandatory (CI has no IPOPT), so an unavailable solver is recorded
  as "NOT RUN", never as a pass.

### Changed

- ADR 0001 status `proposed` -> `accepted`; **result: GO** on Windows 11 and on a
  Debian 12 container (identical numbers, IPOPT 3.13.2, IDAES 2.13.0, Pyomo 6.10.1).
  Seven findings recorded in the ADR, the ones that matter most: IDAES defaults
  fail without domain bounds on T/Psat/phase flows; IPOPT `optimal` can be a
  spurious solution; IDAES's built-in `initialize()` failed at x_IPA = 0.5 (cause
  not established); smoothing error scales with eps/two-phase window; IDAES has
  no extension build for Debian 12/13 (use `--distro ubuntu2204` plus four apt
  packages).
- `docs/model-basis-memo.md` open item for ADR 0001 updated.

### Not done

No flowsheet, no real NRTL parameters, no VLE validation (Gate C1). CI does not
yet install IPOPT. The reference-runtime Dockerfile does not exist yet.

### C1 prep: ADR 0001 Finding 3 diagnosed (2026-10-07)

- Added `scripts/c1_init_diagnosis.py` (rerunnable; not part of `make validate`).
  Result: IDAES `initialize()` steps 2-3 are infeasible in every case on the test
  grid, including successful initializations, because the flash is solved with
  gamma = 1 at an NRTL-derived bubble temperature where the ideal liquid is
  subcooled. Only the last step is checked, so success depends on step 4 recovering.
  Why step 4 fails around x_IPA = 0.5 is still not explained.
- ADR 0001: appended an addendum; the original findings are unchanged.
- Placeholder NRTL parameters only; nothing here concerns real IPA/water behaviour.

