"""Rebuild all frozen case-study tables/figures from configs/.

P0 stub: no cases exist yet (land in C4). This will iterate configs/cases/*.yaml,
call simulate()/optimize(), and write results/figures/summary.json into
cases/<case-name>/ — never hand-edited.
"""

import sys


def main() -> int:
    print("no case configs found — cases land in Gate C4, see docs/adr/ for status")
    return 0


if __name__ == "__main__":
    sys.exit(main())
