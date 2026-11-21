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

### C1 prep: NRTL sources read (2026-10-07)

- Both candidate papers read in full. Source 1 (Barbieri et al., JCT 2024) supplies one
  sourced NRTL set (tau = a + b/T, alpha = 0.47 fixed, fitted at 60-80 kPa); transcription
  checked against its own data (~0.1 K). Source 2 (Moioli et al., JCED 2021) is not a
  parameter source and not 101.3 kPa: it is new isobaric data at 103.5-300 kPa measured
  against Aspen default parameters. Both come from the same lab, so Overview 5.5's
  "two independent parameter sets" is not yet met. Corrections recorded in
  `docs/model-basis-memo.md`. No code changed; the spike's placeholder parameters are
  still placeholders.

### C1: second NRTL source and cross-lab check (2026-10-07)

- Added `data/vle/` (published tables parsed from the PDFs, with provenance),
  `scripts/c1_extract_vle_tables.py`, and `scripts/c1_nrtl_crosscheck.py`.
- Second independent parameter source: Marzal et al. 1996 (NRTL at 30/60/100 kPa,
  alpha 0.30, tau = A/RT, component 1 = water). Reproduces its reported in-sample fit.
- Criteria frozen before running. Gate A (Barbieri params on Marzal 60 kPa) PASS
  (0.245 K, 0.0060). Gate B (Marzal params on Barbieri 60 kPa) FAIL (0.828 K, 0.0385 vs
  0.6 K / 0.03); a post-hoc look shows dilute-IPA noise plus a ~0.4 K inter-lab offset.
  Gate not loosened. Barbieri's own reported fit is not reproduced (open).
- Details in `docs/model-basis-memo.md`.
- Third parameter set (Lin & Tu 2014, 101.3 kPa, tau = A/T) added as informational only
  after the gates were frozen and run. It fits Marzal's data (0.32-0.33 K) but, like
  Marzal's set, misses Barbieri's 60 kPa data (0.69 K), which suggests the offset is in
  the Barbieri 60 kPa measurements (inference).

### C1: T-dependent NRTL in IDAES, and an initializer for it (2026-11-21, rebuilt on macOS)

A first implementation of this was written on 2026-10-07 on the Windows machine and never
committed; it is not reachable any more. This is a rebuild on macOS from the written record
of that work, not a copy of it. All numbers below are from this rebuild. The lost run's
numbers (34 points, 140/140 vs IDAES default 92/140, frozen-tau shift 0.15-0.70 K) used grids
that are not recorded exactly, so they are not compared with these.

Added:

- `src/fabchem/ipa_water.py`: constants, the three sourced NRTL sets (Barbieri 2024;
  Marzal 1996 at 30/60/100 kPa; Lin & Tu 2014) mapped onto one convention
  tau_ij = a_ij + b_ij/T with provenance and fitted pressure, and an independent numpy
  reference (bubble, dew, flash). Agrees with the C0 spike's reference to 1.7e-13 on the
  placeholder parameters; reproduces Marzal's printed infinite-dilution gammas to 0.3 % and
  Barbieri's azeotrope temperatures (340.77 / 347.56 K vs ~340.9 / ~347.6 K).
- `src/fabchem/nrtl_tdep.py`: IDAES 2.13's NRTL `tau` is one fixed `Var` read by the flash,
  bubble and dew equations. A state-block subclass builds IDAES's own equations unchanged
  but resolves tau to tau(T) at each group's own temperature: flash liquid at the
  equilibrium temperature (via a new `_T_nrtl` plus `_T_nrtl == _temperature_equilibrium`,
  because IDAES builds the NRTL equations before the flash equations), bubble at
  `temperature_bubble`, dew at `temperature_dew`. No IDAES source modified. Domain bounds
  (ADR 0001 Finding 1) applied when variables are built.
- `src/fabchem/nrtl_start.py`: initializer that loads the reference flash (gamma, NRTL
  intermediates, T_bubble, T_dew) as the IPOPT start, sets eps_1/eps_2 to the local
  two-phase window, solves once. IDAES's `initialize()` is not used (ADR 0001 addendum).
- `scripts/c1_tdep_nrtl_check.py`, `scripts/c1_tdep_init_check.py`, unit tests (parameter
  conventions against printed paper values, reference consistency, model structure with a
  mutation check) and solver tests in `tests/validation/` (skipped without IPOPT).
- `.github/workflows/solver.yml`: manual-only job that installs the IDAES extensions on
  ubuntu-22.04 and runs the solver tests and C1 scripts. **Not yet run on GitHub.**
- `scripts/validate.py` records the two C1 scripts as non-mandatory checks (NOT RUN without
  IPOPT).

Results (macOS 27.0.1 arm64, Python 3.11.16, IDAES 2.13.0, Pyomo 6.10.1, IPOPT 3.13.2
darwin-arm64):

- T-dependence check: 4 set/pressure cases x 3 compositions x 3 window temperatures = 36
  points, each from the reference start and from a perturbed start (T +2 K, gamma +10 %,
  V +0.1): 72/72 valid, worst |IDAES - reference| over V, x, y, T_bubble 1.2e-6 (tol 1e-5).
- Counter-example: tau frozen at 341 K shifts bubble temperatures by up to 0.13 / 0.22 /
  0.44 / 1.06 K (Barbieri 60, Barbieri 80, Marzal 60, Lin & Tu 101.3 kPa) - the same order
  as the sets' own fit quality (~0.3 K), so the T dependence cannot be dropped.
- Initializer check, 4 cases x 7 compositions x 5 states (subcooled, 25/50/75 % of the
  window, superheated) = 140: new initializer 140/140; IDAES `initialize()` + one solve
  95/140, of which 37 failures are IPOPT `optimal` with a wrong answer (ADR 0001 Finding 2
  again) and 8 are initialization failures.
- Worst agreement of the new initializer is 8.6e-6, at subcooled states (z = 0.3): the smooth
  flash puts T_eq about eps_1^2 / (4 |T - T_bubble|) above T_bubble, which leaves a small
  vapor fraction. It is the smoothing approximation (ADR 0001 Finding 4), and it sits close
  to the 1e-5 tolerance.
- IDAES's T_dew in two-phase states is below the true dew point by up to 0.68 K with these
  sourced parameters (ADR 0001 Finding 7, now measured on real parameters). It is exact for
  states at or above the dew point, which is where the smooth flash uses it, so no
  answer in these checks was affected; T_dew is therefore not part of the pass criterion.
- ADR 0001 spike re-run on macOS arm64: same summary as on Windows/Linux (final strategy 10/10
  cold starts, 8/8 sweep). The first IPOPT launch on this Mac exceeded Pyomo's 2 s
  `ipopt -v` probe (first-launch check of the downloaded binary); it ran normally after.

Corrected during the work (kept for the record):

- The first run of the initializer check gave 137/140. All three failures were superheated
  states solved to V = 1 + 1e-12..8e-12 (liquid flow ~1e-23) with x, y agreeing to 1e-13; the
  physical-range test allowed no slack. It now allows the same 1e-9 slack the reference
  flash uses. This change was made after seeing the result; the 1e-5 agreement tolerance was
  not changed.

Not done: the C1 Gate is still open (Gate B failed and stays failed; see memo). No flowsheet
(C2). No comparison with real column data. The initializer handles the binary only.

