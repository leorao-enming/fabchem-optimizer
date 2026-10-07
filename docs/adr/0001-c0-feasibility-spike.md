# ADR 0001: C0 feasibility spike — IDAES/IPOPT environment stability

- **Status:** accepted — executed 2026-10-07, result recorded below (**GO**, with findings that change how C1/C2 must be built)
- **Date:** 2026-08-19 (proposed) / 2026-10-07 (executed)
- **Gate:** P0 (deliberately pulled forward from its natural place at C1; executed ~4 weeks later than the original "first two weeks" target)

## Context

Per the Overview doc's risk table, IDAES/IPOPT local installation instability
is the single highest-probability, highest-impact risk in the entire
FabTwin/FabChem plan — and under the original schedule it wasn't checked
until Gate C1 (2027-01-18), five months in, leaving only ~4 months of
recovery time if it failed.

This ADR exists to force that check into the first two weeks instead, while
recovery time is still ~9 months.

## Decision

Before any flowsheet, property-package, or optimization code is written,
run and record the result of this checklist:

- [x] Install IDAES (`pip install idaes-pse`) in the project's `.venv`
      — idaes-pse 2.13.0, Pyomo 6.10.1, Python 3.11.9 (Windows 11)
- [x] Run `idaes get-extensions` and confirm IPOPT is available
      — IDAES extensions v3.4.2 (20240811); IPOPT 3.13.2, linear solver ma27
- [x] Build a minimal IPA/water flash calculation using the IDAES
      activity-coefficient property package with ideal vapor + NRTL liquid
      — `scripts/c0_flash_spike.py` (**NRTL parameters are unsourced placeholders**)
- [x] Solve it with IPOPT and confirm a normal termination condition (not
      just "solver returned", but wall time and termination string recorded)
      — `optimal`, 2 IPOPT iterations, ~0.03 s, and agrees with an independent
      numpy/scipy implementation to < 5e-7 (see Result)
- [x] Repeat the solve 10 times from cold start; record success rate
      — 10/10 valid (same 2 iterations every time); plus an 8-composition sweep, 8/8 valid
- [x] Repeat the entire checklist inside the Docker/Linux reference runtime,
      not just the local dev machine
      — `python:3.11-slim-bookworm` (Debian 12, glibc 2.36, WSL2 host): identical
      results; needed workarounds recorded under Findings 5-6
- [x] Record solver name, version, and termination condition in
      `evidence/validation-summary.json` per the schema's `solver` field
      — `scripts/validate.py` now writes `solver: {name, version, termination_condition}`
      when IPOPT is available

## Alternatives considered

- **Wait until Gate C1 as originally scheduled** — rejected: this is exactly
  the risk-table trigger being pre-empted; waiting defeats the purpose.
- **Skip local dev entirely, only ever run inside Docker** — not rejected
  outright, but the checklist still needs to run once locally first so
  day-to-day development isn't Docker-only from week one; if local install
  proves unstable, this becomes the fallback (see rollback trigger).

## Consequences

- Two focused development days spent before any "real" project code exists.
- A concrete go/no-go signal in week 1-2 instead of an ambiguous one in month 5.

## Rollback trigger

