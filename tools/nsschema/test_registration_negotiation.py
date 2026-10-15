"""Registration negotiation: the D18 addendum, rule 6 (queue items SPEC-REG-NEGOTIATE
and SPEC-REG-DECISIONS).

Execution plan §2.6.1; contract in the hub-sync design §3.5, with the
maintainer's decisions of 2026-10-14 applied (SPEC-REG-DECISIONS). Every
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
    # SPEC-REG-DECISIONS
    "accepted-first-to-claim", "rejected-namespace-claimed-first-to-claim",
    "update-token-rotated", "update-not-registration-owner",
    "update-api-secret-bound", "update-api-secret-not-owner",
    "retire-not-registration-owner", "retire-roots-not-required", "retire-not-authorised",
    "accepted-api-secret-single", "owner-retire", "owner-action-on-data-listener",
    "owner-block", "owner-block-api-secret-single", "blocked-update-stale-etag",
    "blocked-by-owner", "owner-block-pre-emptive", "blocked-pre-emptive-create",
    "owner-unblock", "owner-unblock-retired", "owner-release", "released-update-binds",
    "owner-transfer", "owner-free-namespaces", "owner-free-namespaces-not-retired",
    "namespace-claimed-after-free", "rejected-namespace-claimed-retired",
    "accepted-dual-write-view-not-served", "accepted-dual-write-view-served",
    "typed-write-load-503", "typed-write-load-429-retry-after",
    "typed-write-blocked-by-owner", "typed-write-route-404",
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
        if stored["registration"] is None:
            assert stored["state"] == "blocked"  # a pre-emptive block
            continue
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
        summary = response["registration"]
        if response["outcome"] in ("accepted", "partial") and not response.get("noop"):
            assert summary["etag"] == negotiate.etag(case["registration"], summary["state"])
        if case["expected"].get("storedAfter"):
            assert summary["etag"] == case["expected"]["storedAfter"]["etag"]
        assert {"vendor": summary["vendor"], "product": summary["product"]} == \
            case["request"]["identity"]


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
    assert response["outcome"] in ("accepted", "retired", "applied"), case["control"]
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
    accepted = {e["element"]: e for e in response.get("elements") or []
                if e["result"] in negotiate.ACCEPTED}
    if response.get("outcome") not in ("accepted", "partial"):
        accepted = {}
    elements = {e[0]: e for e in negotiate.elements(case["registration"])}
    assert set(plan) == set(elements)
    for eid, entry in plan.items():
        node = elements[eid][3]
        if eid in accepted:
            # Decision 7: typed only, or typed and carrier when the hub serves
            # no carrier view and the element declares a dual-write link.
            linked = node.get("dualWriteLink") and \
                accepted[eid].get("carrierView", "not-served") == "not-served"
            assert entry == ({"write": "typed-and-carrier", "carrier": node.get("wire") or
                              node.get("carrier"), "link": node["dualWriteLink"]}
                             if linked else {"write": "typed"})
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


# ── SPEC-REG-DECISIONS (maintainer's decisions, 2026-10-14) ───────────

def _run(cid, **changes):
    """Negotiate a case's request with some inputs changed."""
    case = copy.deepcopy(CASES[cid])
    for key, value in changes.items():
        if key == "request":
            case["request"].update(value)
        else:
            case[key] = value
    return negotiate.negotiate(case["capabilities"], case["hubState"], case["submitter"],
                               case["registration"], case["request"], GRAMMAR)


def _codes(response):
    return [r["code"] for r in response.get("reasons") or []]


def test_namespaces_are_first_to_claim_unless_roots_are_stated():
    # Decision 1. No stated roots: any namespace no other registration holds.
    submitter = copy.deepcopy(CASES["accepted-first-to-claim"]["submitter"])
    assert "namespaceRoots" not in submitter
    response, _ = _run("accepted-first-to-claim")
    assert response["outcome"] == "accepted"
    # Stated roots restrict, and an empty list is a stated restriction.
    submitter["namespaceRoots"] = []
    response, _ = _run("accepted-first-to-claim", submitter=submitter)
    assert response["outcome"] == "partial"
    assert response["elements"][1]["reasons"][0]["code"] == "namespace-not-owned"
    # Control: a covering root.
    submitter["namespaceRoots"] = ["com.example.negotiation"]
    response, _ = _run("accepted-first-to-claim", submitter=submitter)
    assert response["outcome"] == "accepted"


