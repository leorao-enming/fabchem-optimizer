"""Export case figures (cases/<case>/figures/) for report and demo-video use.

P0 stub: no cases or figures exist yet. This will iterate cases/<case-name>/
and copy/re-render the frozen figures into a report-ready location (or
regenerate them from the case's stored data if regeneration is cheaper than
storing rasters) — never hand-edited afterward.
"""

import sys


def main() -> int:
    print("no case figures to export yet — figures land with Gate C4/C5")
    return 0


if __name__ == "__main__":
    sys.exit(main())
