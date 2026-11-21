"""fabchem-optimizer computation core.

C1 (thermodynamics) modules:

- `fabchem.ipa_water`: constants, sourced NRTL parameter sets, independent numpy VLE reference
- `fabchem.nrtl_tdep`: IDAES property package with T-dependent NRTL tau
- `fabchem.nrtl_start`: initializer for that package's flash states

No flowsheet or optimization modules exist yet. Application services will live here; app/
only calls into this package via simulate()/optimize(), never touching Pyomo variables
directly.
"""

__version__ = "0.0.0"
