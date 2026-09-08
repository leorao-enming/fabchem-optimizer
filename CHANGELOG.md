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
