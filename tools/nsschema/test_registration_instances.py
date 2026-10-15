"""Registration definitions and instances: D19 (queue item SPEC-REG-INSTANCE).

Execution plan §2.6.2; contract in the hub-sync design §3.6. Every conformance
case under specs/sync/conformance/instances/ validates against the schemas,
and the reference (tools/nsschema/instances.py, which extends negotiate.py; a
reference and not a hub) reproduces its expected outcome. Each refusal names
a passing control, and each rule below is tested against a control that
differs from it only in the aspect under test.
"""

import copy
import datetime
import hashlib
import json
import re

import jsonschema
import pytest
import yaml

from nsschema import corpus, instances, negotiate, sync_model

ROOT = corpus.repo_root()
GRAMMAR = json.loads((ROOT / negotiate.GRAMMAR_SCHEMA).read_text())
CAPS_SCHEMA = json.loads((ROOT / negotiate.CAPABILITIES_SCHEMA).read_text())
SUBMIT_SCHEMA = json.loads((ROOT / negotiate.SUBMIT_SCHEMA).read_text())
INSTANCE_SCHEMA = json.loads((ROOT / instances.INSTANCE_SCHEMA).read_text())
CASE_PATHS = sorted((ROOT / instances.CASES_DIR).glob("*.yaml"))
CASES = {p.stem: yaml.safe_load(p.read_text()) for p in CASE_PATHS}
IDS = sorted(CASES)

# The cases the queue gate names, by id.
REQUIRED = {
    # a definition id reproduced from canonical JSON; two definitions coexisting
    "definition-put", "definition-id-mismatch", "definition-retry-noop",
    # version-conflict, with a differing-version control and a non-meaning control
    "definition-version-conflict", "definition-extension-version-conflict",
    "definition-same-meaning", "product-update-version-conflict", "product-update-new-version",
    # a well-known kind referenced, not copied
    "definition-wellknown-ref", "definition-wellknown-ref-unknown",
    "definition-wellknown-copy-agrees", "definition-wellknown-copy-conflicts",
    # leases
    "instance-create", "instance-renew", "instance-handoff-lapse",
    # role-held with a simulated control; overlaps
    "instance-role-held", "instance-role-simulated", "instance-overlap-listed",
    # handoff by release, lapse and owner transfer
    "instance-handoff-release", "instance-delete", "owner-transfer-role",
    "lapsed-role-not-auto-assigned",
    # one destination per command channel
    "command-routed", "command-no-destination-simulated",
    # labels
    "instance-label-not-namespaced", "instance-label-reserved-unknown",
    "instance-label-not-string", "instance-label-other-value",
    # read selection
    "select-live-device", "select-newest-stored", "select-owner-pin", "select-label-selector",
    "select-capability-limit",
    # projected carrier view
    "project-served", "write-projected-read-only", "carrier-view-needs-mapping",
    # retention
    "retention-eligible", "retention-referenced", "retention-in-use",
    # older controllers lose nothing
    "typed-write-instance-required", "typed-write-hub-without-instances",
    "carrier-write-claimant", "carrier-write-older-controller", "carrier-write-older-hub",
}
CELLS = {"older-controller/older-hub", "older-controller/newer-hub",
         "newer-controller/older-hub", "newer-controller/newer-hub"}
SUCCESS = {"accepted", "partial", "released", "applied", "listed", "routed", "selected",
           "projected", "written", "eligible"}
SYNTHETIC_INSTANCE = re.compile(r"^00000000-0000-4000-8000-0000000000[0-9a-f]{2}$")


def _def(schema, name):
    return jsonschema.Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": schema["$defs"]})


def _errors(validator, doc):
    return list(validator.iter_errors(doc))


def _strip_detail(value):
    if isinstance(value, dict):
        return {k: _strip_detail(v) for k, v in value.items() if k != "detail"}
    if isinstance(value, list):
        return [_strip_detail(v) for v in value]
    return value


def _codes(response):
    return [r["code"] for r in response.get("reasons") or []]


def _response(cid):
    return CASES[cid]["expected"]["response"]


def _run(cid, **changes):
    case = copy.deepcopy(CASES[cid])
    for key, value in changes.items():
        if key == "request":
            case["request"].update(value)
        else:
            case[key] = value
    return instances.run_case(case, GRAMMAR)["response"]


def _refuses(response):
    if response["outcome"] in ("rejected", "precondition-failed", "not-found", "not-eligible"):
        return True
    return any(e["result"] == "rejected" for e in response.get("elements") or []) or \
        any(r["result"] == "refused" for r in response.get("roles") or [])


# ── schemas and the case set ──────────────────────────────────────────

@pytest.mark.parametrize("schema", [INSTANCE_SCHEMA, CAPS_SCHEMA, SUBMIT_SCHEMA, GRAMMAR],
                         ids=["instance", "capabilities", "submit", "grammar"])
def test_schemas_are_valid_2020_12_schemas(schema):
    jsonschema.Draft202012Validator.check_schema(schema)


def test_the_required_cases_and_all_four_cells_exist():
    assert REQUIRED <= set(IDS), REQUIRED - set(IDS)
    assert {c["cell"] for c in CASES.values()} == CELLS


