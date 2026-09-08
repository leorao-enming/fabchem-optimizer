"""Build the technical report from evidence/ and cases/ only.

P0 stub: consumes nothing yet because no evidence/cases exist. Must never read
numbers from anywhere except evidence/validation-summary.json and cases/*/summary.json.
"""

import sys


def main() -> int:
    print("no evidence/cases to report on yet — report generation lands with Gate C4/C5")
    return 0


if __name__ == "__main__":
    sys.exit(main())
