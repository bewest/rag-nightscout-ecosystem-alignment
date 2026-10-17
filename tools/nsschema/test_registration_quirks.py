"""Version-scoped quirks, the shared slot list and the two-id rule: D20 (queue item SPEC-REG-QUIRKS).

Execution plan §2.6.3; contract in the hub-sync design §3.7. Every conformance
case under specs/sync/conformance/quirks/ validates against the schemas, and
the reference (tools/nsschema/instances.py with quirks_registration.py; a
reference and not a hub) reproduces its expected outcome. The registry half
(rules 1 and 4) is tools/nsschema/quirks.py, tested here on synthetic
documents. Each refusal names a passing control.

Amended 2026-10-16 (SPEC-REG-AMEND; the maintainer's walk-through, execution
plan §2.6.3, rows 1-9): every hub serves 24-hex `_id` values on its legacy
surface (the `legacyIdForm` member, its `opaque` option and their two cases
are removed); a slot is shared only through the shared slot list or
`sameAs`, and the owner's listing records equal unlisted names; Trio's `id`
member is QUIRK-TREATMENTS-007. Each changed test says so.
"""

import copy
import datetime
import json
import re

import jsonschema
import pytest
import yaml

from nsschema import corpus, instances, negotiate, quirks, quirks_registration, sync_model

ROOT = corpus.repo_root()
GRAMMAR = json.loads((ROOT / negotiate.GRAMMAR_SCHEMA).read_text())
CAPS_SCHEMA = json.loads((ROOT / negotiate.CAPABILITIES_SCHEMA).read_text())
SUBMIT_SCHEMA = json.loads((ROOT / negotiate.SUBMIT_SCHEMA).read_text())
QUIRK_SCHEMA = json.loads((ROOT / quirks.SCHEMA).read_text())
CASES_DIR = ROOT / "specs/sync/conformance/quirks"
CASE_PATHS = sorted(CASES_DIR.glob("*.yaml"))
CASES = {p.stem: yaml.safe_load(p.read_text()) for p in CASE_PATHS}
IDS = sorted(CASES)
REGISTRY = quirks.load_registry(ROOT / "specs/quirks")
BY_ID = {q["id"]: q for q in REGISTRY}
SHARED = yaml.safe_load((ROOT / "specs/sync/shared-slots.yaml").read_text())

REQUIRED = {
    # rule 2: sameAs, the shared list, names that look alike, catalogue mappings
    "same-as-definition-accepted", "same-as-unknown-shared-slot", "same-as-no-shared-list",
    "same-as-own-shared-name", "same-as-without-slot", "same-as-role-granted",
    "same-as-role-held", "names-alike-do-not-contend", "same-as-own-name-not-a-channel",
    "same-as-unlisted-not-own-name",
    # row 5 (2026-10-16): equal unlisted names do not contend; the observation
    "equal-names-unlisted-do-not-contend", "slot-name-observation-recorded",
    "catalogue-mapping-applied", "catalogue-mapping-version-outside",
    "catalogue-mapping-version-unknown",
    # rule 3: mappings are recorded
    "same-as-typed-write-declared", "carrier-uuid-id-moved",
    # rules 5 and 6: two ids, identifier first
    "carrier-write-both-ids", "carrier-resend-matches-identifier",
    "carrier-resend-identifier-first", "carrier-resend-matches-objectid", "carrier-hex-id-kept",
    # rule 7: today's handling, unchanged
    "carrier-uuid-id-dropped", "carrier-uuid-entries-moved", "carrier-uuid-resend-matches",
    # rule 8: projected and typed records. REMOVED 2026-10-16 (SPEC-REG-AMEND,
    # row 2): typed-write-opaque-hub and project-served-opaque, with the
    # `opaque` legacy id form they tested.
    "typed-write-assigns-objectid", "typed-write-resend-same-ids",
    "write-projected-read-only-by-objectid",
}
SUCCESS = {"accepted", "partial", "written", "projected"}
SYNTHETIC_UUID = re.compile(r"^00000000-0000-[47]000-8000-0000000000[0-9a-fA-F]{2}$")
UUID_FORM = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _def(schema, name):
    return jsonschema.Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": schema["$defs"]})