@pytest.mark.parametrize("cid", IDS)
def test_case_validates_against_the_case_schema(cid):
    case = CASES[cid]
    assert _errors(_def(SUBMIT_SCHEMA, "instanceCase"), case) == []
    assert case["id"] == cid


@pytest.mark.parametrize("cid", IDS)
def test_case_capabilities_are_a_valid_capability_document(cid):
    caps = CASES[cid]["capabilities"]
    if caps is None:
        return
    assert _errors(jsonschema.Draft202012Validator(CAPS_SCHEMA), caps) == []
    assert negotiate.capability_problems(caps) == []


@pytest.mark.parametrize("cid", IDS)
def test_stored_state_is_consistent(cid):
    """Definition ids, instance etags and ids, the stored registrations'
    grammar validity and the one-holder invariant, before and after."""
    case = CASES[cid]
    states = [case["hubState"]] + ([case["expected"]["stateAfter"]]
                                   if case["expected"].get("stateAfter") else [])
    grammar = jsonschema.Draft202012Validator(GRAMMAR)
    instance_schema = jsonschema.Draft202012Validator(INSTANCE_SCHEMA)
    for state in states:
        for entry in state.get("definitions") or []:
            assert entry["definitionId"] == negotiate.definition_id(entry["definition"])
            assert not _errors(grammar, entry["definition"])
        for stored in state.get("instances") or []:
            assert SYNTHETIC_INSTANCE.match(stored["instanceId"]), stored["instanceId"]
            assert not _errors(instance_schema, stored["instance"])
            assert stored["etag"] == instances.instance_etag(
                stored["instance"], stored["boundTo"], instances.granted(stored))
        for channel in {g["channel"] for s in state.get("instances") or []
                        for g in instances.granted(s)}:
            for role in ("source", "command-sink"):
                instances.holder(state, channel, role, case["now"])  # raises on two


@pytest.mark.parametrize("cid", IDS)
def test_the_reference_reproduces_the_expected_outcome(cid):
    computed = instances.run_case(copy.deepcopy(CASES[cid]), GRAMMAR)
    assert _strip_detail(computed) == CASES[cid]["expected"]


@pytest.mark.parametrize("cid", IDS)
def test_the_reference_does_not_mutate_its_inputs(cid):
    case = CASES[cid]
    before = copy.deepcopy(case)
    instances.run_case(case, GRAMMAR)
    assert case == before


@pytest.mark.parametrize("cid", [i for i in IDS if _refuses(_response(i))])
def test_every_refusal_has_a_passing_control(cid):
    case = CASES[cid]
    assert "control" in case, cid
    control = CASES[case["control"]]
    response = control["expected"]["response"]
    assert response["outcome"] in SUCCESS, case["control"]
    inputs = ("capabilities", "hubState", "submitter", "request", "body", "now")
    assert any(case.get(k) != control.get(k) for k in inputs)
    # What is refused here is accepted or granted there.
    ok_elements = {e["element"] for e in response.get("elements") or []
                   if e["result"] in negotiate.ACCEPTED}
    for element in _response(cid).get("elements") or []:
        if element["result"] == "rejected":
            assert element["element"] in ok_elements, element
    # A role refused here is granted in the control wherever the control claims
    # it; a case whose aspect under test is the claim itself (an unknown channel,
    # an unlisted role) shows the rest of the instance granted instead.
    ok_roles = {(r["channel"], json.dumps(r["role"])) for r in response.get("roles") or []
                if r["result"] == "granted"}
    claimed = {(r["channel"], json.dumps(r["role"])) for r in response.get("roles") or []}
    for role in _response(cid).get("roles") or []:
        key = (role["channel"], json.dumps(role["role"]))
        if role["result"] == "refused" and key in claimed:
            assert key in ok_roles, role
    for role in _response(cid).get("roles") or []:
        key = (role["channel"], json.dumps(role["role"]))
        if key in ok_roles and key not in {(r["channel"], json.dumps(r["role"]))
                                           for r in _response(cid)["roles"]
                                           if r["result"] == "refused"}:
            assert role["result"] == "granted", role


def test_cases_are_synthetic():
    # Rule 3 of the item: no names, device names, emails or serials.
    for path in CASE_PATHS:
        text = path.read_text()
        assert "@" not in text, path.name
        assert text.startswith("# SYNTHETIC CONFORMANCE CASE."), path.name
        for value in re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
                                text):
            assert SYNTHETIC_INSTANCE.match(value), (path.name, value)


# ── rule 1: content-addressed definitions ─────────────────────────────

def test_a_definition_id_is_the_hash_of_its_canonical_json():
    body = CASES["definition-put"]["body"]
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False).encode()
    wanted = "sha256:" + hashlib.sha256(canonical).hexdigest()
    assert negotiate.definition_id(body) == wanted
    assert _response("definition-put")["definitionId"] == wanted
    assert CASES["definition-put"]["request"]["definitionId"] == wanted
    # Key order does not change it; content does.
    assert negotiate.definition_id(json.loads(json.dumps(body, sort_keys=True))) == wanted
    changed = copy.deepcopy(body)
    changed["metadata"]["versionRange"] = "9.9.9-test"
    assert negotiate.definition_id(changed) != wanted


