"""Registration negotiation: the D18 addendum, rule 6 (queue item SPEC-REG-NEGOTIATE).

Execution plan §2.6.1; contract in the hub-sync design §3.5. Every
conformance case under specs/sync/conformance/ validates against the schemas,
and the reference decision function (tools/nsschema/negotiate.py, a reference
and not a hub) reproduces its expected response and controller fallback.
Each rejection case names a passing control, and each schema rejection test
here is paired with a control that validates.
"""

import copy
import json

import jsonschema
import pytest
import yaml

from nsschema import corpus, negotiate, sync_model

ROOT = corpus.repo_root()
GRAMMAR = json.loads((ROOT / negotiate.GRAMMAR_SCHEMA).read_text())
CAPS_SCHEMA = json.loads((ROOT / negotiate.CAPABILITIES_SCHEMA).read_text())
SUBMIT_SCHEMA = json.loads((ROOT / negotiate.SUBMIT_SCHEMA).read_text())
CASE_PATHS = sorted((ROOT / negotiate.CONFORMANCE_DIR).glob("*.yaml"))
CASES = {p.stem: yaml.safe_load(p.read_text()) for p in CASE_PATHS}
IDS = sorted(CASES)

# The cases the queue item requires, by id.
REQUIRED = {
    "accepted", "accepted-with-ignored-members", "rejected-untyped-extension",
    "rejected-unsupported-grammar-major", "rejected-type-keyword-outside-subset",
    "rejected-namespace-not-owned", "older-hub-no-capabilities",
    "newer-hub-older-controller", "update-stale-etag", "retire",
}
CELLS = {"older-controller/older-hub", "older-controller/newer-hub",
         "newer-controller/older-hub", "newer-controller/newer-hub"}


def _submit_def(name):
    return jsonschema.Draft202012Validator(
        {"$ref": f"#/$defs/{name}", "$defs": SUBMIT_SCHEMA["$defs"]})


def _errors(validator, doc):
    return list(validator.iter_errors(doc))


def _strip_detail(value):
    if isinstance(value, dict):
        return {k: _strip_detail(v) for k, v in value.items() if k != "detail"}
    if isinstance(value, list):
        return [_strip_detail(v) for v in value]
    return value


def _rejects(response):
    if response is None:
        return False
    if response["outcome"] in ("rejected", "precondition-failed", "not-found"):
        return True
    return any(e["result"] == "rejected" for e in response.get("elements") or [])


@pytest.mark.parametrize("schema", [CAPS_SCHEMA, SUBMIT_SCHEMA], ids=["capabilities", "submit"])
def test_schemas_are_valid_2020_12_schemas(schema):
    jsonschema.Draft202012Validator.check_schema(schema)


def test_the_capability_vocabularies_match_the_grammar():
    # The capability document restates the grammar's closed lists rather
    # than referencing them across files; drift between the two would let a
    # hub advertise something no registration can declare.
    defs = GRAMMAR["$defs"]
    props = CAPS_SCHEMA["properties"]
    assert props["horizons"]["properties"]["classes"]["items"]["enum"] == \
        defs["horizon"]["properties"]["class"]["enum"]
    assert props["horizons"]["properties"]["availability"]["items"]["enum"] == \
        defs["availability"]["enum"]
    assert set(props["typeFragment"]["properties"]["keywords"]["items"]["enum"]) == \
        set(defs["typeFragment"]["properties"])
    assert props["typeFragment"]["properties"]["formats"]["items"]["enum"] == \
        defs["typeFragment"]["properties"]["format"]["enum"]
    assert SUBMIT_SCHEMA["$defs"]["response"]["properties"]["apiVersion"]["const"] == \
        GRAMMAR["properties"]["apiVersion"]["const"]


# ── the case set ──────────────────────────────────────────────────────

def test_the_required_cases_and_all_four_cells_exist():
    assert REQUIRED <= set(IDS), REQUIRED - set(IDS)
    assert {c.get("cell") for c in CASES.values()} == CELLS


@pytest.mark.parametrize("cid", IDS)
def test_case_validates_against_the_case_schema(cid):
    case = CASES[cid]
    assert _errors(_submit_def("conformanceCase"), case) == []
    assert case["id"] == cid


