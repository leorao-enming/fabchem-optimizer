# Configs

Version-controlled, human-readable configuration: feed/operating scenarios,
`cost_basis` (CAPEX factors, utility prices, discount rate, CEPCI/currency
year — plus, per the Monte Carlo differentiator in section 5.3, declared
*distributions* for the uncertain ones, not just point values), and the NRTL
parameter sets under evaluation (each tagged with its literature source and
declared applicability range — section 5.5).

Nothing here is generated — these are the frozen inputs that `make cases` reads.
Empty at P0; first configs land with Gate C1 (model-basis memo + thermo spike).
