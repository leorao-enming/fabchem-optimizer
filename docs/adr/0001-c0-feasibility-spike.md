# ADR 0001: C0 feasibility spike — IDAES/IPOPT environment stability

- **Status:** proposed (not yet executed)
- **Date:** 2026-08-19
- **Gate:** P0 (deliberately pulled forward from its natural place at C1)

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

- [ ] Install IDAES (`pip install idaes-pse`) in the project's `.venv`
- [ ] Run `idaes get-extensions` and confirm IPOPT is available
- [ ] Build a minimal IPA/water flash calculation using the IDAES
      activity-coefficient property package with ideal vapor + NRTL liquid
- [ ] Solve it with IPOPT and confirm a normal termination condition (not
      just "solver returned", but wall time and termination string recorded)
- [ ] Repeat the solve 10 times from cold start; record success rate
- [ ] Repeat the entire checklist inside the Docker/Linux reference runtime,
      not just the local dev machine
- [ ] Record solver name, version, and termination condition in
      `evidence/validation-summary.json` per the schema's `solver` field

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

(Fill in after running the checklist — do not leave this ADR at "proposed"
once C0 work starts.)