def test_the_binding_is_checked_before_the_preconditions():
    # Decision 4: step (1). Another subject with no precondition is 403, not 428.
    response, stored = _run("update-not-registration-owner", request={"preconditions": {}})
    assert (response["status"], _codes(response)) == (403, ["not-registration-owner"])
    assert stored == CASES["update-not-registration-owner"]["hubState"]["registrations"][0]
    # Control: the bound subject with no precondition reaches step (2).
    response, _ = _run("update-token-rotated", request={"preconditions": {}})
    assert (response["status"], _codes(response)) == (428, ["precondition-required"])


def test_the_binding_is_the_subject_not_the_token():
    case = CASES["update-token-rotated"]
    bound = case["hubState"]["registrations"][0]["boundTo"]
    assert bound == {"kind": "subject", "subject": case["submitter"]["subject"]}
    assert "token" in case["submitter"] and case["submitter"]["token"] not in json.dumps(bound)
    assert negotiate.binding_of(case["submitter"]) == bound


def test_a_released_registration_binds_its_next_writer():
    after = CASES["released-update-binds"]["expected"]["storedAfter"]
    assert after["boundTo"] == {"kind": "subject", "subject": "subject-test-controller-b"}
    # The subject it was bound to before the release is now refused.
    hub = {"registrations": [after]}
    first = copy.deepcopy(CASES["update-token-rotated"]["submitter"])
    request = dict(CASES["released-update-binds"]["request"],
                   preconditions={"ifMatch": after["etag"]})
    response, _ = negotiate.negotiate(CASES["accepted"]["capabilities"], hub, first,
                                      CASES["released-update-binds"]["registration"], request,
                                      GRAMMAR)
    assert _codes(response) == ["not-registration-owner"]
    # Control: the new owner's identical resubmission is a no-op.
    response, _ = negotiate.negotiate(CASES["accepted"]["capabilities"], hub,
                                      CASES["released-update-binds"]["submitter"],
                                      CASES["released-update-binds"]["registration"], request,
                                      GRAMMAR)
    assert (response["status"], response["noop"]) == (200, True)


def test_binding_and_credential_kind_are_outside_the_etag():
    # Decisions 3 and 4: the etag's input stays {registration, state}.
    for cid in ("owner-release", "owner-transfer", "owner-free-namespaces"):
        before = CASES[cid]["hubState"]["registrations"][0]
        after = CASES[cid]["expected"]["storedAfter"]
        assert after["etag"] == before["etag"], cid
        assert after != before, cid
    secret = CASES["accepted-api-secret-single"]["expected"]
    assert secret["storedAfter"]["credentialKind"] == "api-secret"
    assert secret["response"]["registration"]["credentialKind"] == "api-secret"
    assert secret["storedAfter"]["etag"] == CASES["accepted"]["expected"]["storedAfter"]["etag"]


def test_a_block_changes_the_etag_and_unblocking_restores_it():
    before = CASES["owner-block"]["hubState"]["registrations"][0]
    blocked = CASES["owner-block"]["expected"]["storedAfter"]
    assert (blocked["state"], blocked["blockedFrom"]) == ("blocked", "active")
    assert blocked["etag"] != before["etag"]
    assert blocked["registration"] == before["registration"]
    assert blocked["boundTo"] == before["boundTo"]
    assert CASES["owner-unblock"]["expected"]["storedAfter"]["etag"] == before["etag"]
    retired = CASES["owner-unblock-retired"]["expected"]["storedAfter"]
    assert retired["state"] == "retired"