def _strip_detail(value):
    if isinstance(value, dict):
        return {k: _strip_detail(v) for k, v in value.items() if k != "detail"}
    if isinstance(value, list):
        return [_strip_detail(v) for v in value]
    return value


def _response(cid):
    return CASES[cid]["expected"]["response"]


def _run(case):
    return _strip_detail(instances.run_case(copy.deepcopy(case), GRAMMAR))


def _refuses(response):
    return response["outcome"] == "rejected" or \
        any(e["result"] == "rejected" for e in response.get("elements") or []) or \
        any(r["result"] == "refused" for r in response.get("roles") or [])


# ── the case set ──────────────────────────────────────────────────────

def test_the_required_cases_exist():
    assert REQUIRED <= set(IDS), REQUIRED - set(IDS)


@pytest.mark.parametrize("cid", IDS)
def test_case_validates_against_the_case_schema(cid):
    case = CASES[cid]
    assert list(_def(SUBMIT_SCHEMA, "instanceCase").iter_errors(case)) == []
    assert case["id"] == cid


@pytest.mark.parametrize("cid", IDS)
def test_case_capabilities_are_a_valid_capability_document(cid):
    caps = CASES[cid]["capabilities"]
    assert list(jsonschema.Draft202012Validator(CAPS_SCHEMA).iter_errors(caps)) == []
    assert negotiate.capability_problems(caps) == []


@pytest.mark.parametrize("cid", IDS)
def test_the_reference_reproduces_the_expected_outcome(cid):
    assert _run(CASES[cid]) == CASES[cid]["expected"]


@pytest.mark.parametrize("cid", IDS)
def test_the_reference_does_not_mutate_its_inputs(cid):
    case = CASES[cid]
    before = copy.deepcopy(case)
    instances.run_case(case, GRAMMAR)
    assert case == before


@pytest.mark.parametrize("cid", [i for i in IDS if _refuses(_response(i))])
def test_every_refusal_has_a_passing_control(cid):
    case = CASES[cid]
    control = CASES[case["control"]]
    response = control["expected"]["response"]
    assert response["outcome"] in SUCCESS and not _refuses(response), case["control"]
    inputs = ("capabilities", "hubState", "submitter", "request", "body", "now")
    assert any(case.get(k) != control.get(k) for k in inputs)
    ok = {e["element"] for e in response.get("elements") or [] if e["result"] == "accepted"}
    for element in _response(cid).get("elements") or []:
        if element["result"] == "rejected":
            assert element["element"] in ok, element


def test_cases_are_synthetic():
    for path in CASE_PATHS:
        text = path.read_text()
        assert text.startswith("# SYNTHETIC CONFORMANCE CASE."), path.name
        assert "@" not in text, path.name
        for value in UUID_FORM.findall(text):
            assert SYNTHETIC_UUID.match(value), (path.name, value)


def test_assigned_object_ids_carry_the_hub_receipt_time():
    # Decided (maintainer, 2026-10-16, walk-through row 3; it was an
    # assumption of SPEC-REG-QUIRKS): an assigned ObjectId's timestamp is the
    # hub's receipt time (`now`), not the record's own time.
    seen = 0
    for cid, case in CASES.items():
        now = int(datetime.datetime.fromisoformat(case["now"].replace("Z", "+00:00")).timestamp())
        for oid in case.get("assignedIds") or []:
            assert quirks_registration.is_object_id(oid)
            assert int(oid[:8], 16) == now, (cid, oid)
            seen += 1
    assert seen >= 8


# ── rule 1: affects, over the vendor's own version strings ────────────

@pytest.mark.parametrize("version,expr,inside", [
    ("3.8.1.2026030500", ">=3.2.3 <3.14", True),
    ("3.14.8", ">=3.2.3 <3.14", False),       # 3.14.8 is after 3.14
    ("3.2.3", ">=3.2.3 <3.14", True),
    ("3.2", ">=3.2.3", False),                 # a prefix sorts first
    ("3.12.0", ">3.8", True),                  # numeric, not text, order
    ("0.9.2", "<1.0", True),
    ("1.0.0-test", "<1.0.0", False),           # text sorts after numbers
    ("anything", "*", True),
    ("1.0.1", "=1.0.1", True),
])
def test_a_version_range_compares_dotted_parts_numerically(version, expr, inside):
    assert quirks.in_range(version, expr) is inside