def test_the_product_response_names_its_definition_id():
    # The §3.5 cases gained `definitionId` on accepted and partial responses only.
    for path in sorted((ROOT / negotiate.CONFORMANCE_DIR).glob("*.yaml")):
        case = yaml.safe_load(path.read_text())
        response = case["expected"]["response"]
        if response and response["outcome"] in ("accepted", "partial"):
            assert response["definitionId"] == negotiate.definition_id(case["registration"])
        elif response:
            assert "definitionId" not in response, path.name


def test_two_definitions_coexist_and_the_product_etag_does_not_move():
    case = CASES["definition-put"]
    before, after = case["hubState"], case["expected"]["stateAfter"]
    assert after["registrations"] == before["registrations"]
    stored = negotiate.product_definitions(after, ("Example", "ControllerA"))
    assert len(stored) == 3 and case["request"]["definitionId"] in stored
    assert _response("definition-put")["registration"]["etag"] == before["registrations"][0]["etag"]
    # A retried identical PUT is a no-op that stores nothing more.
    noop = CASES["definition-retry-noop"]
    assert (_response("definition-retry-noop")["status"], _response("definition-retry-noop")["noop"]) \
        == (200, True)
    assert noop["expected"]["stateAfter"] == noop["hubState"]


def test_a_definition_is_authorised_by_the_product_binding():
    assert _codes(_response("definition-not-registration-owner")) == ["not-registration-owner"]
    # Checked before the precondition: no precondition still answers 403.
    response = _run("definition-not-registration-owner", request={"preconditions": {}})
    assert _codes(response) == ["not-registration-owner"]
    # Control: the bound subject without a precondition reaches 428.
    response = _run("definition-put", request={"preconditions": {}})
    assert response["status"] == 428
    # A released product is not bound by a definition PUT.
    released = copy.deepcopy(CASES["definition-put"]["hubState"])
    released["registrations"][0] = negotiate._restate(released["registrations"][0], boundTo=None)
    assert _codes(_run("definition-put", hubState=released)) == ["not-registration-owner"]


def test_a_mismatched_definition_id_stores_nothing():
    case = CASES["definition-id-mismatch"]
    assert (_response("definition-id-mismatch")["status"],
            _codes(_response("definition-id-mismatch"))) == (422, ["definition-id-mismatch"])
    assert case["expected"]["stateAfter"] == case["hubState"]


def test_namespaces_belong_to_the_product_across_its_definitions():
    rejected = [e for e in _response("definition-namespace-claimed")["elements"]
                if e["result"] == "rejected"]
    assert [(e["element"], _codes(e)) for e in rejected] == [
        ("extensions/com.example.shared.feature", ["namespace-claimed"])]
    # The holder's declaration is in a stored definition, not its current registration.
    holder = negotiate._find(CASES["definition-namespace-claimed"]["hubState"],
                             ("Example", "ControllerB"))
    assert "com.example.shared.feature" not in negotiate._declared_namespaces(holder["registration"])
    assert _response("definition-namespace-own")["outcome"] == "accepted"


# ── rule 2: one kind at one version has one meaning ───────────────────

def test_a_kind_typed_differently_at_one_version_is_rejected():
    rejected = {e["element"]: _codes(e) for e in _response("definition-version-conflict")["elements"]
                if e["result"] == "rejected"}
    assert rejected == {"stateSpans/ExampleOverride": ["version-conflict"]}
    # Control: the same retyping at version 2 (definition-put's DA3) is accepted.
    put = CASES["definition-put"]["body"]["spec"]["stateSpans"][0]
    conflict = CASES["definition-version-conflict"]["body"]["spec"]["stateSpans"][0]
    assert {k: v for k, v in put.items() if k != "version"} == \
        {k: v for k, v in conflict.items() if k != "version"}
    assert (put["version"], conflict["version"]) == ("2", "1")
    assert _response("definition-put")["outcome"] == "accepted"
    ext = _response("definition-extension-version-conflict")["elements"][1]
    assert (ext["result"], _codes(ext)) == ("rejected", ["version-conflict"])


def test_the_product_resource_compares_with_its_stored_definitions():
    rejected = [e for e in _response("product-update-version-conflict")["elements"]
                if e["result"] == "rejected"]
    assert [_codes(e) for e in rejected] == [["version-conflict"]]
    for cid in ("product-update-version-conflict", "product-update-new-version"):
        after = CASES[cid]["expected"]["stateAfter"]
        old = CASES[cid]["hubState"]["registrations"][0]["registration"]
        # The replaced registration stays stored as a definition.
        assert negotiate.definition_id(old) in {d["definitionId"] for d in after["definitions"]}
    assert _response("product-update-new-version")["outcome"] == "accepted"


def _span_pair(member, value):
    base = copy.deepcopy(CASES["definition-put"]["hubState"]["registrations"][0]["registration"])
    other = copy.deepcopy(base)
    other["metadata"]["versionRange"] = "1.0.9-test"
    other["spec"]["stateSpans"][0][member] = value
    return base, other