def test_the_owner_never_edits_content():
    # Decision 5. The owner's submit is refused, even holding every
    # permission, so the refusal is the owner rule and not a missing grant.
    # Control: the owner's retire.
    owner = dict(CASES["owner-retire"]["submitter"], permissions=["*"])
    response, _ = _run("owner-retire", registration=CASES["update-accepted"]["registration"],
                       submitter=owner, request={"action": "submit"})
    assert (response["status"], _codes(response)) == (403, ["not-authorised"])
    response, _ = _run("owner-retire")
    assert response["outcome"] == "retired"


def test_api_secret_acts_as_the_owner_only_on_the_single_listener():
    # Decision 3 and 5. A subject on `single` is not the owner; nor is the
    # secret on ns-api. Control: owner-block-api-secret-single.
    subject = CASES["update-token-rotated"]["submitter"]
    response, _ = _run("owner-block-api-secret-single", submitter=subject)
    assert (response["status"], _codes(response)) == (403, ["not-authorised"])
    response, _ = _run("owner-block-api-secret-single", request={"listener": "ns-api"})
    assert (response["status"], _codes(response)) == (403, ["not-authorised"])
    response, _ = _run("owner-block-api-secret-single")
    assert response["outcome"] == "applied"


def test_the_owner_retires_a_blocked_registration_only_after_unblocking():
    blocked = CASES["owner-unblock"]["hubState"]["registrations"][0]
    response, stored = _run("owner-retire", hubState={"registrations": [blocked]},
                            request={"preconditions": {"ifMatch": blocked["etag"]}})
    assert (response["status"], _codes(response)) == (409, ["blocked-by-owner"])
    assert stored == blocked
    # Control: the same owner retire on the active registration.
    response, _ = _run("owner-retire")
    assert (response["status"], response["outcome"]) == (200, "retired")


def test_unblocking_a_pre_emptive_block_removes_it():
    placeholder = CASES["owner-block-pre-emptive"]["expected"]["storedAfter"]
    assert placeholder["registration"] is None
    response, stored = _run("owner-unblock", hubState={"registrations": [placeholder]},
                            request={"preconditions": {"ifMatch": placeholder["etag"]}})
    assert (response["status"], response["outcome"], stored) == (200, "applied", None)
    assert "registration" not in response
    # Control: nothing to release on a pre-emptive block.
    response, _ = _run("owner-release", hubState={"registrations": [placeholder]},
                       request={"preconditions": {"ifMatch": placeholder["etag"]}})
    assert response["status"] == 404


def test_a_reactivated_registration_reclaims_a_freed_namespace_only_if_unheld():
    # Decision 5, the rule this item chose: a freed namespace stays freed
    # while another registration holds it; otherwise reactivation reclaims it.
    retired = copy.deepcopy(CASES["retire"]["expected"]["storedAfter"])
    retired = negotiate._restate(retired, freedNamespaces=["com.example.negotiation.targets"])
    case = CASES["update-token-rotated"]
    request = dict(case["request"], preconditions={"ifMatch": retired["etag"]})
    response, after = negotiate.negotiate(case["capabilities"], {"registrations": [retired]},
                                          case["submitter"], retired["registration"], request,
                                          GRAMMAR)
    assert response["outcome"] == "accepted"
    assert "freedNamespaces" not in after
    holder = CASES["namespace-claimed-after-free"]["expected"]["storedAfter"]
    holder = negotiate._stored(("Example", "OtherController"),
                               CASES["rejected-namespace-claimed"]["hubState"]["registrations"]
                               [0]["registration"], "active",
                               boundTo={"kind": "subject", "subject": "subject-test-controller-b"},
                               credentialKind="subject")
    response, after = negotiate.negotiate(case["capabilities"],
                                          {"registrations": [retired, holder]},
                                          case["submitter"], retired["registration"], request,
                                          GRAMMAR)
    assert response["outcome"] == "partial"
    assert after["freedNamespaces"] == ["com.example.negotiation.targets"]