@pytest.mark.parametrize("expr", ["", "3.2", ">=", "~3.2"])
def test_a_malformed_range_is_refused(expr):
    with pytest.raises(ValueError):
        quirks.parse_range(expr)


def test_affected_distinguishes_unmeasured_from_outside():
    entry = {"affects": [{"vendor": "V", "product": "P", "versions": {"range": "<2"}},
                         {"vendor": "V", "product": "Q", "versions": {"unmeasured": "why"}}]}
    assert quirks.affected(entry, "V", "P", "1.5") is True
    assert quirks.affected(entry, "V", "P", "2.0") is False
    assert quirks.affected(entry, "V", "P", None) is None
    assert quirks.affected(entry, "V", "Q", "1.0") is None
    assert quirks.affected(entry, "W", "P", "1.0") is False
    assert quirks.affected({}, "V", "P", "1.0") is False


def test_the_registry_validates_and_affects_is_additive():
    # CHANGED 2026-10-16 (SPEC-REG-AMEND, row 6): 19 entries became 20 with
    # QUIRK-TREATMENTS-007 (Trio's `id`), a D20 entry like the two below.
    assert len(REGISTRY) == 20
    validator = jsonschema.Draft202012Validator(QUIRK_SCHEMA)
    jsonschema.Draft202012Validator.check_schema(QUIRK_SCHEMA)
    pre_d20 = [q for q in REGISTRY
               if not q["id"].endswith(("TREATMENTS-006", "TREATMENTS-007", "ENTRIES-004"))]
    assert len(pre_d20) == 17
    for quirk in REGISTRY:
        assert not list(validator.iter_errors({k: v for k, v in quirk.items()
                                                if k not in ("collection", "source_file")}))
    for quirk in pre_d20:
        assert not {"affects", "mapping", "applies_to"} & set(quirk), quirk["id"]


def test_a_range_is_stated_only_with_evidence():
    for quirk in REGISTRY:
        for item in quirk.get("affects") or []:
            versions = item["versions"]
            if "range" in versions:
                assert versions.get("seen") or item.get("evidence"), quirk["id"]
            for seen in versions.get("seen") or []:
                assert seen["claim"] in ("measured", "read-derived")
                if seen["claim"] == "read-derived":
                    assert re.search(r":\d+", seen["ref"]) and seen.get("commit"), seen


def test_an_affects_item_needs_a_range_or_says_unmeasured():
    validator = jsonschema.Draft202012Validator(QUIRK_SCHEMA)
    entry = copy.deepcopy({k: v for k, v in BY_ID["QUIRK-TREATMENTS-006"].items()
                           if k not in ("collection", "source_file")})
    assert not list(validator.iter_errors(entry))
    entry["affects"][0]["versions"] = {"seen": entry["affects"][0]["versions"]["seen"]}
    assert list(validator.iter_errors(entry))
    entry["affects"][0]["versions"] = {"range": "<1", "unmeasured": "both"}
    assert list(validator.iter_errors(entry))


def test_a_declaration_entry_needs_a_declaration_and_affects():
    validator = jsonschema.Draft202012Validator(QUIRK_SCHEMA)
    entry = {"id": "QUIRK-DECLARATION-901", "title": "t", "status": "proposed",
             "applies_to": "declarations", "kind": "slot-name", "reader_guidance": "r",
             "references": ["x"],
             "declaration": {"member": "slot", "value": "runningMode", "sameAs": "loopMode"},
             "affects": [{"vendor": "Example", "product": "LegacyController",
                          "versions": {"range": "<1.0"}}]}
    assert not list(validator.iter_errors(entry))
    for drop in ("declaration", "affects"):
        broken = {k: v for k, v in entry.items() if k != drop}
        assert list(validator.iter_errors(broken)), drop