@pytest.mark.parametrize("cid", IDS)
def test_case_capabilities_are_a_valid_capability_document(cid):
    caps = CASES[cid]["capabilities"]
    if caps is None:
        return
    assert _errors(jsonschema.Draft202012Validator(CAPS_SCHEMA), caps) == []
    assert negotiate.capability_problems(caps) == []


@pytest.mark.parametrize("cid", IDS)
def test_case_registrations_validate_as_stated(cid):
    case = CASES[cid]
    grammar = jsonschema.Draft202012Validator(GRAMMAR)
    if case["registration"] is not None:
        assert (not _errors(grammar, case["registration"])) is case["grammarValid"]
    for stored in case.get("hubState", {}).get("registrations", []):
        assert not _errors(grammar, stored["registration"])
    for reg in (case.get("wellKnownRegistrations") or {}).values():
        assert not _errors(grammar, reg)
        assert reg["metadata"]["tier"] == "well-known"


@pytest.mark.parametrize("cid", IDS)
def test_case_etags_follow_the_derivation(cid):
    case = CASES[cid]
    stored = list(case.get("hubState", {}).get("registrations", []))
    if case["expected"].get("storedAfter"):
        stored.append(case["expected"]["storedAfter"])
    for entry in stored:
        assert entry["etag"] == negotiate.etag(entry["registration"], entry["state"])
    response = case["expected"]["response"]
    if response and "registration" in response:
        meta = (case["registration"] or {}).get("metadata", {})
        summary = response["registration"]
        if response["outcome"] != "retired" and not response.get("noop"):
            assert summary["etag"] == negotiate.etag(case["registration"], summary["state"])
        assert (summary["vendor"], summary["product"]) == (meta["vendor"], meta["product"])


@pytest.mark.parametrize("cid", IDS)
def test_the_reference_reproduces_the_expected_outcome(cid):
    case = CASES[cid]
    computed = negotiate.run_case(copy.deepcopy(case), GRAMMAR)
    assert _strip_detail(computed) == case["expected"]


@pytest.mark.parametrize("cid", IDS)
def test_the_reference_does_not_mutate_its_inputs(cid):
    case = CASES[cid]
    before = copy.deepcopy(case)
    negotiate.run_case(case, GRAMMAR)
    assert case == before


@pytest.mark.parametrize("cid", [i for i in IDS if _rejects(CASES[i]["expected"]["response"])])
def test_every_rejection_has_a_passing_control(cid):
    case = CASES[cid]
    control = CASES[case["control"]]
    response = control["expected"]["response"]
    assert response["outcome"] in ("accepted", "retired"), case["control"]
    assert not _rejects(response)
    # The control differs from the case in at least one input.
    inputs = ("capabilities", "hubState", "submitter", "registration", "request")
    assert any(case.get(k) != control.get(k) for k in inputs)
    # An element rejected here is accepted in the control.
    accepted = {e["element"] for e in response.get("elements") or []}
    for element in case["expected"]["response"].get("elements") or []:
        if element["result"] == "rejected":
            assert element["element"] in accepted


@pytest.mark.parametrize("cid", IDS)
def test_the_fallback_writes_typed_only_what_was_accepted(cid):
    case = CASES[cid]
    plan = case["expected"]["fallback"]
    if plan is None:
        assert case["registration"] is None
        return
    response = case["expected"]["response"] or {}
    accepted = {e["element"] for e in response.get("elements") or []
                if e["result"] in negotiate.ACCEPTED}
    if response.get("outcome") not in ("accepted", "partial"):
        accepted = set()
    elements = {e[0]: e for e in negotiate.elements(case["registration"])}
    assert set(plan) == set(elements)
    for eid, entry in plan.items():
        node = elements[eid][3]
        if eid in accepted:
            assert entry == {"write": "typed"}
        elif eid.startswith("stateSpans/"):
            assert entry == ({"write": "carrier", "carrier": node["wire"]}
                             if node.get("wire") else {"write": "none"})
        elif eid.startswith("extensions/"):
            assert entry == ({"write": "carrier", "carrier": node["carrier"]}
                             if node.get("carrier") else {"write": "none"})


def test_the_older_hub_cases_send_nothing():
    for cid, case in CASES.items():
        if case.get("cell") in ("newer-controller/older-hub", "older-controller/older-hub") \
                and case["request"] is None:
            assert case["expected"]["controllerWouldSubmit"] is False
            assert case["expected"]["response"] is None