MEANING_CHANGES = {
    "category": "OtherCategory", "slot": "elsewhere", "exclusiveWithinSlot": True,
    "coexistsWith": ["temporaryTarget"], "overlay": True, "supersedes": True,
    "states": ["active"], "endReasons": [{"reason": "expired"}],
    "wire": {"collection": "treatments", "eventType": "Other"},
    "dualWriteLink": {"typedIdPath": "a", "carrierIdPath": "b"},
    "requested": {"collection": "treatments"}, "applied": {"collection": "devicestatus"},
    "initiators": {"values": ["user"]}, "definitions": {"referencedBy": "id"},
    "acceptsFromHub": {"channels": []}, "horizon": {"class": "aggregate"},
}
NON_MEANING_CHANGES = {"description": "Reworded.", "evidence": [{"source": "x", "basis": "read"}],
                       "availability": "experimental", "futureMember": 1}


@pytest.mark.parametrize("member", sorted(MEANING_CHANGES))
def test_each_meaning_member_is_compared(member):
    base, other = _span_pair(member, MEANING_CHANGES[member])
    assert negotiate.meaning("stateSpans", base["spec"]["stateSpans"][0]) != \
        negotiate.meaning("stateSpans", other["spec"]["stateSpans"][0])
    assert member in negotiate.SPAN_MEANING


@pytest.mark.parametrize("member", sorted(NON_MEANING_CHANGES))
def test_non_meaning_members_are_not_compared(member):
    base, other = _span_pair(member, NON_MEANING_CHANGES[member])
    assert negotiate.meaning("stateSpans", base["spec"]["stateSpans"][0]) == \
        negotiate.meaning("stateSpans", other["spec"]["stateSpans"][0])


def test_order_and_prose_inside_a_meaning_member_are_not_meaning():
    base, other = _span_pair("states", ["ended", "active", "scheduled"])
    other["spec"]["stateSpans"][0]["wire"]["description"] = "prose"
    assert negotiate.meaning("stateSpans", base["spec"]["stateSpans"][0]) == \
        negotiate.meaning("stateSpans", other["spec"]["stateSpans"][0])
    assert _response("definition-same-meaning")["outcome"] == "accepted"


def test_extension_fields_are_compared_by_name_and_typing():
    ext = CASES["definition-put"]["body"]["spec"]["extensions"]["com.example.controllera.targets"]
    reordered = copy.deepcopy(ext)
    reordered["fields"].reverse()
    reordered["fields"][0]["description"] = "prose"
    assert negotiate.meaning("extensions", ext) == negotiate.meaning("extensions", reordered)
    retyped = copy.deepcopy(ext)
    retyped["fields"][0]["sensitivity"] = {"level": "identifying", "category": "free-text"}
    assert negotiate.meaning("extensions", ext) != negotiate.meaning("extensions", retyped)


# ── rule 1: well-known references ─────────────────────────────────────

def test_a_well_known_kind_is_referenced_not_copied():
    assert _response("definition-wellknown-ref")["outcome"] == "accepted"
    bad = [e for e in _response("definition-wellknown-ref-unknown")["elements"]
           if e["result"] == "rejected"]
    assert [_codes(e) for e in bad] == [["unknown-well-known-kind"]]
    restated = [e for e in _response("definition-wellknown-ref-restated")["elements"]
                if e["result"] == "rejected"]
    assert [_codes(e) for e in restated] == [["invalid-element"]]
    assert _response("definition-wellknown-copy-agrees")["outcome"] == "accepted"
    conflict = [e for e in _response("definition-wellknown-copy-conflicts")["elements"]
                if e["result"] == "rejected"]
    assert [_codes(e) for e in conflict] == [["version-conflict"]]


def test_a_referenced_kind_falls_back_to_the_catalogue_carrier():
    case = CASES["definition-wellknown-ref-unknown"]
    plan = negotiate.fallback(case["body"], _response("definition-wellknown-ref-unknown"),
                              case["capabilities"], case["wellKnownRegistrations"])
    # The unknown version resolves nothing, so the plan writes nothing typed for it.
    assert plan["stateSpans/LegacyOverride"]["write"] != "typed"
    ok = CASES["definition-wellknown-ref"]
    rejected = {"apiVersion": negotiate.GRAMMAR_API, "outcome": "rejected"}
    plan = negotiate.fallback(ok["body"], rejected, ok["capabilities"], ok["wellKnownRegistrations"])
    catalogue = ok["wellKnownRegistrations"]["/.well-known/nightscout/controllers/example-legacy"]
    assert plan["stateSpans/LegacyOverride"] == {"write": "carrier",
                                                 "carrier": catalogue["spec"]["stateSpans"][0]["wire"]}


def test_the_strict_view_knows_the_well_known_reference():
    body = CASES["definition-wellknown-ref"]["body"]
    assert sync_model.unknown_grammar_fields(body, GRAMMAR) == []
    misspelt = copy.deepcopy(body)
    misspelt["spec"]["stateSpans"][0]["wellKnownReference"] = \
        misspelt["spec"]["stateSpans"][0].pop("wellKnownRef")
    assert sync_model.unknown_grammar_fields(misspelt, GRAMMAR) == [
        "spec.stateSpans.0.wellKnownReference"]
    missing = copy.deepcopy(body)
    del missing["spec"]["stateSpans"][0]["wellKnownRef"]["version"]
    assert _errors(jsonschema.Draft202012Validator(GRAMMAR), missing)