# ── rule 7: today's _id handling as version-scoped entries ────────────

@pytest.mark.parametrize("qid,collection", [("QUIRK-TREATMENTS-006", "treatments"),
                                            ("QUIRK-ENTRIES-004", "entries")])
def test_the_id_handling_is_a_registry_entry(qid, collection):
    quirk = BY_ID[qid]
    assert quirk["collection"] == collection
    assert quirks_registration.ID_QUIRKS[collection] == qid
    assert quirk["mapping"] == {"action": "move-to-identifier", "flag": "UUID_HANDLING",
                                "erasesEvidence": True}
    assert all("unmeasured" in item["versions"] for item in quirk["affects"])
    detect = quirk["detect"]
    for value, fires in (("507f1f77bcf86cd799439011", False), ("507F1F77BCF86CD799439011", False),
                         ("00000000-0000-4000-8000-0000000000E1", True),
                         ("abcdefghijklmnopqrstuvwx", True)):
        assert quirks.evaluate(detect, {"_id": value}) is fires, value
    assert not quirks.evaluate(detect, {})


# ── rule 4: the lifecycle, measured ───────────────────────────────────

def _row(**kw):
    row = {"id": "Q-1", "status": "active", "documents": 0, "recent_documents": 0,
           "share": 0.0, "sites": 0, "expect": {}}
    row.update(kw)
    return row


AFFECTS = {"affects": [{"vendor": "V", "product": "P", "versions": {"range": "<2"}}]}


def test_historical_needs_no_recent_write_and_no_live_affected_instance():
    entry = AFFECTS
    life = quirks.lifecycle(_row(documents=5, recent_documents=0), entry,
                            [{"vendor": "V", "product": "P", "version": "3.0", "live": True}])
    assert "historical" in life["supported"] and life["live_instances"] == 0
    life = quirks.lifecycle(_row(documents=5, recent_documents=1), entry, [])
    assert "historical" not in life["supported"]
    assert life["why_not"]["historical"] == "1 recent document(s)"
    life = quirks.lifecycle(_row(documents=5), entry,
                            [{"vendor": "V", "product": "P", "version": "1.0", "live": True}])
    assert "historical" not in life["supported"]
    assert life["why_not"]["historical"] == "1 live affected instance(s)"
    life = quirks.lifecycle(_row(documents=5), entry, None)
    assert "historical" not in life["supported"] and life["live_instances"] is None
    assert life["why_not"]["historical"] == "live affected instances are unmeasured"


def test_retired_needs_no_stored_document_left():
    entry = AFFECTS
    assert "retired" in quirks.lifecycle(_row(documents=0), entry, [])["supported"]
    life = quirks.lifecycle(_row(documents=3), entry, [])
    assert life["supported"] == ["proposed", "active", "historical"]
    assert life["why_not"]["retired"] == "3 stored document(s) still depend on it"


def test_a_mapping_that_erases_its_evidence_cannot_go_historical_from_the_corpus():
    entry = dict(AFFECTS, mapping={"action": "move-to-identifier", "erasesEvidence": True})
    life = quirks.lifecycle(_row(documents=0, recent_documents=0), entry, [])
    assert "historical" not in life["supported"] and "retired" not in life["supported"]


def test_declaration_entries_are_measured_by_hub_records():
    life = quirks.lifecycle(_row(), {"applies_to": "declarations"}, [])
    assert life["supported"] == ["proposed"]


def test_check_fails_an_unsupported_historical_claim_and_never_a_proposed_one():
    row = _row(status="historical", documents=2, recent_documents=1)
    row["lifecycle"] = quirks.lifecycle(row, AFFECTS, [])
    assert quirks.check([row]) == [("Q-1", "historical not supported by measurement: "
                                           "1 recent document(s)")]
    row = _row(status="historical", documents=2)
    row["lifecycle"] = quirks.lifecycle(row, AFFECTS, [])
    assert quirks.check([row]) == []
    assert quirks.check([_row(status="proposed")]) == []
    assert quirks.check([_row(status="retired")]) == [("Q-1", "retired is asserted, not measured")]


