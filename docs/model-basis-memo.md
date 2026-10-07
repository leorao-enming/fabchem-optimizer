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

1. **Barbieri et al. (author name corrected 2026-10-07; see "C1 source reading" below), "Vapor-liquid equilibrium data for the binary system
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

### C1 source reading (2026-10-07) - corrections to the candidates above

Both papers were read in full (PDFs in the vault's `07 Sources/Research/`). The
descriptions in the numbered list above were written from abstracts and are wrong in
these respects:

- **Source 1 authors** are Barbieri, De Guido, Moioli (not "Bogaert"). It regressed NRTL
  with Aspen Plus V14 on its own 60 and 80 kPa data (T ~ 341-367 K), not on the other
  literature. Form: tau_ij = a_ij + b_ij/T, alpha_12 = alpha_21 = 0.47 **fixed**
  (a first free regression gave 0.43). Table 7, component 1 = 2-propanol,
  2 = water: a12 = -1.39470283, a21 = 4.50009825, b12 = 627.160288, b21 = -791.079743
  (the paper's table header prints the b unit as "1/K"; with tau = a + b/T it must be
  K - a printing inconsistency, inferred). Reported fit: AAD 0.29 K on T and 0.0198 / 0.0146
  on y_IPA / y_water for the isobaric sets; Redlich-Kister consistency passed (-4.83 at
  60 kPa, -0.65 at 80 kPa, tolerance 10 %). Applicability range is the fitted 60-80 kPa,
  ~341-367 K; anything outside is extrapolation.
- **Source 2 is not a parameter source and is not 101.3 kPa.** Moioli et al. (same lab)
  measured new isobaric VLE at 103.5, 150, 200, 250 and 300 kPa (Tables 6-10) in an
  all-glass dynamic recirculation still (not a Rose-type distiller). It used Aspen Plus
  V11 *default* NRTL parameters (values not printed) and states that regression of new
  parameters is out of scope. It is useful as independent validation *data* above
  source 1's fitted range, and as a record of how default parameters perform
  (NRTL %AAD of T 0.26-0.37 %, but 19.6-37.7 % AAD of y_IPA at 150-300 kPa).
- **Independence:** both papers come from the same laboratory (PT lab, Politecnico di
  Milano) with Moioli as an author of each. They are not two independent *parameter*
  sources. Overview 5.5's requirement of at least two independent NRTL parameter sets is
  **not yet met**; the second set (Aspen databank defaults, or another published fit)
  is still `open` and would need its numeric values and applicability range.
- **Transcription check (verified):** with Table 7 as transcribed, a reference bubble-T
  calculation (numpy, Wagner Psat from the C0 spike) reproduces the paper's own 60 kPa
  data to ~0.1 K, the pure boiling points (342.82 / 359.11 K vs paper 342.85 / 359.01 K),
  and the azeotrope temperatures (340.77 K, 347.56 K vs ~340.9, ~347.6). The model
  azeotrope composition (x_IPA 0.686-0.690) sits above the paper's reported ~0.65 because
  the T-x minimum is very flat (a 0.1 K difference moves it by several mole percent); do
  not read composition-of-azeotrope agreement into this check.
- **Open for C2:** IDAES's activity-coefficient package takes tau as a fixed parameter
  per block; tau = a + b/T needs checking against, or an extension of, the package.
  Not yet verified.

Earlier attempt, kept for the record:

- `thermo` 0.6.1 bundled ChemSep NRTL databank: contains **no** isopropanol/water pair
  (CAS 67-63-0 / 7732-18-5). Its metadata defaults a missing pair to b_ij = 0 with
  alpha = 0.3, i.e. silently ideal - any tool that falls back to such a default for
  this system must be treated as having no parameters, not as having parameters.
- Two open-access MDPI articles (Energies 2021, 14, 5471; Separations 2025, 12, 196)
  were read: the first uses Aspen Plus built-in NRTL parameters without tabulating
  them, the second has no IPA/water NRTL table. Neither is usable as a source.
- The placeholder parameters in `scripts/c0_flash_spike.py` remain placeholders.

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
- ~~ADR 0001 (IDAES/IPOPT environment feasibility spike) not yet executed.~~
  **Executed 2026-10-07 — GO**, result in `docs/adr/0001-c0-feasibility-spike.md`.
  It verified the solver stack only; its NRTL parameters were placeholders, so
  nothing in it counts toward the §4 parameter-source/VLE gate. Two of its
  findings affect C1/C2 planning: IDAES's default initialization failed at
  x_IPA = 0.5 (cause not yet established), and the smooth-flash smoothing
  parameters must be set relative to the two-phase window near the azeotrope.
