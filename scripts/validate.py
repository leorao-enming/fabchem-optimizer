"""Run engineering validation and write evidence/validation-summary.json.

Checks:
- evidence_pipeline_smoke (mandatory): still the P0 placeholder - proves schema + CI
  wiring only. Thermo validation lands in C1, balance checks in C2, optimization
  checks in C3; each must replace/extend this as its Gate lands.
- c0_flash_spike (NOT mandatory): the ADR 0001 solver-feasibility spike
  (scripts/c0_flash_spike.py). Non-mandatory on purpose: it needs the IDAES binary
  extensions (`idaes get-extensions`), which CI does not install - when IPOPT is
  unavailable the check is recorded as not run, not as a pass. When it does run,
  the solver name/version/termination condition are recorded in the summary's
  `solver` field as ADR 0001 requires. It validates the solver stack only, never
  IPA/water thermodynamics (its NRTL parameters are placeholders).
"""

import json
import subprocess
import sys
from datetime import UTC, datetime
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
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


SPIKE_RESULT_PATH = ROOT / "evidence" / "c0-spike-result.json"


def ipopt_version() -> str | None:
    try:
        import idaes  # noqa: F401  (adds the IDAES extensions dir to PATH)
        from pyomo.environ import SolverFactory

        solver = SolverFactory("ipopt")
        if not solver.available(exception_flag=False):
            return None
        return ".".join(str(v) for v in solver.version())
    except Exception:
        return None


def run_flash_spike() -> tuple[dict, dict | None]:
    """Returns (check, solver_record). solver_record is None when the spike did not run."""
    version = ipopt_version()
    if version is None:
        check = {
            "name": "c0_flash_spike",
            "mandatory": False,
            "passed": False,
            "detail": "NOT RUN: ipopt unavailable (run `idaes get-extensions`); see ADR 0001.",
        }
        return check, None

    result = subprocess.run(
        [sys.executable, "scripts/c0_flash_spike.py"], cwd=ROOT, capture_output=True, text=True
    )
    passed = result.returncode == 0
    detail = "ADR 0001 spike (placeholder NRTL; solver feasibility only): "
    solver = {"name": "ipopt", "version": version, "termination_condition": "unknown"}
    try:
        report = json.loads(SPIKE_RESULT_PATH.read_text(encoding="utf-8"))
        final = report["strategy_final_nrtl_direct_scaled_eps"]
        solver["termination_condition"] = final["baseline"]["idaes"]["termination_condition"]
        detail += (
            f"cold start {final['summary']['cold_start_valid']}, "
            f"sweep {final['summary']['sweep_valid']} valid vs independent reference"
        )
    except Exception as exc:
        detail += f"result file unreadable ({type(exc).__name__})"
    return {
        "name": "c0_flash_spike",
        "mandatory": False,
        "passed": passed,
        "detail": detail,
    }, solver


def build_summary() -> dict:
    spike_check, solver = run_flash_spike()
    summary = {
        "run_id": f"validate-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "git_sha": git_sha(),
        "app_version": "0.0.0",
        "checks": [
            {
                "name": "evidence_pipeline_smoke",
                "mandatory": True,
                "passed": True,
                "detail": (
                    "P0 placeholder check — schema + CI wiring only, no engineering result yet."
                ),
            },
            spike_check,
        ],
        "warnings": [
            "No property model, flowsheet, or optimization checks exist yet (C1-C3).",
            "NRTL parameters in the C0 spike are unsourced placeholders, not IPA/water data.",
        ],
    }
    if solver is not None:
        summary["solver"] = solver
    return summary


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    summary = build_summary()
    jsonschema.validate(instance=summary, schema=schema)

    OUTPUT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {OUTPUT_PATH}")

    mandatory_failures = [c for c in summary["checks"] if c["mandatory"] and not c["passed"]]
    if mandatory_failures:
        print(f"FAILED mandatory checks: {mandatory_failures}", file=sys.stderr)
        return 1

    print("all mandatory checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