def test_a_carrier_view_the_controller_does_not_know_is_not_accepted():
    reg = CASES["accepted-dual-write-view-served"]["registration"]
    response = copy.deepcopy(CASES["accepted-dual-write-view-served"]["expected"]["response"])
    span = response["elements"][0]
    assert span["carrierView"] == "served"
    assert negotiate.fallback(reg, response)[span["element"]] == {"write": "typed"}
    span["carrierView"] = {"value": "other", "term": "projected-later"}
    assert negotiate.fallback(reg, response)[span["element"]]["write"] == "carrier"
    span["carrierView"] = "served-sometimes"
    assert negotiate.fallback(reg, response)[span["element"]]["write"] == "carrier"


def test_a_link_without_a_carrier_writes_typed_only():
    reg = copy.deepcopy(CASES["accepted-dual-write-view-not-served"]["registration"])
    response = CASES["accepted-dual-write-view-not-served"]["expected"]["response"]
    span = "stateSpans/ExampleOverride"
    assert negotiate.fallback(reg, response)[span]["write"] == "typed-and-carrier"
    reg["spec"]["stateSpans"][0]["wire"] = None
    assert negotiate.fallback(reg, response)[span] == {"write": "typed"}


def test_the_strict_view_knows_the_dual_write_link():
    reg = CASES["accepted-dual-write-view-not-served"]["registration"]
    assert sync_model.unknown_grammar_fields(reg, GRAMMAR) == []
    misspelt = copy.deepcopy(reg)
    misspelt["spec"]["stateSpans"][0]["dualWriteLnk"] = \
        misspelt["spec"]["stateSpans"][0].pop("dualWriteLink")
    assert sync_model.unknown_grammar_fields(misspelt, GRAMMAR) == [
        "spec.stateSpans.0.dualWriteLnk"]


def test_a_dual_write_link_names_both_ids():
    validator = jsonschema.Draft202012Validator(GRAMMAR)
    reg = copy.deepcopy(CASES["accepted-dual-write-view-not-served"]["registration"])
    assert not _errors(validator, reg)
    del reg["spec"]["stateSpans"][0]["dualWriteLink"]["carrierIdPath"]
    assert _errors(validator, reg)


TYPED_WRITE = [i for i in IDS if "typedWrite" in CASES[i]]


@pytest.mark.parametrize("cid", TYPED_WRITE)
def test_a_refused_typed_write_is_retried_for_load_and_carried_when_definite(cid):
    # Decision 8.
    case = CASES[cid]
    refusal, outcome = case["typedWrite"], case["expected"]["typedWrite"]
    before = case["expected"]["fallback"]
    assert before[refusal["element"]]["write"] == "typed"
    assert outcome["recheck"] is False
    others = {k: v for k, v in outcome["fallback"].items() if k != refusal["element"]}
    assert others == {k: v for k, v in before.items() if k != refusal["element"]}
    if refusal["status"] in (429, 503):
        assert outcome["action"] == "retry-backoff"
        assert outcome["fallback"] == before
    else:
        assert outcome["action"] == "carrier-this-record"
        assert outcome["fallback"][refusal["element"]]["write"] == "carrier"
        control = CASES[case["control"]]
        assert control["expected"]["typedWrite"]["action"] == "retry-backoff"
        assert {k: v for k, v in case.items() if k not in ("id", "title", "description",
                                                            "control", "typedWrite", "expected")} \
            == {k: v for k, v in control.items() if k not in ("id", "title", "description",
                                                               "control", "typedWrite",
                                                               "expected")}


def test_both_kinds_of_typed_write_refusal_are_covered():
    statuses = {CASES[c]["typedWrite"]["status"] for c in TYPED_WRITE}
    assert {429, 503} <= statuses and statuses - {429, 503}
    assert any("retryAfter" in CASES[c]["typedWrite"] for c in TYPED_WRITE)
    assert any("retryAfter" not in CASES[c]["typedWrite"] and
               CASES[c]["typedWrite"]["status"] in (429, 503) for c in TYPED_WRITE)