def test_recent_is_a_declared_parameter():
    # Decided (maintainer, 2026-10-16, walk-through row 4): 365 days.
    assert quirks.RECENT_DAYS == 365


def _write(path, docs):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(docs))
    return path


def _ms(text):
    return int(datetime.datetime.fromisoformat(text + "+00:00").timestamp() * 1000)


def test_measure_counts_recent_writes_and_versions(tmp_path):
    # A synthetic corpus: one site, one snapshot dated 2026-04-26.
    treatments = _write(tmp_path / "s/treatments.json", [
        {"_id": "00000000-0000-4000-8000-0000000000E1", "created_at": "2026-04-20T10:00:00Z"},
        {"_id": "00000000-0000-4000-8000-0000000000E2", "created_at": "2024-01-01T10:00:00Z"},
        {"_id": "507f1f77bcf86cd799439011", "created_at": "2026-04-20T10:00:00Z"},
    ])
    devicestatus = _write(tmp_path / "s/devicestatus.json", [
        {"_id": "507f1f77bcf86cd799439012", "loop": {"version": "3.8.1"},
         "created_at": "2026-04-20T10:20:00Z"},
        {"_id": "507f1f77bcf86cd799439013", "loop": {"version": "3.2.3"},
         "created_at": "2024-01-01T08:30:00Z"},
    ])
    sources = [corpus.Source("2026-04-26", "s", "treatments", treatments),
               corpus.Source("2026-04-26", "s", "devicestatus", devicestatus)]
    quirk = copy.deepcopy(BY_ID["QUIRK-TREATMENTS-006"])
    [row] = quirks.measure([quirk], sources)
    assert (row["documents"], row["recent_documents"], row["newest"]) == (2, 1, "2026-04-20")
    # Co-occurrence within 60 minutes: the old document's nearest status is 90 minutes away.
    assert row["versions"] == {"LoopKit/Loop": {"by": "co-occurrence",
                                                "counts": {"3.8.1": 1, "unattributed": 1}}}
    [row] = quirks.measure([quirk], sources, recent_days=10000)
    assert row["recent_documents"] == 2
    # A pre-D20 entry keeps its measured row shape exactly.
    [plain] = quirks.measure([copy.deepcopy(BY_ID["QUIRK-TREATMENTS-005"])], sources)
    assert "recent_documents" not in plain and "versions" not in plain


def test_measure_reads_a_same_document_version(tmp_path):
    devicestatus = _write(tmp_path / "s/devicestatus.json", [
        {"loop": {"version": "3.12.1"}, "created_at": "2026-04-20T10:20:00Z", "pump": {"x": 1}}])
    quirk = {"id": "QUIRK-DEVICESTATUS-901", "title": "t", "status": "active", "kind": "sentinel",
             "path": "pump", "detect": {"path": "pump", "test": "is-object"},
             "collection": "devicestatus",
             "affects": [{"vendor": "LoopKit", "product": "Loop", "versions": {"unmeasured": "u"},
                          "versionSource": {"collection": "devicestatus", "path": "loop.version"}}]}
    [row] = quirks.measure([quirk], [corpus.Source("2026-04-26", "s", "devicestatus", devicestatus)])
    assert row["versions"]["LoopKit/Loop"] == {"by": "same-document", "counts": {"3.12.1": 1}}


# ── rule 2: the shared slot list ──────────────────────────────────────

def _registration_slots():
    out = {}
    for path in sorted((ROOT / "specs/sync/registrations").glob("*.yaml")):
        reg = yaml.safe_load(path.read_text())
        for span in reg["spec"].get("stateSpans") or []:
            if span.get("slot"):
                out.setdefault(span["slot"], set()).add(path.stem)
    return out


def test_the_shipped_shared_slots_are_names_already_used_identically():
    used = _registration_slots()
    for slot in SHARED["slots"]:
        assert set(slot["usedBy"]) == used.get(slot["name"], set()), slot["name"]
        assert len(slot["usedBy"]) >= 2, slot["name"]
    # Every name used by more than one registration is listed, and no other.
    assert {s["name"] for s in SHARED["slots"]} == {n for n, by in used.items() if len(by) >= 2}


