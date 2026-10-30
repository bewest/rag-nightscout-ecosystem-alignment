"""Identity conformance cases (queue item SPEC-ID-AMEND).

Contract: docs/30-design/platform/spec/identity.md (I2's API split, and §5
`ID-ABSENT-DECISION`). Every case under specs/sync/conformance/identity/ is in
the instance case format (registration-submit.schema.json#/$defs/instanceCase)
and validates against it, and the reference (tools/nsschema/instances.py with
quirks_registration.py; a reference and not a hub) reproduces its expected
outcome. Each refusal names a passing control that differs only in the aspect
under test.
"""

import copy
import datetime
import json
import re

import jsonschema
import pytest
import yaml

from nsschema import corpus, instances, negotiate, quirks_registration

ROOT = corpus.repo_root()
GRAMMAR = json.loads((ROOT / negotiate.GRAMMAR_SCHEMA).read_text())
SUBMIT_SCHEMA = json.loads((ROOT / negotiate.SUBMIT_SCHEMA).read_text())
CASES_DIR = ROOT / "specs/sync/conformance/identity"
CASE_PATHS = sorted(CASES_DIR.glob("*.yaml"))
CASES = {p.stem: yaml.safe_load(p.read_text()) for p in CASE_PATHS}
IDS = sorted(CASES)

REQUIRED = {
    # I2: API v3 refuses a client `_id` in every form; API v1 keeps an ObjectId
    "v3-client-id-refused", "v3-client-oid-refused", "v3-client-uuid-id-refused",
    "v3-identifier-written", "v1-client-id-kept",
    # ID-ABSENT-DECISION: SHOULD for legacy writers, MUST for registered instances
    "legacy-without-identifier-written", "registered-instance-identifier-written",
}
SUCCESS = {"written"}
SYNTHETIC_UUID = re.compile(r"^00000000-0000-[47]000-8000-0000000000[0-9a-fA-F]{2}$")
UUID_FORM = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _strip_detail(value):
    if isinstance(value, dict):
        return {k: _strip_detail(v) for k, v in value.items() if k != "detail"}
    if isinstance(value, list):
        return [_strip_detail(v) for v in value]
    return value


def _run(case):
    return _strip_detail(instances.run_case(copy.deepcopy(case), GRAMMAR))


def _write(cid):
    return CASES[cid]["request"]["write"]


def test_the_required_cases_exist():
    assert REQUIRED <= set(IDS), REQUIRED - set(IDS)


@pytest.mark.parametrize("cid", IDS)
def test_case_validates_against_the_case_schema(cid):
    validator = jsonschema.Draft202012Validator(
        {"$ref": "#/$defs/instanceCase", "$defs": SUBMIT_SCHEMA["$defs"]})
    assert list(validator.iter_errors(CASES[cid])) == []
    assert CASES[cid]["id"] == cid


@pytest.mark.parametrize("cid", IDS)
def test_the_reference_reproduces_the_expected_outcome(cid):
    assert _run(CASES[cid]) == CASES[cid]["expected"]


@pytest.mark.parametrize("cid", [i for i in IDS
                                 if CASES[i]["expected"]["response"]["outcome"] == "rejected"])
def test_every_refusal_has_a_passing_control_on_the_same_api(cid):
    case = CASES[cid]
    control = CASES[case["control"]]
    assert control["expected"]["response"]["outcome"] in SUCCESS
    assert _write(cid)["api"] == control["request"]["write"]["api"]
    assert "_id" in _write(cid)["sent"] and "_id" not in control["request"]["write"]["sent"]


@pytest.mark.parametrize("cid", [i for i in IDS if _write(i).get("api") == "v3"
                                 and "_id" in _write(i).get("sent", {})])
def test_api_v3_refuses_a_client_id_and_writes_nothing(cid):
    # I2 (maintainer, 2026-10-25; BF-170): 400, no ids, the stored state unchanged.
    expected = CASES[cid]["expected"]
    assert expected["response"]["status"] == 400
    assert "write" not in expected["response"]
    assert expected["stateAfter"] == CASES[cid]["hubState"]


def test_the_same_id_is_kept_over_v1_and_refused_over_v3():
    v1, v3 = _write("v1-client-id-kept"), _write("v3-client-id-refused")
    assert v1["sent"] == v3["sent"] and (v1["api"], v3["api"]) == ("v1", "v3")
    assert CASES["v1-client-id-kept"]["expected"]["response"]["write"]["ids"]["_id"] == \
        v1["sent"]["_id"].lower()


def test_a_registered_instance_write_carries_identifier_and_the_reply_returns_it():
    case = CASES["registered-instance-identifier-written"]
    w = case["request"]["write"]
    assert instances.find_instance(case["hubState"], w["instanceId"]) is not None
    reply = case["expected"]["response"]["write"]
    assert reply["attributedTo"]["instanceId"] == w["instanceId"]
    assert reply["ids"]["identifier"] == w["sent"]["identifier"]


def test_a_legacy_write_without_identifier_is_accepted():
    case = CASES["legacy-without-identifier-written"]
    assert "instanceId" not in case["request"]["write"]
    assert case["request"]["write"]["sent"] == {}
    reply = case["expected"]["response"]
    assert reply["outcome"] == "written" and reply["write"]["ids"]["identifier"] is None


def test_cases_are_synthetic():
    for path in CASE_PATHS:
        text = path.read_text()
        assert text.startswith("# SYNTHETIC CONFORMANCE CASE."), path.name
        assert "@" not in text, path.name
        for value in UUID_FORM.findall(text):
            assert SYNTHETIC_UUID.match(value), (path.name, value)


def test_assigned_object_ids_carry_the_hub_receipt_time():
    for cid, case in CASES.items():
        now = int(datetime.datetime.fromisoformat(case["now"].replace("Z", "+00:00")).timestamp())
        for oid in case.get("assignedIds") or []:
            assert quirks_registration.is_object_id(oid)
            assert int(oid[:8], 16) == now, (cid, oid)