# ── the capability document ───────────────────────────────────────────

def _caps():
    return copy.deepcopy(CASES["accepted"]["capabilities"])


def test_a_capability_document_must_interpret_what_the_contract_reads():
    caps = _caps()
    caps["grammar"]["interprets"] = ["apiVersion", "kind", "metadata.vendor",
                                     "metadata.product", "spec"]
    assert negotiate.capability_problems(caps) == [
        "required member not interpreted: metadata.tier"]
    caps["grammar"]["interprets"].append("metadata.tier")
    assert negotiate.capability_problems(caps) == []


def test_a_capability_document_must_offer_the_type_keyword():
    caps = _caps()
    validator = jsonschema.Draft202012Validator(CAPS_SCHEMA)
    caps["typeFragment"]["keywords"] = ["enum", "minimum"]
    assert _errors(validator, caps)
    caps["typeFragment"]["keywords"] = ["type", "pattern"]
    assert _errors(validator, caps)
    caps["typeFragment"]["keywords"] = ["type", "enum"]
    assert not _errors(validator, caps)


def test_a_capability_document_is_must_ignore_but_its_vocabularies_are_closed():
    caps = _caps()
    validator = jsonschema.Draft202012Validator(CAPS_SCHEMA)
    caps["futureCapability"] = {"anything": True}
    caps["grammar"]["futureGrammarMember"] = 1
    assert not _errors(validator, caps)
    caps["horizons"]["classes"].append("rolling")
    assert _errors(validator, caps)


def test_a_controller_submits_only_when_the_hub_can_take_it():
    reg = CASES["accepted"]["registration"]
    caps = _caps()
    assert negotiate.should_submit(caps, reg)
    assert not negotiate.should_submit(None, reg)
    assert not negotiate.should_submit(caps, None)
    no_submit = _caps()
    del no_submit["submit"]
    assert not negotiate.should_submit(no_submit, reg)
    v2 = copy.deepcopy(reg)
    v2["apiVersion"] = "nightscout.dev/sync/v2"
    assert not negotiate.should_submit(caps, v2)


# ── the submit contract ───────────────────────────────────────────────

def test_a_rejected_element_must_say_why():
    validator = _submit_def("elementResult")
    assert _errors(validator, {"element": "extensions/com.example.a", "result": "rejected"})
    assert _errors(validator, {"element": "extensions/com.example.a", "result": "rejected",
                               "reasons": []})
    assert _errors(validator, {"element": "extensions/com.example.a",
                               "result": "accepted-with-ignored-members"})
    assert not _errors(validator, {"element": "extensions/com.example.a", "result": "rejected",
                                   "reasons": [{"code": "untyped-extension"}]})


def test_a_reason_outside_the_shared_list_is_other_plus_a_term():
    validator = _submit_def("reason")
    assert _errors(validator, {"code": "brand-new-reason"})
    assert _errors(validator, {"code": "other"})
    assert not _errors(validator, {"code": "other", "term": "brand-new-reason"})


def test_a_failed_request_carries_no_element_results():
    validator = _submit_def("response")
    response = copy.deepcopy(CASES["update-stale-etag"]["expected"]["response"])
    assert not _errors(validator, response)
    response["elements"] = [{"element": "stateSpans/X", "result": "accepted"}]
    assert _errors(validator, response)
    response = copy.deepcopy(CASES["update-stale-etag"]["expected"]["response"])
    response["status"] = 200
    assert _errors(validator, response)


def test_an_etag_is_a_sha256_digest_that_changes_with_state():
    reg = CASES["accepted"]["registration"]
    active, retired = negotiate.etag(reg, "active"), negotiate.etag(reg, "retired")
    assert active != retired
    assert not _errors(_submit_def("etag"), active)
    assert _errors(_submit_def("etag"), "W/\"1\"")
    # Key order does not change the etag.
    reordered = json.loads(json.dumps(reg, sort_keys=True))
    assert negotiate.etag(reordered, "active") == active