def test_the_shared_slot_list_matches_the_capability_schema():
    caps = copy.deepcopy(CASES["same-as-definition-accepted"]["capabilities"])
    caps["wellKnown"]["slots"] = [{"name": s["name"]} for s in SHARED["slots"]]
    assert not list(jsonschema.Draft202012Validator(CAPS_SCHEMA).iter_errors(caps))


def test_same_as_is_meaning_and_known_to_the_strict_view():
    assert "sameAs" in negotiate.SPAN_MEANING
    body = CASES["same-as-definition-accepted"]["body"]
    assert sync_model.unknown_grammar_fields(body, GRAMMAR) == []
    other = copy.deepcopy(body)
    other["spec"]["stateSpans"][1]["sameAs"] = "override"
    assert negotiate.meaning("stateSpans", other["spec"]["stateSpans"][1]) != \
        negotiate.meaning("stateSpans", body["spec"]["stateSpans"][1])


def test_an_uninterpreted_same_as_derives_the_slot_name():
    caps = copy.deepcopy(CASES["same-as-role-granted"]["capabilities"])
    span = {"slot": "runningMode", "sameAs": "loopMode"}
    assert quirks_registration.slot_channel(caps, span, "E/P/x") == "loopMode"
    caps["grammar"]["interprets"] = ["apiVersion", "kind", "metadata", "spec.cadence",
                                     "spec.stateSpans.*.slot"]
    assert quirks_registration.slot_channel(caps, span, "E/P/x") == "runningMode"


def test_names_that_look_alike_never_share_a_channel():
    roles = _response("names-alike-do-not-contend")["roles"]
    assert roles == [{"channel": "runningMode", "role": "source", "provenance": "device",
                      "result": "granted"}]
    held = _response("same-as-role-held")["roles"][0]
    assert (held["channel"], held["result"], held["reasons"][0]["code"]) == \
        ("loopMode", "refused", "role-held")


def test_a_slot_is_shared_only_through_the_list_or_same_as():
    # Walk-through row 5 (maintainer, 2026-10-16). Equal names the shared list
    # does not hold, from different products, do not contend; the control,
    # the same case with `override` listed, is refused role-held.
    case = CASES["equal-names-unlisted-do-not-contend"]
    control = yaml.safe_load((ROOT / instances.CASES_DIR / "instance-role-held.yaml").read_text())
    assert "slots" not in case["capabilities"]["wellKnown"]
    assert control["capabilities"]["wellKnown"]["slots"] == [{"name": "override"}]
    listed = copy.deepcopy(case["capabilities"])
    listed["wellKnown"]["slots"] = [{"name": "override"}]
    assert listed == control["capabilities"]
    assert {k: v for k, v in case.items() if k not in ("id", "title", "description", "control",
                                                       "capabilities", "expected")} == \
        {k: v for k, v in control.items() if k not in ("id", "title", "description", "control",
                                                       "capabilities", "expected")}
    assert all(r["result"] == "granted" for r in _response(case["id"])["roles"])
    held = [r for r in control["expected"]["response"]["roles"] if r["channel"] == "override"]
    assert held and all(r["reasons"][0]["code"] == "role-held" for r in held)
    # The observation: on the owner's listing, never an overlap.
    observed = _response("slot-name-observation-recorded")
    assert observed["slotNameObservations"] == [
        {"slot": "override", "products": [{"vendor": "Example", "product": "ControllerA"},
                                          {"vendor": "Example", "product": "ControllerB"}]}]
    assert observed["overlaps"] == []
    listing = yaml.safe_load((ROOT / instances.CASES_DIR / "instance-overlap-listed.yaml")
                             .read_text())
    assert listing["expected"]["response"]["overlaps"]
    assert "slotNameObservations" not in listing["expected"]["response"]


def test_a_catalogue_mapping_is_scoped_to_the_versions_it_affects():
    applied = _response("catalogue-mapping-applied")["write"]
    assert applied["slotMapping"] == {"slot": "runningMode", "channel": "loopMode",
                                      "by": "catalogue", "quirk": "QUIRK-DECLARATION-901"}
    assert applied["quirksApplied"][0]["action"] == "same-as"
    for cid in ("catalogue-mapping-version-outside", "catalogue-mapping-version-unknown"):
        write = _response(cid)["write"]
        assert write["slotMapping"]["by"] == "name" and "quirksApplied" not in write, cid