def test_the_generated_registrations_declare_no_kind_versions_yet():
    # Why none of their kinds can be referenced (reported, not changed here).
    for name in ("loop", "trio", "androidaps"):
        reg = yaml.safe_load((ROOT / sync_model.OUT_DIR / f"{name}.yaml").read_text())
        assert all(negotiate.stored_version(s) is None for s in reg["spec"]["stateSpans"]), name


# ── rule 4: instances ─────────────────────────────────────────────────

def _plus(now, seconds):
    t = datetime.datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ") + datetime.timedelta(seconds=seconds)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_a_lease_runs_for_the_advertised_length_and_a_renewal_moves_it():
    for cid in ("instance-create", "instance-renew", "instance-handoff-lapse"):
        case = CASES[cid]
        lease = _response(cid)["instance"]["leaseExpiresAt"]
        assert lease == _plus(case["now"], case["capabilities"]["instances"]["leaseSeconds"]), cid
    renew = CASES["instance-renew"]
    before = renew["hubState"]["instances"][0]
    assert _response("instance-renew")["noop"] is True
    assert _response("instance-renew")["instance"]["etag"] == before["etag"]
    assert _response("instance-renew")["instance"]["leaseExpiresAt"] > before["leaseExpiresAt"]


def test_an_instance_lapses_when_its_lease_ends():
    stored = CASES["instance-renew"]["hubState"]["instances"][0]
    assert instances.live(stored, _plus(stored["leaseExpiresAt"], -1))
    assert not instances.live(stored, stored["leaseExpiresAt"])


def test_an_instance_id_is_a_random_uuid_v4_never_a_device_name():
    assert _codes(_response("instance-invalid-id")) == ["invalid-instance-id"]
    for bad in ("example-phone-name", "00000000-0000-7000-8000-00000000000a",
                "00000000-0000-4000-8000-00000000000A", "0000000000004000800000000000000a"):
        assert not instances.INSTANCE_ID.match(bad), bad
    assert instances.INSTANCE_ID.match(CASES["instance-create"]["request"]["instanceId"])


def test_an_instance_carries_no_hardware_identifiers():
    # The upstream RFC's ControllerInstanceRegistration has these; D19 rule 4 does not.
    members = json.dumps(INSTANCE_SCHEMA["properties"])
    for upstream in ("deviceId", "pumpSerial", "cgmId", "model", "pumpBinding", "cgmBinding"):
        assert upstream not in members, upstream


def test_an_instance_is_bound_to_its_creator_not_to_the_product():
    assert _response("instance-create-other-subject")["status"] == 201
    stored = CASES["instance-create-other-subject"]["expected"]["stateAfter"]["instances"]
    dev = [s for s in stored if s["instanceId"].endswith("0d")][0]
    assert dev["boundTo"] == {"kind": "subject", "subject": "subject-test-dev-build"}
    assert _codes(_response("instance-not-registration-owner")) == ["not-registration-owner"]


def test_an_instance_names_a_stored_definition_of_its_product():
    assert _codes(_response("instance-unknown-definition")) == ["unknown-definition"]
    assert _response("instance-create")["instance"]["definitionId"] == \
        CASES["instance-create"]["body"]["definitionId"]


def test_delete_releases_the_instance_and_its_roles():
    case = CASES["instance-delete"]
    assert _response("instance-delete")["outcome"] == "released"
    ids = {s["instanceId"] for s in case["expected"]["stateAfter"]["instances"]}
    assert case["request"]["instanceId"] not in ids
    assert instances.holder(case["expected"]["stateAfter"], "override", "source", case["now"]) is None
    assert instances.holder(case["hubState"], "override", "source", case["now"]) == \
        case["request"]["instanceId"]


# ── rules 5 and 6: roles, provenance, exclusivity ─────────────────────

def _role_results(cid):
    return {(r["channel"], json.dumps(r["role"])): (r["result"], _codes(r))
            for r in _response(cid).get("roles") or []}


def test_a_second_device_source_is_refused_and_a_simulated_one_is_not():
    held = _role_results("instance-role-held")
    assert held[("override", '"source"')] == ("refused", ["role-held"])
    assert held[("override", '"command-sink"')] == ("refused", ["role-held"])
    assert [v for k, v in held.items() if k[0] != "override"] == [("granted", [])]
    assert all(v == ("granted", []) for v in _role_results("instance-role-simulated").values())
    # The refused claimant writes the override kind as its carrier.
    plan = CASES["instance-role-held"]["expected"]["plan"]
    assert plan["stateSpans/ExampleOverride"]["write"] == "carrier"
    assert CASES["instance-role-simulated"]["expected"]["plan"]["stateSpans/ExampleOverride"] == \
        {"write": "typed"}