If two development days pass without a reproducible solve (per the Overview
doc's risk table): set Docker/Linux as the *only* reference runtime for
anything solver-related immediately, and restrict local (non-Docker)
development to non-solver tests. If Docker also fails to produce a stable
solve, escalate per the Overview doc's row *"IDAES/IPOPT 本机安装不稳定"* —
this is the point at which the FabChem topic itself would need to shrink to
a verifiable binary system, not just the tooling.

## Result

**Verdict: GO.** IDAES 2.13.0 + Pyomo 6.10.1 + IPOPT 3.13.2 builds, initializes,
and solves an NRTL VLE flash reliably on both Windows 11 and a Debian 12 Linux
container, and the answers match an independent implementation. The rollback
trigger ("two development days without a reproducible solve") did **not** fire.
Docker/Linux stays the release reference runtime as originally decided, but the
local Windows environment is also workable for solver development.

What this spike does and does not show:

- **Shows:** the solver stack works; the failure modes below are understood and
  have working mitigations; the IDAES equations reproduce a hand-built reference.
- **Does not show:** anything about IPA/water thermodynamics. The NRTL alpha/tau
  are unsourced placeholders (order-of-magnitude plausible, not fitted). Wagner
  vapor-pressure constants are sourced (McGarry/Reid 4th ed. via `chemicals`
  1.5.2, sanity-checked at the normal boiling points) but no VLE comparison has
  been done. NRTL source selection and the VLE gate are Gate C1.

Measured, final strategy (domain bounds + non-ideality-aware start, direct IPOPT
solve, smoothing parameters scaled to the two-phase window):

| | Windows 11, Python 3.11.9 | Debian 12, Python 3.11.17 (WSL2) |
|---|---|---|
| Baseline (x_IPA = 0.17, 1 atm, T = 359.68 K) | optimal, 2 iterations | optimal, 2 iterations |
| 10 cold-start repeats | 10/10 valid, 0.026 s median | 10/10 valid, 0.011 s median |
| 8-composition sweep (x_IPA 0.02-0.80) | 8/8 valid | 8/8 valid |
| Max |dV|, |dx|, |dy| vs independent reference | 4.6e-7 | 4.6e-7 |
| IPOPT optimal but answer invalid | 0 | 0 |

Windows and Linux baseline vapor fraction are bit-identical (difference 0.0).
"Valid" means: IPOPT `optimal` **and** 0 <= V <= 1 **and** all mole fractions in
[0,1] **and** agreement with the independent reference below 1e-5. IPOPT's
termination status alone was not trusted (Finding 2).

### Findings (these change how C1/C2 must be built)

1. **IDAES defaults fail outright on this system.** With unbounded variables,
   IPOPT's first Newton step on the Psat / T_bubble / T_dew sub-problem pushes T
   above the critical temperature and the Wagner term `((Tc-T)/Tc)**1.5` is
   evaluated on a negative base (`can't evaluate pow(-0.0711184,1.5)`); the solve
   aborts with status `error`. Mitigation: bound temperature variables below
   0.99*min(Tc), Psat > 0, activity coefficients > 0, phase flows >= 0
   (`harden_state_block` in the spike). Bounds are inactive at the solution.
2. **IPOPT `optimal` is not evidence of a correct answer.** With temperature/Psat/
   activity-coefficient bounds but *unbounded phase flows*, the baseline case ended
   `optimal` after 0 iterations on a spurious point: vapor fraction -3.25e9,
   T_dew (352.19 K) below T_bubble (353.91 K), x = y = (0.666, 0.334). Reproduced
   on demand (see `harden_state_block`: the `flow_mol_phase >= 0` bound is what
   removes it). IPOPT's status did not flag it; the independent reference did.
   This is the Overview's rule "optimized result must re-run an independent
   balance/constraint check — IPOPT 'optimal' is not a pass", now with a concrete
   case behind it. C2/C3 must keep that check. (After the flow bounds were added,
   the remaining "optimal but disagrees with the reference" cases were not
   spurious solutions but smoothing error — Finding 4.)
3. **IDAES's built-in `initialize()` failed at x_IPA = 0.5.** Observed, with the
   domain bounds in place: initialization step 1 (Psat, T_bubble, T_dew) is
   optimal; steps 2-5 are all infeasible and IDAES raises `InitializationError`.
   Step 2 is where activity coefficients are fixed at gamma = 1. **Cause not
   established**: the obvious guess — the real two-phase window lies outside the
   ideal-solution one — is *not* the discriminator, because the operating
   temperature is also outside the ideal window at x_IPA = 0.17 and 0.30 (15 K and
   13 K below the ideal bubble point) where initialization succeeds. With default
   IDAES initialization (default smoothing) 5 of 8 sweep compositions were valid,
   with or without a Raoult's-law starting guess: x_IPA 0.02-0.30 valid; 0.5
   initialization error; 0.65 and 0.8 failed on smoothing error (Finding 4),
   not on initialization. Skipping `initialize()` and handing IPOPT a non-ideality-
   aware starting point (phase split, compositions, gamma, Psat, T_bubble/T_dew
   from the independent reference) solved x_IPA = 0.5 (6/8 at default smoothing,
   8/8 with Finding 4's fix). **C2 baseline-flowsheet initialization (the
   "distillation column initialization difficulty" row of the Overview risk
   table) should plan for a custom initializer rather than assume IDAES's default
   works; why it fails at 0.5 should be understood before C2, not assumed.**
4. **The smooth-flash approximation error scales with eps / two-phase window.** IDAES
   uses a smoothed bubble/dew formulation (Burgard et al. 2018) with eps_1 = 0.01 K,
   eps_2 = 0.0005 K. Near the IPA/water azeotrope the window collapses (0.017 K at
   x_IPA = 0.65 with the placeholder parameters), and the error in vapor fraction is
   7.3e-2 at default eps, 1.1e-3 at eps/10, 1.2e-5 at eps/100. Setting eps_1 =
   window/1000 gave < 5e-7 at every sweep point. **Any column or flash model near
   the azeotrope must set the smoothing parameters relative to the local window.**
5. **IDAES 2.13.0 provides no extension build for Debian 12/13.** Official builds
   exist only for el7/el8, ubuntu1804/2004/2204 (aliases: ubuntu2404, el9). On
   `python:3.11-slim` (now Debian 13) `idaes get-extensions` stops with "Unsupported
   platform: debian13-x86_64". The working reference runtime is
   `python:3.11-slim-bookworm` with `idaes get-extensions --distro ubuntu2204`.
6. **That IPOPT binary needs four shared libraries not in the slim image:**
   `libgfortran5 liblapack3 libblas3 libgomp1` (`apt-get install`). Without them the
   file exists, `SolverFactory("ipopt").available()` returns True, but
   `.version()` returns None — the spike now treats that as unavailable. The
   Dockerfile for the release runtime must pin the base image and install these.
7. **Property-package observation, not verified as a bug:** in
   `activity_coeff_prop_pack.py` the NRTL dew-point residual is built from
   `activity_coeff_comp` (the flash-liquid activity coefficients), while an unused
   `activity_coeff_comp_dew` expression is also constructed. So IDAES's `T_dew`
   is coupled to the flash solution rather than being the true dew temperature
   (e.g. 356.42 K vs 356.51 K at x_IPA = 0.5). It did not change any answer in
   this spike (all 8 points match the reference) but is worth re-checking in C2.

### Addendum 2026-10-07: Finding 3 diagnosed (placeholder NRTL parameters)

`scripts/c1_init_diagnosis.py` reproduces this. Finding 3's guess that the failure is
a property of x_IPA = 0.5 was wrong in a more basic way: `initialize()` steps 2 and 3
are infeasible in **every** case on a 5-composition x 3-temperature grid, including the
cases where initialization succeeds overall. IDAES raises only if the *last* step is not
optimal, so success depends on whether step 4 (NRTL restored) recovers from the iterate
the infeasible steps leave behind.

Why steps 2-3 are infeasible (verified from the package source and numerically):
`temperature_bubble` is built from NRTL activity coefficients at the feed composition
(352.44 K at x_IPA = 0.5, equal to the independent reference), but step 2 solves the
flash with gamma fixed at 1. For this system the NRTL dew temperature sits below the
ideal-solution bubble point, so every operating temperature inside the real two-phase
window is below the ideal bubble point; the gamma = 1 liquid is then subcooled
(sum z_i Psat_i / P = 0.56-0.71 at the NRTL bubble temperature across the grid) and
`eq_sum_mol_frac` cannot be satisfied. Step 1 also leaves `activity_coeff_comp` as a free
variable (it was 23.4 / 1.63 for ipa / water at x_IPA = 0.5), so `T_dew` after step 1 is
not meaningful (343.95 K, below T_bubble); this is the same coupling as Finding 7.

Still **not** diagnosed: why step 4 fails to recover in a band around x_IPA = 0.5
(T fractions 0.35-0.85 of the window; 0.05-0.25 and 0.95 recover), and it does not depend
on the starting phase split (0.01-0.9) or on the phase-flow lower bound. Consequence for
C2 is unchanged but now better grounded: do not rely on `initialize()` for this system;
the non-ideality-aware start used in the spike avoids steps 2-3 entirely. Re-run with the
sourced NRTL sets in C1; these are placeholder parameters, so nothing here is a statement
about real IPA/water.

### Corrected during the spike (kept for the record)

The first version of the independent reference declared x_IPA = 0.5 a superheated
vapor because it made a single-phase decision on the first successive-substitution
iteration (gamma evaluated at the feed composition rather than the equilibrium
liquid). That made the *correct* IDAES answer look wrong by dV = 0.12. The
reference was rewritten as a 1-D root solve of sum(K_i x_i) = 1 with no early
shortcut; after that IDAES and the reference agree at x_IPA = 0.5 to 1.3e-7.
Lesson: an independent check needs its own verification before it can condemn
the thing it checks.

### Follow-ups

- C1: replace placeholder NRTL parameters with the two sourced parameter sets
  (docs/model-basis-memo.md section 4) and run the VLE comparison; re-run this
  spike's sweep with real parameters.
- C2: build a reusable property initializer (bounds + non-ideality-aware start
  + window-scaled smoothing) rather than relying on `initialize()`.
- Release runtime: Dockerfile on `python:3.11-slim-bookworm` + the four apt
  packages + `idaes get-extensions --distro ubuntu2204`; consider caching the
  extension download.
- CI currently has no IPOPT, so `make validate` records the spike as "NOT RUN"
  there (non-mandatory). Adding `idaes get-extensions` to the CI workflow would put
  this check on every push; not done in this change.