def test_a_request_without_a_precondition_is_refused():
    case = copy.deepcopy(CASES["accepted"])
    case["request"]["preconditions"] = {}
    response, stored = negotiate.negotiate(case["capabilities"], case["hubState"],
                                           case["submitter"], case["registration"],
                                           case["request"], GRAMMAR)
    assert (response["status"], response["reasons"][0]["code"]) == (428, "precondition-required")
    assert stored is None


def test_permissions_follow_shiro_implication():
    want = "api:registrations:create"
    for grant in ("*", "api", "api:*", "api:registrations", "api:registrations:*", want):
        assert negotiate.permitted([grant], want), grant
    for grant in ("api:treatments:create", "api:registrations:delete",
                  "api:registrations:create:extra", "admin"):
        assert not negotiate.permitted([grant], want), grant
    assert negotiate.permitted(["api:registrations:create:*"], want)


def test_a_namespace_root_covers_itself_and_what_is_below_it():
    ns = "com.example.negotiation.targets"
    for root in ("com.example", "com.example.negotiation", ns, "*"):
        assert negotiate._owns([root], ns), root
    for root in ("com.examplefoo", "com.example.negotiation.targets.sub", "org.example", ""):
        assert not negotiate._owns([root], ns), root


def test_a_retired_registration_keeps_its_declaration():
    case = CASES["retire"]
    after = case["expected"]["storedAfter"]
    assert after["state"] == "retired"
    assert after["registration"] == case["hubState"]["registrations"][0]["registration"]


def test_ignored_members_reuse_unknown_grammar_fields():
    # With a hub that interprets everything, what is ignored is exactly what
    # sync_model.unknown_grammar_fields reports.
    reg = CASES["accepted-with-ignored-members"]["registration"]
    caps = _caps()
    assert negotiate.ignored_members(caps, reg, GRAMMAR) == \
        sync_model.unknown_grammar_fields(reg, GRAMMAR)
    # Control: the synthetic grammar fixture's unknown members are found too.
    fixture = yaml.safe_load((ROOT / sync_model.FIXTURES_DIR /
                              "example-testcontroller.yaml").read_text())
    assert negotiate.ignored_members(caps, fixture, GRAMMAR) == [
        "spec.futureGrammarMember", "spec.stateSpans.0.futureSpanMember"]


def test_the_grammar_fixture_negotiates_against_a_full_hub():
    # The SCHEMA-REG-EXT test registration uses every rule; against a hub that
    # supports everything, every element is accepted.
    fixture = yaml.safe_load((ROOT / sync_model.FIXTURES_DIR /
                              "example-testcontroller.yaml").read_text())
    meta = fixture["metadata"]
    request = {"action": "submit", "identity": {"vendor": meta["vendor"],
                                                "product": meta["product"]},
               "preconditions": {"ifNoneMatch": "*"}}
    submitter = {"permissions": ["api:registrations:create"],
                 "namespaceRoots": ["com.example.testcontroller"]}
    response, _ = negotiate.negotiate(_caps(), {"registrations": []}, submitter, fixture,
                                      request, GRAMMAR)
    assert response["outcome"] == "accepted"
    assert {e["result"] for e in response["elements"]} <= set(negotiate.ACCEPTED)
    assert len(response["elements"]) == 6
    # Control: without the namespace root, the extension is rejected.
    submitter["namespaceRoots"] = []
    response, _ = negotiate.negotiate(_caps(), {"registrations": []}, submitter, fixture,
                                      request, GRAMMAR)
    assert response["outcome"] == "partial"


def test_only_an_accepted_or_partial_outcome_yields_typed_writes():
    # A retired registration's response may still list element results; the
    # controller writes its carriers all the same.
    reg = CASES["retire"]["registration"]
    response = copy.deepcopy(CASES["retire"]["expected"]["response"])
    response["elements"] = [{"element": e[0], "result": "accepted"}
                            for e in negotiate.elements(reg)]
    assert all(entry["write"] != "typed"
               for entry in negotiate.fallback(reg, response).values())
    # Control: the same element results under `accepted` are written typed.
    response["outcome"] = "accepted"
    assert all(entry["write"] == "typed"
               for entry in negotiate.fallback(reg, response).values())
    # An element result the controller does not know is not accepted.
    first = response["elements"][0]
    first["result"] = "accepted-later"
    assert negotiate.fallback(reg, response)[first["element"]]["write"] != "typed"
