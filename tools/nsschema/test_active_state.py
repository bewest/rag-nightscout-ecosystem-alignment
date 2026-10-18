"""What a hub reports as active at a time (queue item SPEC-ACTIVE-STATE).

State and intent §6, rules A1-A12. Each case under
specs/sync/conformance/active-state/ carries hand-authored expectations; the
reference decision function in active_state.py must reproduce them. A case
that names a control is a refusal or a difference whose passing counterpart is
that control, so a test cannot pass because everything is empty.
"""
import json

import jsonschema
import pytest
import yaml

from nsschema import active_state, corpus

ROOT = corpus.repo_root()
CASES_DIR = ROOT / "specs" / "sync" / "conformance" / "active-state"
CASES = {p.stem: yaml.safe_load(p.read_text()) for p in sorted(CASES_DIR.glob("*.yaml"))}
SCHEMA = json.loads((ROOT / "specs/sync/controller-state-model.schema.json").read_text())


def _order(rows):
    return sorted(rows, key=lambda r: (r["product"], r["kind"], r["layer"], r["start"], r["key"]))


def test_there_are_cases():
    assert len(CASES) >= 20


@pytest.mark.parametrize("cid", sorted(CASES))
def test_case_id_matches_its_file(cid):
    assert CASES[cid]["id"] == cid


@pytest.mark.parametrize("cid", sorted(CASES))
def test_declarations_are_grammar_valid(cid):
    span_schema = dict(SCHEMA["properties"]["spec"]["properties"]["stateSpans"]["items"])
    span_schema["$defs"] = SCHEMA["$defs"]
    validator = jsonschema.Draft202012Validator(span_schema)
    for decl in CASES[cid]["declarations"]:
        for span in decl["stateSpans"]:
            errors = list(validator.iter_errors(span))
            assert not errors, [e.message for e in errors]


@pytest.mark.parametrize("cid", sorted(CASES))
def test_instances(cid):
    case = CASES[cid]
    assert active_state.summary(case) == _order(case["expected"]["instances"])


@pytest.mark.parametrize("cid", sorted(CASES))
def test_active_at(cid):
    case = CASES[cid]
    for query in case["expected"]["activeAt"]:
        assert active_state.active_at(case, query["at"]) == _order(query["active"]), query["at"]


@pytest.mark.parametrize("cid", sorted(c for c in CASES if CASES[c].get("control")))
def test_control_exists_and_differs(cid):
    case = CASES[cid]
    control = CASES[case["control"]]
    assert control["id"] != cid
    assert (control["expected"] != case["expected"]
            or control["records"] != case["records"]), "a control must differ in what it tests"


@pytest.mark.parametrize("cid", sorted(c for c in CASES if "stateVersion" in CASES[c]["expected"]))
def test_state_version(cid):
    case = CASES[cid]
    spec = case["expected"]["stateVersion"]
    product = spec["product"]
    version = lambda c, at: active_state.state_version(c, product, at)
    for a, b in spec.get("equal", []):
        assert version(case, a) == version(case, b)
    for a, b in spec.get("differ", []):
        assert version(case, a) != version(case, b)
    for other in spec.get("differFromCase", []):
        assert version(case, other["at"]) != version(CASES[other["case"]], other["at"])
    assert version(case, spec["equal"][0][0]).startswith("sha256:")


@pytest.mark.parametrize("cid", sorted(CASES))
def test_unreadable_kinds(cid):
    # A11: a unit is never assumed; the kind is reported, the rest still answers.
    case = CASES[cid]
    assert active_state.unreadable(case) == case["expected"].get("unreadable", [])


def test_the_hub_never_composes():
    # A1, S1: two active instances are reported as two rows, never merged.
    case = CASES["products-never-supersede-each-other"]
    rows = active_state.active_at(case, case["expected"]["activeAt"][0]["at"])
    assert len(rows) == 2 and {r["product"] for r in rows} == {"ControllerA", "ControllerB"}