def test_the_overlap_is_listed_with_its_holder_until_the_claim_ends():
    overlaps = _response("instance-overlap-listed")["overlaps"]
    assert {(o["channel"], o["role"]) for o in overlaps} == {("override", "source"),
                                                              ("override", "command-sink")}
    assert all(o["holder"] and o["claimant"] != o["holder"] for o in overlaps)
    lapsed = _response("instance-overlap-holder-lapsed")["overlaps"]
    assert lapsed and all(o["holder"] is None for o in lapsed)


def test_provenance_is_required_and_closed():
    assert _role_results("instance-unknown-provenance")[("override", '"source"')] == \
        ("refused", ["unknown-provenance"])
    assert _codes(_response("instance-missing-provenance")) == ["invalid-instance"]
    assert INSTANCE_SCHEMA["$defs"]["provenance"]["enum"] == ["device", "simulated"]
    assert list(instances.PROVENANCE) == INSTANCE_SCHEMA["$defs"]["provenance"]["enum"]
    granted = _def(SUBMIT_SCHEMA, "roleResult")
    assert _errors(granted, {"channel": "x", "role": "source", "provenance": "hardware",
                             "result": "granted"})
    assert not _errors(granted, {"channel": "x", "role": "source", "provenance": "device",
                                 "result": "granted"})


def test_roles_are_an_open_vocabulary_the_hub_lists():
    assert _role_results("instance-unsupported-role")[
        ("override", json.dumps({"value": "other", "controllerTerm": "proposer"}))] == \
        ("refused", ["unsupported-role"])
    caps = copy.deepcopy(CASES["instance-unsupported-role"]["capabilities"])
    caps["instances"]["roles"].append({"value": "other", "controllerTerm": "proposer"})
    response = _run("instance-unsupported-role", capabilities=caps)
    assert response["outcome"] == "accepted"
    bad = copy.deepcopy(CASES["instance-create"]["body"])
    bad["roles"][0]["role"] = "proposer"
    assert list(jsonschema.Draft202012Validator(INSTANCE_SCHEMA).iter_errors(bad))


def test_channels_are_slots_shared_across_products_or_element_paths():
    case = CASES["instance-create"]
    definition = negotiate.product_definitions(case["hubState"], ("Example", "ControllerA"))[
        case["body"]["definitionId"]]
    chans = instances.channels(case["capabilities"], case["wellKnownRegistrations"], definition)
    assert set(chans) == {"override",
                          "Example/ControllerA/extensions/com.example.controllera.targets"}
    assert chans["override"]["commands"] is True
    assert chans["Example/ControllerA/extensions/com.example.controllera.targets"]["commands"] is False
    # A slot name with `/` derives no shared channel.
    odd = copy.deepcopy(definition)
    odd["spec"]["stateSpans"][0]["slot"] = "a/b"
    assert "Example/ControllerA/stateSpans/ExampleOverride" in \
        instances.channels(case["capabilities"], {}, odd)
    assert _role_results("instance-unknown-channel")[("temporaryTarget", '"source"')] == \
        ("refused", ["unknown-channel"])
    assert _role_results("instance-not-a-command-channel")[
        ("Example/ControllerA/extensions/com.example.controllera.targets", '"command-sink"')] == \
        ("refused", ["not-a-command-channel"])


def test_handoff_by_release_lapse_and_transfer():
    for cid in ("instance-handoff-lapse", "instance-handoff-release"):
        assert all(v[0] == "granted" for v in _role_results(cid).values()), cid
        before = CASES[cid]["hubState"]
        claimant = CASES[cid]["request"]["instanceId"]
        assert instances.holder(before, "override", "source", CASES[cid]["now"]) != claimant
        assert instances.holder(CASES[cid]["expected"]["stateAfter"], "override", "source",
                                CASES[cid]["now"]) == claimant
    # Control: while the holder is live, the claimant's renewal stays refused.
    assert _role_results("instance-renew-holder-live")[("override", '"source"')][0] == "refused"
    transfer = CASES["owner-transfer-role"]
    after = transfer["expected"]["stateAfter"]
    move = transfer["request"]["transferRole"]
    assert instances.holder(after, "override", "command-sink", transfer["now"]) == move["to"]
    for iid in (move["from"], move["to"]):
        assert instances.find_instance(after, iid)["etag"] != \
            instances.find_instance(transfer["hubState"], iid)["etag"]


def test_a_lapsed_role_is_not_auto_assigned():
    case = CASES["lapsed-role-not-auto-assigned"]
    claimant = instances.find_instance(case["hubState"], "00000000-0000-4000-8000-00000000000a")
    assert instances.live(claimant, case["now"])
    assert all(r["result"] == "refused" for r in claimant["roles"] if r["channel"] == "override")
    assert _codes(_response("lapsed-role-not-auto-assigned")) == ["no-command-destination"]


def test_the_owner_transfer_is_preconditioned_and_on_the_admin_listener():
    assert _response("owner-transfer-role-stale")["status"] == 412
    assert _codes(_response("owner-transfer-role-data-listener")) == ["not-authorised"]
    assert _codes(_response("owner-transfer-role-not-claimed")) == ["role-not-claimed"]
    assert _response("instance-renew-after-transfer-stale")["status"] == 412
    assert _role_results("instance-renew-after-transfer")[("override", '"command-sink"')] == \
        ("refused", ["role-held"])