# ── rules 5 and 6: two ids ────────────────────────────────────────────

@pytest.mark.parametrize("cid", [i for i in IDS if "ids" in (_response(i).get("write") or {})])
def test_every_write_reply_returns_both_ids(cid):
    case = CASES[cid]
    ids = _response(cid)["write"]["ids"]
    assert set(ids) == {"identifier", "_id"}
    # CHANGED 2026-10-16 (SPEC-REG-AMEND, row 2): asserted only on an
    # `objectId` hub; every hub's `_id` is now a 24-hex ObjectId.
    assert quirks_registration.is_object_id(ids["_id"]) and ids["_id"] == ids["_id"].lower()
    stored = [d["_id"] for d in case["hubState"].get("documents") or []] + \
        [r.get("_id") for r in case["hubState"].get("records") or []]
    sent = (case["request"]["write"].get("sent") or {}).get("_id")
    kept = [sent.lower()] if quirks_registration.is_object_id(sent) else []
    # The hub's key: stored, assigned now, or a client ObjectId kept. CHANGED
    # 2026-10-16 (row 2): "or (opaque) the typed id" is removed.
    assert ids["_id"] in stored + (case.get("assignedIds") or []) + kept, cid


def test_a_resend_matches_on_identifier_first_and_stores_no_second_copy():
    assert _response("carrier-resend-identifier-first")["write"]["matchedBy"] == "identifier"
    assert _response("carrier-resend-identifier-first")["write"]["ids"]["_id"] == \
        CASES["carrier-resend-identifier-first"]["hubState"]["documents"][0]["_id"]
    for cid in ("carrier-resend-matches-identifier", "carrier-uuid-resend-matches",
                "typed-write-resend-same-ids"):
        case = CASES[cid]
        assert case["expected"]["stateAfter"] == case["hubState"], cid
    assert _response("carrier-resend-matches-objectid")["write"]["matchedBy"] == "_id"


def test_every_hub_serves_24_hex_ids_and_declares_no_legacy_id_form():
    # REPLACES test_the_legacy_id_form_is_declared_and_defaults_to_object_id
    # (SPEC-REG-AMEND, walk-through rows 1 and 2, maintainer 2026-10-16):
    # `objectId` names the shape, a 24-hex value the hub assigns, on either
    # store, and every hub's legacy surface serves it. The capability member
    # `legacyIdForm` and its `opaque` option are removed: a document that
    # still sends one is read as if it did not (must-ignore), never as a
    # licence to keep a client's string `_id` or to serve the typed id.
    assert "legacyIdForm" not in CAPS_SCHEMA["properties"]
    assert '"opaque"' not in json.dumps(CAPS_SCHEMA)
    assert not hasattr(quirks_registration, "LEGACY_ID_FORMS")
    assert not any("legacyIdForm" in c["capabilities"] for c in CASES.values())
    for cid in ("project-served-opaque", "typed-write-opaque-hub"):
        assert cid not in IDS, cid
    # A stale `opaque` declaration changes nothing: the typed write still
    # gets an ObjectId the hub assigns, and its projection carries it.
    case = copy.deepcopy(CASES["typed-write-assigns-objectid"])
    case["capabilities"]["legacyIdForm"] = "opaque"
    assert _run(case) == case["expected"]
    ids = _run(case)["response"]["write"]["ids"]
    assert quirks_registration.is_object_id(ids["_id"]) and ids["_id"] != ids["identifier"]


# ── rule 7: behaviour unchanged ───────────────────────────────────────