def test_a_typed_write_refused_with_an_unknown_status_is_definite():
    reg = CASES["typed-write-load-503"]["registration"]
    plan = CASES["typed-write-load-503"]["expected"]["fallback"]
    element = "extensions/com.example.negotiation.targets"
    assert negotiate.typed_write_refused(reg, plan, {"element": element, "status": 500})[
        "action"] == "carrier-this-record"
    assert negotiate.typed_write_refused(reg, plan, {"element": element, "status": 503})[
        "action"] == "retry-backoff"


def test_a_submit_answered_429_or_503_is_no_response():
    # Decision 8 keeps the existing rule: a submit refused for load is "no
    # response", so every element is written as its carrier.
    reg = CASES["accepted"]["registration"]
    for response in (None, {"status": 503}, {"status": 429}):
        assert all(e["write"] != "typed" for e in negotiate.fallback(reg, response).values())
    assert all(e["write"] == "typed" for e in
               negotiate.fallback(reg, CASES["accepted"]["expected"]["response"]).values())


# ── schemas for the decisions ─────────────────────────────────────────

def test_a_credential_kind_outside_the_shared_list_is_other_plus_a_term():
    validator = _submit_def("credentialKind")
    for good in ("subject", "api-secret", {"value": "other", "term": "client-certificate"}):
        assert not _errors(validator, good), good
    for bad in ("client-certificate", {"value": "other"}):
        assert _errors(validator, bad), bad


def test_a_binding_names_a_subject_exactly_when_it_is_one():
    validator = _submit_def("binding")
    assert not _errors(validator, {"kind": "subject", "subject": "subject-test-x"})
    assert not _errors(validator, {"kind": "api-secret"})
    assert _errors(validator, {"kind": "subject"})
    assert _errors(validator, {"kind": "api-secret", "subject": "subject-test-x"})


def test_a_carrier_view_outside_the_shared_list_is_other_plus_a_term():
    validator = _submit_def("elementResult")
    base = {"element": "stateSpans/X", "result": "accepted"}
    for good in ("served", "not-served", {"value": "other", "term": "partial-view"}):
        assert not _errors(validator, dict(base, carrierView=good)), good
    assert _errors(validator, dict(base, carrierView="partial-view"))


def test_the_new_reason_codes_are_shared_values():
    validator = _submit_def("reason")
    for code in ("not-registration-owner", "blocked-by-owner", "not-retired"):
        assert not _errors(validator, {"code": code}), code


def test_a_stored_registration_is_null_only_when_blocked():
    validator = _submit_def("storedRegistration")
    placeholder = CASES["owner-block-pre-emptive"]["expected"]["storedAfter"]
    assert not _errors(validator, placeholder)
    assert _errors(validator, dict(placeholder, state="active"))
    assert _errors(validator, dict(placeholder, boundTo=None))
    blocked = CASES["owner-block"]["expected"]["storedAfter"]
    assert not _errors(validator, blocked)
    assert _errors(validator, {k: v for k, v in blocked.items() if k != "blockedFrom"})
    active = CASES["accepted"]["expected"]["storedAfter"]
    assert _errors(validator, {k: v for k, v in active.items() if k != "boundTo"})


def test_owner_actions_name_the_owner_and_the_listener():
    validator = _submit_def("request")
    request = copy.deepcopy(CASES["owner-transfer"]["request"])
    assert not _errors(validator, request)
    for key in ("actor", "listener", "transferTo"):
        assert _errors(validator, {k: v for k, v in request.items() if k != key}), key
    assert _errors(validator, dict(request, actor="controller"))


def test_a_dual_write_plan_entry_carries_its_carrier_and_link():
    validator = _submit_def("fallbackEntry")
    entry = CASES["accepted-dual-write-view-not-served"]["expected"]["fallback"][
        "stateSpans/ExampleOverride"]
    assert entry["write"] == "typed-and-carrier"
    assert not _errors(validator, entry)
    assert _errors(validator, {k: v for k, v in entry.items() if k != "link"})


def test_a_typed_write_outcome_never_rechecks():
    validator = _submit_def("conformanceCase")
    case = copy.deepcopy(CASES["typed-write-blocked-by-owner"])
    assert not _errors(validator, case)
    case["expected"]["typedWrite"]["recheck"] = True
    assert _errors(validator, case)