def test_a_command_channel_has_one_destination():
    destination = _response("command-routed")["destination"]
    case = CASES["command-routed"]
    assert destination["instanceId"] == instances.holder(case["hubState"], "override",
                                                         "command-sink", case["now"])
    assert _codes(_response("command-no-destination-simulated")) == ["no-command-destination"]
    # The simulator does claim command-sink there; it is never a destination.
    sim = CASES["command-no-destination-simulated"]["hubState"]["instances"][0]
    assert any(r["role"] == "command-sink" and r["result"] == "granted" for r in sim["roles"])
    # Two device holders of one role are a broken invariant, never resolved by a guess.
    broken = copy.deepcopy(CASES["instance-overlap-listed"]["hubState"])
    for stored in broken["instances"]:
        for r in stored["roles"]:
            r.pop("reasons", None)
            r["result"] = "granted"
    with pytest.raises(ValueError):
        instances.holder(broken, "override", "command-sink", case["now"])


# ── rule 7: labels ────────────────────────────────────────────────────

def test_labels_are_strings_under_reverse_dns_keys():
    assert _codes(_response("instance-label-not-namespaced")) == ["invalid-label"]
    assert _codes(_response("instance-label-reserved-unknown")) == ["invalid-label"]
    assert _codes(_response("instance-label-not-string")) == ["invalid-label"]
    assert _response("instance-label-other-value")["outcome"] == "accepted"
    assert _response("instance-label-old-prefix")["outcome"] == "accepted"
    for key in ("com.example.testcontroller/rig", "dev.nightscout/purpose", "org.example/a.b-c"):
        assert instances.LABEL_KEY.match(key), key
    for key in ("purpose", "dev.nightscout", "Example.com/rig", "com.example/", "com/rig"):
        assert not instances.LABEL_KEY.match(key), key
    assert instances.LABEL_KEY.pattern == INSTANCE_SCHEMA["$defs"]["labelKey"]["pattern"]


def test_the_well_known_label_keys_and_values():
    assert set(instances.WELL_KNOWN_LABELS) == {"dev.nightscout/purpose", "dev.nightscout/build",
                                               "dev.nightscout/migration-group"}
    assert set(INSTANCE_SCHEMA["$defs"]["labels"]["properties"]) == set(instances.WELL_KNOWN_LABELS)
    assert instances.label_value("dev.nightscout/purpose", "weekend") == "other"
    assert instances.label_value("dev.nightscout/purpose", "lab") == "lab"
    assert instances.label_value("dev.nightscout/build", "nightly") == "other"
    assert instances.label_value("dev.nightscout/migration-group", "g-1") == "g-1"
    assert instances.RESERVED_LABEL_PREFIX == "dev.nightscout/"


# ── rule 3: read selection ────────────────────────────────────────────

def _selection(cid):
    return {k: (v["version"], v["by"]) for k, v in _response(cid)["selection"].items()}


EXT = "extensions/com.example.controllera.targets"


def test_the_read_selection_order():
    assert _selection("select-live-device")[EXT] == ("1", "live-device")
    assert _selection("select-newest-stored")[EXT] == ("2", "newest-stored")
    assert _selection("select-owner-pin")[EXT] == ("2", "owner-pin")
    assert _selection("select-label-selector")[EXT] == ("2", "label-selector")
    assert _selection("select-capability-limit")[EXT] == ("2", "newest-stored")
    # The pin in select-capability-limit names a version the operator does not accept.
    pins = CASES["select-capability-limit"]["hubState"]["pins"][0]["pins"]
    assert pins[EXT] == "3"


def test_a_pin_never_changes_stored_data_or_the_product_etag():
    case = CASES["owner-pin-version"]
    after = case["expected"]["stateAfter"]
    for key in ("registrations", "definitions", "instances", "records"):
        assert after[key] == case["hubState"][key], key
    assert after["pins"][0]["pins"] == {EXT: "2"}
    assert _codes(_response("owner-pin-unknown-version")) == ["unknown-version"]
    assert _response("owner-pin-stale")["status"] == 412


def test_version_order_is_numeric_by_part():
    assert max(["2", "10", "9"], key=instances._version_key) == "10"
    assert max(["1.2", "1.10"], key=instances._version_key) == "1.10"


# ── rule 8: the projected view for older readers ──────────────────────

def test_a_projected_document_is_labelled_and_carries_the_typed_id():
    projected = _response("project-served")["projected"]
    record = CASES["project-served"]["request"]["record"]
    document = projected["document"]
    assert document["identifier"] == record["id"] == document["_id"]
    assert document[instances.PROJECTION_MARKER] == {
        "definitionId": record["definitionId"], "element": record["element"],
        "entities": [record["id"]]}
    assert document["duration"] == record["durationSeconds"] / 60  # the wire's minutes
    assert _codes(_response("project-no-mapping")) == ["no-carrier-mapping"]


def test_a_projected_document_is_read_only():
    assert _codes(_response("write-projected-read-only")) == ["projected-read-only"]
    assert _response("write-stored-carrier")["outcome"] == "written"


