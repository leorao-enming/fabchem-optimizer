"""Run engineering validation and write evidence/validation-summary.json.

P0 stub: no real checks exist yet (thermo validation lands in C1, balance
checks in C2, optimization checks in C3). This script writes a schema-conformant
fixture so the evidence pipeline itself is proven end to end before there is
anything real to validate. Every check below must be replaced with a genuine
test as each Gate lands; none of these numbers may be quoted anywhere until they are.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("jsonschema not installed — run `make setup` first.", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "evidence" / "validation-summary.schema.json"
OUTPUT_PATH = ROOT / "evidence" / "validation-summary.json"


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def build_summary() -> dict:
    return {
        "run_id": f"p0-fixture-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "app_version": "0.0.0",
        "checks": [
            {
                "name": "evidence_pipeline_smoke",
                "mandatory": True,
                "passed": True,
                "detail": "P0 placeholder check — schema + CI wiring only, no engineering result yet.",
            }
        ],
        "warnings": [
            "P0 skeleton: no property model, flowsheet, or optimization checks exist yet.",
            "IDAES/IPOPT solver availability has NOT been verified in this environment — see docs/adr/0001-c0-feasibility-spike.md.",
        ],
    }


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    summary = build_summary()
    jsonschema.validate(instance=summary, schema=schema)

    OUTPUT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {OUTPUT_PATH}")

    mandatory_failures = [
        c for c in summary["checks"] if c["mandatory"] and not c["passed"]
    ]
    if mandatory_failures:
        print(f"FAILED mandatory checks: {mandatory_failures}", file=sys.stderr)
        return 1

    print("all mandatory checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