@pytest.mark.parametrize("sent,expected", [
    ({"_id": "00000000-0000-4000-8000-0000000000E1"},
     (None, "00000000-0000-4000-8000-0000000000E1", "moved-to-identifier")),
    ({"_id": "00000000-0000-4000-8000-0000000000E1", "identifier": "x"}, (None, "x", "dropped")),
    ({"_id": "507F1F77BCF86CD799439011"}, ("507f1f77bcf86cd799439011", None, None)),
    ({"_id": {"$oid": "507f1f77bcf86cd799439011"}}, ("507f1f77bcf86cd799439011", None, None)),
    ({"_id": ""}, (None, None, None)),
])
def test_the_id_handling_matches_cgm_remote_monitor(sent, expected):
    # normalizeTreatmentId, lib/server/treatments.js:394-411 at official a8888f0d
    # (read-derived), with UUID_HANDLING at its default (true).
    # CHANGED 2026-10-16 (SPEC-REG-AMEND, row 2): the capability argument is
    # gone with `legacyIdForm`; the handling is the same on every hub.
    _id, identifier, applied = quirks_registration.normalise_sent_id("treatments", sent)
    assert (_id, identifier, applied[0]["action"] if applied else None) == expected


def test_no_hub_keeps_a_string_id():
    # REPLACES test_an_opaque_hub_keeps_a_string_id (SPEC-REG-AMEND, row 2):
    # a client's non-ObjectId string `_id` is never stored, on any hub.
    _id, identifier, applied = quirks_registration.normalise_sent_id("treatments", {"_id": "k"})
    assert (_id, identifier) == (None, "k")
    assert applied == [{"quirk": "QUIRK-TREATMENTS-006", "member": "_id",
                        "action": "moved-to-identifier"}]


# ── rule 8: the projected record's ObjectId is stored ─────────────────

def test_the_object_id_assigned_at_the_typed_write_is_the_projected_id():
    case = CASES["typed-write-assigns-objectid"]
    [record] = [r for r in case["expected"]["stateAfter"]["records"]]
    assert record["_id"] == case["assignedIds"][0] == _response(case["id"])["write"]["ids"]["_id"]
    record = dict(record, startedAt="2026-10-15T11:00:00Z", durationSeconds=600)
    caps, state = case["capabilities"], case["expected"]["stateAfter"]
    wk = case["wellKnownRegistrations"]
    first = instances.project(caps, state, record, wk)["document"]
    second = instances.project(caps, state, copy.deepcopy(record), wk)["document"]
    assert first["_id"] == second["_id"] == record["_id"]
    assert first["identifier"] == record["id"]


def test_a_hub_never_projects_a_record_without_its_stored_id():
    # CHANGED 2026-10-16 (SPEC-REG-AMEND, row 2): this used the removed case
    # project-served-opaque, and its control asserted the opaque hub's typed
    # id for both. The record is now typed-write-assigns-objectid's, with its
    # stored `_id` removed; no hub falls back to the typed id.
    case = CASES["typed-write-assigns-objectid"]
    [record] = case["expected"]["stateAfter"]["records"]
    record = dict(record, startedAt="2026-10-15T11:00:00Z", durationSeconds=600)
    state, wk = case["expected"]["stateAfter"], case["wellKnownRegistrations"]
    assert instances.project(case["capabilities"], state, record, wk)["document"]["_id"] == \
        record["_id"]
    bare = {k: v for k, v in record.items() if k != "_id"}
    with pytest.raises(ValueError, match="assigned at the typed write"):
        instances.project(case["capabilities"], state, bare, wk)


def test_the_existing_case_sets_keep_their_counts():
    # CHANGED 2026-10-16 (SPEC-REG-AMEND): 55 negotiation cases became 54
    # (typed-write-load-deadline-passed removed, row 8) and 86 instance cases
    # became 90 (rows 7 and 9 added four).
    # CHANGED 2026-10-17 (SPEC-REG-AMEND-2): 90 instance cases became 103
    # (rows 14, 15 and 16 added four, one and eight); the 54 negotiation cases
    # are unchanged.
    assert len(list((ROOT / negotiate.CONFORMANCE_DIR).glob("*.yaml"))) == 54
    assert len(list((ROOT / instances.CASES_DIR).glob("*.yaml"))) == 103


def test_the_new_reason_code_is_a_shared_value():
    assert not list(_def(SUBMIT_SCHEMA, "reason").iter_errors({"code": "unknown-shared-slot"}))