def test_a_served_view_needs_a_declared_mapping():
    element = _response("carrier-view-needs-mapping")["elements"][0]
    assert (element["element"], element["carrierView"]) == ("stateSpans/ExampleOverride",
                                                            "not-served")
    assert CASES["carrier-view-needs-mapping"]["carrierViews"] == {
        "stateSpans/ExampleOverride": "served"}
    # Control: the §3.5 case whose kind has a wire is reported served.
    served = yaml.safe_load((ROOT / negotiate.CONFORMANCE_DIR /
                             "accepted-dual-write-view-served.yaml").read_text())
    assert served["expected"]["response"]["elements"][0]["carrierView"] == "served"


def test_the_dual_write_link_is_scoped_by_instance():
    assert _response("dual-write-linked")["write"]["linkedTo"] == \
        CASES["dual-write-linked"]["hubState"]["records"][0]["id"]
    assert _response("dual-write-not-linked-across-instances")["write"]["linkedTo"] is None


# ── older controllers never lose anything ─────────────────────────────

def test_typed_writes_need_an_instance_only_where_the_hub_advertises_instances():
    assert (_response("typed-write-instance-required")["status"],
            _codes(_response("typed-write-instance-required"))) == (422, ["instance-required"])
    assert not negotiate.is_load_refusal(_response("typed-write-instance-required")["status"])
    assert _response("typed-write-hub-without-instances")["outcome"] == "written"
    assert CASES["typed-write-hub-without-instances"]["expected"]["controllerWouldRegister"] is False
    assert _response("typed-write-attributed")["write"]["provenance"] == "device"
    assert _response("typed-write-simulated")["write"]["provenance"] == "simulated"
    assert _codes(_response("typed-write-role-held")) == ["role-held"]


def test_exclusivity_never_blocks_a_carrier_write():
    claimant = _response("carrier-write-claimant")["write"]
    assert claimant["accepted"] and claimant["attributedTo"]["instanceId"].startswith("00000000")
    older = _response("carrier-write-older-controller")["write"]
    assert older["attributedTo"] == {"vendor": "Example", "product": "LegacyController",
                                     "instanceId": "unregistered"}
    assert _response("carrier-write-older-hub")["write"] == {"accepted": True, "as": "carrier"}
    for cid in IDS:
        response = _response(cid)
        if CASES[cid]["request"]["action"] == "write" and \
                CASES[cid]["request"]["write"]["as"] == "carrier" and \
                not CASES[cid]["request"]["write"].get("target"):
            assert response["outcome"] == "written", cid


def test_the_observed_alias_is_identifying_and_withheld_by_default():
    after = CASES["observed-alias-recorded"]["expected"]["stateAfter"]["instances"][0]
    assert after["observedAliases"] == [{"value": "example-device-string",
                                         "sensitivity": {"level": "identifying",
                                                         "category": "device"}}]
    assert after["instanceId"] != "example-device-string"
    assert "observedAliases" not in _response("listing-withholds-alias")["instances"][0]
    assert "observedAliases" in _response("listing-includes-withheld")["instances"][0]
    assert "observedAliases" not in json.dumps(CAPS_SCHEMA)


# ── rule 9: retention ─────────────────────────────────────────────────

def test_a_definition_is_kept_while_anything_references_it():
    assert _response("retention-eligible")["outcome"] == "eligible"
    assert _codes(_response("retention-referenced")) == ["definition-referenced"]
    assert _codes(_response("retention-in-use")) == ["definition-in-use"]
    assert _codes(_response("retention-current")) == ["definition-current"]
    # "Not current" is not a reason: retention-referenced's definition is not current.
    case = CASES["retention-referenced"]
    current = negotiate.definition_id(case["hubState"]["registrations"][0]["registration"])
    assert case["request"]["definitionId"] != current


# ── the capability document's instances section ──────────────────────

def test_the_instances_section_states_the_lease_and_vocabularies():
    validator = jsonschema.Draft202012Validator(CAPS_SCHEMA)
    caps = copy.deepcopy(CASES["instance-create"]["capabilities"])
    assert not _errors(validator, caps)
    for broken in ({"leaseSeconds": 10}, {"channels": ["slot", "document"]},
                   {"roles": ["observer"]}, {"instanceId": "serial"}):
        bad = copy.deepcopy(caps)
        bad["instances"].update(broken)
        assert _errors(validator, bad), broken
    del caps["instances"]["leaseSeconds"]
    assert _errors(validator, caps)


def test_a_controller_registers_an_instance_only_on_a_hub_that_advertises_them():
    caps = CASES["instance-create"]["capabilities"]
    assert instances.should_register_instance(caps)
    no_instances = copy.deepcopy(caps)
    del no_instances["instances"]
    assert not instances.should_register_instance(no_instances)
    assert not instances.should_register_instance(None)


def test_the_new_reason_codes_are_shared_values():
    validator = _def(SUBMIT_SCHEMA, "reason")
    for code in ("version-conflict", "unknown-well-known-kind", "definition-id-mismatch",
                 "role-held", "instance-required", "no-command-destination",
                 "projected-read-only", "definition-referenced", "unknown-provenance"):
        assert not _errors(validator, {"code": code}), code
