"""Proves the case-manifest evidence pipeline (schema + a conformant record)
end to end before any real case exists — cases land at Gate C4. Mirrors what
scripts/validate.py already does for validation-summary.schema.json at P0.

Delete the "no real case exists" assumption once Gate C4 lands and this
fixture is replaced by a real make-cases-produced manifest.
"""

import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = ROOT / "evidence" / "case-manifest.schema.json"
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "case_manifest_example.json"


def test_hand_written_fixture_conforms_to_case_manifest_schema():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(instance=fixture, schema=schema)


def test_schema_rejects_missing_required_field():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    del fixture["solver"]
    try:
        jsonschema.validate(instance=fixture, schema=schema)
    except jsonschema.ValidationError:
        return
    raise AssertionError("schema should reject a manifest missing solver")
