# FabChem model-basis memo

**Status:** locked at P0 (2026-09-08) as the problem definition for Gate C1
(thermo spike). This is a specification/scope document — no property model,
flowsheet, or cost calculation exists yet. Per the Overview's staged-fidelity
rule (§5.1), nothing below authorizes writing optimization or high-purity
dehydration code before the VLE validation in §4 clears its error tolerance.

## 1. Feed definition

**Scenario:** an IPA/water waste stream from a solvent-cleaning/rinse
operation, carrying a small fraction of non-volatile contaminant (dissolved
residue that does not vaporize under any condition this flowsheet reaches).

**v1 baseline feed (screening-level basis, not a real plant feed — final
numeric values live in `configs/cost_basis.*` at C1, not hardcoded):**

| quantity | v1 baseline | note |
|---|---|---|
| mass flow | 1000 kg/h | arbitrary round-number basis for screening-level TEA; not a claimed real-plant capacity |
| IPA | 40 wt% | illustrative — chosen mid-range so both distillation bulk-recovery and post-azeotrope dehydration are load-bearing, not trivial |
| water | 58 wt% | balance |
| non-volatile contaminant | 2 wt% | modeled as an explicit pseudo-component or a bounded separator assumption per Overview §5.1 — which of the two is decided at C2, not here |
| feed condition | ambient T, 1 atm, liquid | preheater (Overview §5.2 flow diagram) brings it to column feed condition |

## 2. Purity / recovery targets — engineering meaning

**Product purity target: 99.5 wt% IPA.** This is the kind of spec a reclaimed
solvent needs to be requalified for reuse as a cleaning/rinse solvent rather
than downgraded to a lower-value fuel-blend or disposal stream — i.e. the
target is chosen because it is *not* achievable by distillation alone (see
§3), so it forces the two-stage architecture the Overview already commits to
(§5.1), rather than being an arbitrary round number.

**Recovery target: to be set as a bounded decision variable, not a fixed
point value** (Overview §5.3 — IPA recovery is a constraint/objective
component, not a single hardcoded target). The baseline case (C2) reports
whatever recovery the initialized flowsheet achieves; C3 optimization treats
recovery as a variable traded off against cost and purity.

## 3. Distillation vs. dehydration boundary

IPA and water form a well-documented **homogeneous minimum-boiling azeotrope**
at **87.4–87.7 wt% IPA**, boiling at **80.3–80.4 °C at 1 atm**. This is the
hard physical limit on what ordinary (non-azeotropic) distillation can
achieve, regardless of tray count or reflux — it is not a solver or model
limitation.

**Boundary, locked:**

- **Distillation stage:** bulk recovery of IPA up to a composition
  approaching but not exceeding the azeotropic limit. This is where most of
  the water is rejected and where the mass/energy balance closure and
  baseline flowsheet (Gate C2) live.
- **Dehydration/polishing stage:** takes the near-azeotropic distillate and
  pushes it to the 99.5 wt% product target. Per Overview §5.1, v1 uses a
  **reduced-order separator** for this stage — bounded by literature/vendor
  ranges and checked with sensitivity analysis — explicitly *not* a rigorous
  adsorption/membrane design. The README's non-goals section already commits
  to this; this memo is the record of *why* the boundary sits here rather
  than trying to force a single column past the azeotrope.

## 4. NRTL parameter candidate sources and VLE validation dataset

At least two independent literature sources are required before any
flowsheet work per Overview §5.5 — candidates identified at P0, to be
formally regressed/compared at C1:

1. **Bogaert et al., "Vapor-liquid equilibrium data for the binary system
   isopropanol+water at 60 kPa and 80 kPa,"** *J. Chem. Thermodynamics*,
   2024 ([ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0021961424000958)).
   New experimental data (GASP / Politecnico di Milano, all-glass dynamic
   recirculation still) at sub-atmospheric pressures the literature
   previously lacked, with NRTL parameters regressed by the authors and a
   thermodynamic-consistency test reported. **This is the "2024 new dataset"
   validation point required by §5.5 item 2** — it is a candidate parameter
   source *and* the cross-check dataset simultaneously, so the sensitivity
   analysis (§5.5 item 1) must include at least one *other* source to be a
   real comparison, not a self-check.
2. **"Isobaric Vapor–Liquid Equilibrium Data for the Isopropanol-Water
   System,"** *J. Chem. Eng. Data*, 2021, DOI
   [10.1021/acs.jced.1c00327](https://pubs.acs.org/doi/10.1021/acs.jced.1c00327).
   Atmospheric-pressure (101.3 kPa) data from a Rose-type circulating
   distiller, correlated with NRTL/UNIQUAC/Wilson — covers the pressure
   range distillation column trays actually operate at, complementing
   source 1's sub-atmospheric range.
3. **Fallback/tertiary candidate (not yet verified — `open`):** Aspen
   Plus/DECHEMA built-in NRTL binary parameter databank for IPA/water,
   commonly cited in older student/industrial work. Kept as a third
   comparison point at C1 *only if* it is verified to carry an explicit
   applicability range; per §5.5, any source whose declared range doesn't
   match this project's operating window must be excluded with a stated
   reason, not silently used.

**Validation gate (Overview §5.6):** bubble-temperature / phase-composition
error against source 1 and source 2, tolerance frozen *before* results are
seen, per the ADR discipline already established for this repo.

## 5. Cost-basis placeholders (values TBD at C3, structure locked now)

Per Overview §5.3 and §5.5 item 3, `configs/cost_basis.*` must declare, for
every uncertain parameter, a **distribution** (for Monte Carlo) not a bare
point value:

- CAPEX / installation factor
- Project life, discount rate
- Capacity factor
- CEPCI / currency base year
- Utility prices: steam, electricity, cooling water
- Waste disposal price, IPA market price (for loss/recovery valuation)

None of these have numeric values yet — this section exists so the *shape*
of the cost basis (what must be a distribution, what base year convention
applies) is agreed before C3, not improvised mid-optimization.

## 6. Open items (`open`, resolved at C1)

- Final numeric feed composition/flow (§1 values are illustrative, not
  frozen — freezing happens when `configs/` is authored at C1 alongside the
  thermo spike).
- Whether the non-volatile contaminant is a pseudo-component or a separator
  assumption (Overview §5.1) — decided once the property package (C1) shows
  which is numerically tractable.
- ADR 0001 (IDAES/IPOPT environment feasibility spike) is still `proposed`,
  not yet executed — this memo does not depend on it, but no flowsheet code
  should be written until ADR 0001 records a result.
