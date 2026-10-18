"""Registration grammar: the D18 addendum, rules 1-5 (queue item SCHEMA-REG-EXT).

Execution plan §2.6.1. Every extensible field is typed: controller data is
accepted only with a type declaration, never as an untyped bag. Each
rejection test here is paired with a control that passes, so a test cannot
pass because everything is rejected.
"""

import copy
import json

import jsonschema
import pytest
import yaml

from nsschema import corpus, sync_model

ROOT = corpus.repo_root()
SCHEMA = json.loads((ROOT / sync_model.SCHEMA).read_text())
FIXTURE_PATH = ROOT / sync_model.FIXTURES_DIR / "example-testcontroller.yaml"
GENERATED = sorted(sync_model.CONTROLLERS)


def _validator():
    return jsonschema.Draft202012Validator(SCHEMA)


def _errors(doc):
    return list(_validator().iter_errors(doc))


def _valid(doc):
    return not _errors(doc)


def _fixture():
    return yaml.safe_load(FIXTURE_PATH.read_text())


def _committed(key):
    return yaml.safe_load((ROOT / sync_model.OUT_DIR / f"{key}.yaml").read_text())


def _strip_x(doc):
    return {k: v for k, v in doc.items() if not k.startswith("x-")}


def _def_validator(name):
    return jsonschema.Draft202012Validator(
        {"$ref": f"#/$defs/{name}", "$defs": SCHEMA["$defs"]})


def test_schema_is_a_valid_2020_12_schema():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


# ── the three generated registrations ──────────────────────────────────

@pytest.mark.parametrize("key", GENERATED)
def test_generated_registration_validates_and_uses_only_known_members(key):
    registration = _strip_x(_committed(key))
    assert _valid(registration)
    assert sync_model.unknown_grammar_fields(registration, SCHEMA) == []


@pytest.mark.parametrize("key", GENERATED)
def test_generated_registration_is_unchanged_in_meaning(key):
    # The grammar change adds typing and horizons; the names, paths and
    # statuses the registrations carried before are the same, and projecting
    # the additions away yields the 2026-09-11 form, which still validates.
    registration = _strip_x(_committed(key))
    built = sync_model.build(ROOT, key, sync_model.CONTROLLERS[key])
    assert _strip_x(built) == registration
    legacy = copy.deepcopy(registration)
    legacy["spec"]["settings"]["fields"] = [
        f["name"] for f in legacy["spec"]["settings"]["fields"]]
    legacy["spec"]["settings"].pop("horizon")
    for row in legacy["spec"]["replayInputs"]:
        row.pop("typeRef", None)
        assert set(row) == {"input", "path", "collection", "status"}
        assert row["status"] in ("recorded", "derivable", "partial", "absent")
    for document in legacy["spec"]["documents"]:
        document.pop("horizon", None)
    assert _valid(legacy)


@pytest.mark.parametrize("key", GENERATED)
def test_generated_types_are_references_within_the_subset(key):
    # Types are referenced from controller-settings.schema.json, not
    # restated, and only where that definition was read from this
    # controller's own algorithm family.
    registration = _committed(key)
    family = registration["metadata"]["algorithmFamily"]
    typed = [f for f in registration["spec"]["settings"]["fields"] if "typeRef" in f]
    typed += [r for r in registration["spec"]["replayInputs"] if "typeRef" in r]
    assert typed, key
    fragment = _def_validator("typeFragment")
    for field in typed:
        assert "type" not in field
        definition = sync_model.resolve_type_ref(ROOT, field["typeRef"])
        assert definition["x-algorithm"] == family
        assert definition["x-source"] == sync_model.FAMILY_SOURCE[family]
        core = {k: v for k, v in definition.items()
                if not k.startswith("x-") and k != "description"}
        assert not list(fragment.iter_errors(core)), field["typeRef"]


def test_a_definition_from_another_family_is_left_untyped():
    # suspendThreshold's settings definition is labelled oref0 but typed from
    # Loop's AlgorithmInput: omitted for both rather than guessed.
    for key in GENERATED:
        reg = _committed(key)
        fields = {f["name"]: f for f in reg["spec"]["settings"]["fields"]}
        inputs = {r["input"]: r for r in reg["spec"]["replayInputs"]}
        for name in ("suspendThreshold", "profile.suspendThreshold"):
            for table in (fields, inputs):
                if name in table:
                    assert "typeRef" not in table[name], (key, name)
        # Per-cycle state is never typed as a setting.
        for name in ("profile.sensitivity", "iob.iob", "glucoseStatus.glucose"):
            if name in inputs:
                assert "typeRef" not in inputs[name], (key, name)


# ── the unfamiliar test registration ──────────────────────────────────

def test_fixture_validates():
    assert _errors(_fixture()) == []


def test_fixture_exercises_every_rule():
    spec = _fixture()["spec"]
    assert _fixture()["metadata"]["tier"] == "controller-owned"
    assert sync_model.unknown_grammar_fields(_fixture(), SCHEMA)          # rule 1
    assert any(k.startswith("com.example.") for k in spec["extensions"])  # rule 1
    assert any(isinstance(f, dict) and "type" in f
               for f in spec["settings"]["fields"])                       # rule 2
    assert any(isinstance(f, dict) and "typeRef" in f
               for f in spec["settings"]["fields"])                       # rule 2
    assert any(isinstance(f, dict) and "sensitivity" not in f
               for f in spec["settings"]["fields"])                       # rule 2
    others = [spec["documents"][0]["discriminator"]["test"],
              spec["stateSpans"][0]["wire"]["endedEncoding"],
              spec["commands"][0]["transport"],
              spec["replayInputs"][1]["status"]]
    assert all(o["value"] == "other" for o in others)                     # rule 3
    versions = spec["stateSpans"][0]["versions"]
    assert len(versions["served"]) == 2 and "mappings" not in versions    # rule 4
    aggregate = spec["stateSpans"][1]
    assert aggregate["availability"] == "experimental"                    # rule 5
    assert aggregate["horizon"]["class"] == "aggregate"                   # rule 5


# ── rule 1: must-ignore and typed extensions ──────────────────────────

def test_an_unknown_grammar_field_is_ignored_not_rejected():
    doc = _fixture()
    assert _valid(doc)
    ignored = sync_model.unknown_grammar_fields(doc, SCHEMA)
    assert ignored == ["spec.futureGrammarMember", "spec.stateSpans.0.futureSpanMember"]
    # Kept as written: nothing in reading it removed the member.
    assert doc["spec"]["futureGrammarMember"]["note"]

    # And on a generated registration, at three depths.
    loop = _strip_x(_committed("loop"))
    loop["newTopLevel"] = 1
    loop["metadata"]["newMetadata"] = "x"
    loop["spec"]["stateSpans"][0]["wire"]["newWireMember"] = []
    assert _valid(loop)
    assert sync_model.unknown_grammar_fields(loop, SCHEMA) == [
        "metadata.newMetadata", "newTopLevel", "spec.stateSpans.0.wire.newWireMember"]


def test_must_ignore_does_not_reach_values_of_a_closed_list():
    # Rejection: an unknown *value* of a list that is not open is still an error.
    doc = _fixture()
    doc["spec"]["documents"][0]["collection"] = "notACollection"
    assert _errors(doc)
    # Control.
    doc["spec"]["documents"][0]["collection"] = "devicestatus"
    assert _valid(doc)


def _with_extension(extension, namespace="com.example.testcontroller.probe"):
    doc = _fixture()
    doc["spec"]["extensions"] = {namespace: extension}
    return doc


def test_an_extension_without_a_type_declaration_is_rejected():
    untyped = {"version": "1", "fields": [{"name": "bag"}]}
    assert _errors(_with_extension(untyped))
    # Control: the same extension with a type validates.
    typed = {"version": "1", "fields": [{"name": "bag", "type": {"type": "string"}}]}
    assert _valid(_with_extension(typed))
    # Control: a reference to a published type validates.
    ref = {"version": "1", "fields": [{
        "name": "maxIob",
        "typeRef": "https://nightscout.dev/schemas/sync/controller-settings.json"
                   "#/properties/settings/properties/maxIob"}]}
    assert _valid(_with_extension(ref))


def test_an_extension_with_no_fields_or_no_version_is_rejected():
    assert _errors(_with_extension({"version": "1"}))
    assert _errors(_with_extension({"version": "1", "fields": []}))
    assert _errors(_with_extension({"fields": [{"name": "a", "type": {"type": "boolean"}}]}))
    # Control.
    assert _valid(_with_extension(
        {"version": "1", "fields": [{"name": "a", "type": {"type": "boolean"}}]}))


def test_an_object_or_array_type_must_say_what_it_holds():
    # An `object` with no properties is an untyped bag by another name.
    bag = {"version": "1", "fields": [{"name": "a", "type": {"type": "object"}}]}
    assert _errors(_with_extension(bag))
    listless = {"version": "1", "fields": [{"name": "a", "type": {"type": "array"}}]}
    assert _errors(_with_extension(listless))
    # Control.
    shaped = {"version": "1", "fields": [{"name": "a", "type": {
        "type": "object", "properties": {"b": {"type": "integer"}}}}]}
    assert _valid(_with_extension(shaped))


def test_a_type_fragment_outside_the_subset_is_rejected():
    # The fragment is closed: a keyword the hub would not apply is rejected
    # rather than silently dropped.
    for keyword, value in (("pattern", "^a"), ("oneOf", [{"type": "string"}]),
                           ("$ref", "https://example.invalid/s.json")):
        outside = {"version": "1", "fields": [
            {"name": "a", "type": {"type": "string", keyword: value}}]}
        assert _errors(_with_extension(outside)), keyword
    # Control.
    inside = {"version": "1", "fields": [
        {"name": "a", "type": {"type": "string", "enum": ["x"], "format": "date-time"}}]}
    assert _valid(_with_extension(inside))


def test_an_extension_namespace_must_be_reverse_dns():
    typed = {"version": "1", "fields": [{"name": "a", "type": {"type": "boolean"}}]}
    for bad in ("probe", "Example.probe", "com..example", ".com.example"):
        assert _errors(_with_extension(typed, bad)), bad
    # Control.
    assert _valid(_with_extension(typed, "org.example-controller.probe"))


def test_type_and_type_ref_are_alternatives():
    both = {"version": "1", "fields": [{
        "name": "a", "type": {"type": "number"},
        "typeRef": "https://nightscout.dev/schemas/sync/controller-settings.json"
                   "#/properties/settings/properties/maxIob"}]}
    assert _errors(_with_extension(both))


# ── rule 2: typed fields and the unlabelled default ───────────────────

def _field(doc, name):
    return next(f for f in doc["spec"]["settings"]["fields"]
                if isinstance(f, dict) and f["name"] == name)


def test_an_unlabelled_field_resolves_to_withhold():
    doc = _fixture()
    unlabelled = _field(doc, "exampleUnlabelledSetting")
    assert "sensitivity" not in unlabelled
    assert sync_model.field_disclosure(doc, unlabelled) == {"unlabelled": "withhold"}
    # The name-only form is unlabelled too.
    assert sync_model.field_disclosure(doc, "legacyNameOnlySetting") == {
        "unlabelled": "withhold"}
    # With no sensitivity block at all, the default is still withhold.
    bare = copy.deepcopy(doc)
    bare["spec"].pop("sensitivity")
    assert _valid(bare)
    assert sync_model.field_disclosure(bare, unlabelled) == {"unlabelled": "withhold"}
    # Control: a labelled field resolves to its label.
    labelled = _field(doc, "maxIob")
    assert sync_model.field_disclosure(doc, labelled) == {
        "labelled": {"level": "descriptive", "category": "therapy-setting"}}


@pytest.mark.parametrize("key", GENERATED)
def test_generated_settings_carry_no_labels_and_so_are_withheld(key):
    # The registrations do not invent labels; their fields fall to the
    # declared unlabelledPolicy, which is withhold.
    reg = _committed(key)
    for field in reg["spec"]["settings"]["fields"]:
        assert sync_model.field_disclosure(reg, field) == {"unlabelled": "withhold"}


def test_sensitivity_label_vocabulary_matches_sensitivity_yaml():
    spec = yaml.safe_load((ROOT / "specs/sync/sensitivity.yaml").read_text())
    label = SCHEMA["$defs"]["sensitivityLabel"]["properties"]
    assert label["level"]["enum"] == [s["id"] for s in spec["sensitivity_levels"]]
    assert label["category"]["enum"] == [c["id"] for c in spec["categories"]]


def test_an_unknown_sensitivity_level_is_rejected():
    doc = _fixture()
    _field(doc, "maxIob")["sensitivity"]["level"] = "public"
    assert _errors(doc)
    _field(doc, "maxIob")["sensitivity"]["level"] = "descriptive"
    assert _valid(doc)


def test_settings_fields_still_accept_the_name_only_form():
    loop = _strip_x(_committed("loop"))
    loop["spec"]["settings"]["fields"] = ["maxBolus", "maxBasalRate"]
    assert _valid(loop)


# ── rule 3: open vocabularies ─────────────────────────────────────────

def _at(doc, location):
    spec = doc["spec"]
    return {
        "discriminator": (spec["documents"][0]["discriminator"], "test"),
        "endedEncoding": (spec["stateSpans"][0]["wire"], "endedEncoding"),
        "transport": (spec["commands"][0], "transport"),
        "status": (spec["replayInputs"][1], "status"),
    }[location]


OPEN_LISTS = ["discriminator", "endedEncoding", "transport", "status"]


@pytest.mark.parametrize("location", OPEN_LISTS)
def test_an_unknown_term_validates_as_other_plus_controller_term(location):
    doc = _fixture()
    node, key = _at(doc, location)
    node[key] = {"value": "other", "controllerTerm": "brandNewTerm"}
    assert _valid(doc)
    assert sync_model.term_label(node[key]) == "other: brandNewTerm"


@pytest.mark.parametrize("location", OPEN_LISTS)
def test_a_bare_unknown_term_is_rejected(location):
    doc = _fixture()
    node, key = _at(doc, location)
    for bad in ("brandNewTerm", "other", {"value": "other"},
                {"value": "brandNewTerm", "controllerTerm": "x"},
                {"value": "other", "controllerTerm": ""}):
        node[key] = bad
        assert _errors(doc), (location, bad)


def test_a_shared_term_still_validates_as_a_plain_string():
    doc = _fixture()
    for location, shared in (("discriminator", "is-object"),
                             ("endedEncoding", "amend-duration"),
                             ("transport", "apns"), ("status", "absent")):
        node, key = _at(doc, location)
        node[key] = shared
        assert sync_model.term_label(shared) == shared
    assert _valid(doc)


def test_carrier_discriminators_are_open_too():
    doc = _fixture()
    wire = doc["spec"]["stateSpans"][0]["wire"]
    wire["discriminator"] = {"path": "x", "test": {"value": "other",
                                                  "controllerTerm": "matches-regex"}}
    assert _valid(doc)
    wire["discriminator"]["test"] = "matches-regex"
    assert _errors(doc)


def test_an_other_end_reason_needs_its_controller_term():
    doc = _fixture()
    reasons = doc["spec"]["stateSpans"][0]["endReasons"]
    assert reasons[1] == {"reason": "other", "controllerTerm": "replacedByScheduleChange"}
    reasons[1] = {"reason": "other"}
    assert _errors(doc)
    reasons[1] = {"reason": "replacedByScheduleChange"}
    assert _errors(doc)
    # Control: a shared reason needs no term.
    reasons[1] = {"reason": "cancelled"}
    assert _valid(doc)


def test_completeness_counts_an_other_status_by_its_label():
    stats = sync_model.completeness(_fixture())
    assert stats["by_status"] == {"recorded": 1, "other: computed-on-device-only": 1}


# ── rule 4: per-kind versions ─────────────────────────────────────────

def test_two_served_versions_with_no_mapping_validate_and_are_not_converted():
    doc = _fixture()
    span = doc["spec"]["stateSpans"][0]
    assert span["versions"] == {"served": ["1", "2"], "stored": "2"}
    assert _valid(doc)
    assert sync_model.version_plan(span) == {
        "1": {"storedAs": "1", "convertedVia": None},
        "2": {"storedAs": "2", "convertedVia": None},
    }
    # Control: with a declared lossless mapping, version 1 is converted.
    mapping = {"from": "1", "to": "2", "lossless": True}
    span["versions"]["mappings"] = [mapping]
    assert _valid(doc)
    assert sync_model.version_plan(span)["1"] == {"storedAs": "2", "convertedVia": mapping}


def test_a_lossy_mapping_is_rejected():
    doc = _fixture()
    versions = doc["spec"]["stateSpans"][0]["versions"]
    versions["mappings"] = [{"from": "1", "to": "2", "lossless": False}]
    assert _errors(doc)
    versions["mappings"] = [{"from": "1", "to": "2", "lossless": True}]
    assert _valid(doc)


def test_a_stored_version_must_be_served():
    span = {"versions": {"served": ["1", "2"], "stored": "3"}}
    with pytest.raises(ValueError):
        sync_model.version_plan(span)
    assert sync_model.version_plan({"version": "1"}) == {
        "1": {"storedAs": "1", "convertedVia": None}}


def test_extensions_carry_their_own_version():
    ext = _fixture()["spec"]["extensions"]["com.example.testcontroller.adaptiveTargets"]
    assert sync_model.version_plan(ext) == {"1": {"storedAs": "1", "convertedVia": None}}


# ── rule 5: horizons and experimental availability ────────────────────

def test_horizon_classes_and_retention():
    doc = _fixture()
    horizon = doc["spec"]["stateSpans"][1]["horizon"]
    for good in ("P30D", "P1Y", "PT12H", "indefinite"):
        horizon["retention"] = good
        assert _valid(doc), good
    for bad in ("30 days", "P", "PT", "forever"):
        horizon["retention"] = bad
        assert _errors(doc), bad
    horizon["retention"] = "P30D"
    horizon["class"] = "rolling"
    assert _errors(doc)
    horizon["class"] = "aggregate"
    assert _valid(doc)


def test_experimental_is_an_availability_and_others_are_not():
    doc = _fixture()
    span = doc["spec"]["stateSpans"][1]
    assert span["availability"] == "experimental"
    span["availability"] = "beta"
    assert _errors(doc)
    span["availability"] = "dev-only"
    assert _valid(doc)


# ── state and intent: initiators, carrier durations, typed carrier paths ──
#
# docs/30-design/platform/spec/state-intent.md S6-S8 (queue item
# SCHEMA-INTENT-GAPS). Each addition is additive: a registration that does
# not use it validates and reads as before.

def _span0(doc):
    return doc["spec"]["stateSpans"][0]


def test_fixture_exercises_the_intent_forms():
    span = _span0(_fixture())
    values = span["initiators"]["values"]
    assert any(isinstance(v, str) for v in values)
    assert {"value": "other", "controllerTerm": "example-agent"} in values
    for carrier in ("wire", "requested", "applied"):
        assert span[carrier]["durationField"] and span[carrier]["durationUnit"], carrier
    paths = span["wire"]["paths"] + span["applied"]["paths"]
    assert any(isinstance(p, str) for p in paths)
    assert any(isinstance(p, dict) and "unit" in p and "type" in p for p in paths)
    assert any(isinstance(p, dict) and "typeRef" in p for p in paths)
    # Every new member is one the grammar defines: none is merely ignored.
    assert sync_model.unknown_grammar_fields(_fixture(), SCHEMA) == [
        "spec.futureGrammarMember", "spec.stateSpans.0.futureSpanMember"]


def test_an_initiator_outside_the_vocabulary_takes_the_other_form():
    doc = _fixture()
    values = _span0(doc)["initiators"]["values"]
    values[:] = ["phone", {"value": "other", "controllerTerm": "agent"}]
    assert _valid(doc)
    assert sync_model.unknown_grammar_fields(doc, SCHEMA) == [
        "spec.futureGrammarMember", "spec.stateSpans.0.futureSpanMember"]
    assert [sync_model.term_label(v) for v in values] == ["phone", "other: agent"]
    # The controller's own vocabulary is free strings: any string is valid.
    values[:] = ["anyControllerTerm", "other"]
    assert _valid(doc)


def test_an_initiator_object_must_be_the_other_form():
    doc = _fixture()
    values = _span0(doc)["initiators"]["values"]
    for bad in ({"value": "other"}, {"value": "other", "controllerTerm": ""},
                {"value": "agent", "controllerTerm": "x"}, {"controllerTerm": "x"}, 7):
        values[:] = ["phone", bad]
        assert _errors(doc), bad
    # Control.
    values[:] = ["phone", {"value": "other", "controllerTerm": "x"}]
    assert _valid(doc)


@pytest.mark.parametrize("carrier", ["wire", "requested", "applied"])
def test_every_carrier_declares_a_duration_unit_from_one_list(carrier):
    doc = _fixture()
    node = _span0(doc)[carrier]
    for unit in ("seconds", "minutes", "milliseconds"):
        node["durationUnit"] = unit
        assert _valid(doc), unit
    for bad in ("hours", "Seconds", "ms", 60, None):
        node["durationUnit"] = bad
        assert _errors(doc), bad
    node["durationUnit"] = "seconds"
    node["durationField"] = 3
    assert _errors(doc)


def test_a_carrier_without_a_duration_reads_as_before():
    doc = _fixture()
    for carrier in ("requested", "applied"):
        _span0(doc)[carrier].pop("durationField")
        _span0(doc)[carrier].pop("durationUnit")
    assert _valid(doc)


def test_a_carrier_path_may_be_typed():
    doc = _fixture()
    paths = _span0(doc)["applied"]["paths"]
    paths[:] = ["a.b",
                {"path": "a.c"},
                {"path": "a.d", "unit": "milliseconds"},
                {"path": "a.e", "type": {"type": "integer", "minimum": 0}},
                {"path": "a.f", "typeRef": "https://nightscout.dev/schemas/sync/"
                 "controller-settings.json#/properties/settings/properties/maxIob"}]
    assert _valid(doc)
    assert sync_model.unknown_grammar_fields(doc, SCHEMA) == [
        "spec.futureGrammarMember", "spec.stateSpans.0.futureSpanMember"]


def test_a_typed_carrier_path_needs_its_path():
    doc = _fixture()
    paths = _span0(doc)["wire"]["paths"]
    for bad in ({"unit": "milliseconds"}, {"path": "", "unit": "seconds"},
                {"path": 5}, {"path": "a", "type": {"type": "object"}},
                {"path": "a", "type": {"type": "string", "pattern": "^x"}},
                {"path": "a", "type": {"type": "number"},
                 "typeRef": "https://nightscout.dev/schemas/sync/"
                 "controller-settings.json#/properties/settings/properties/maxIob"}):
        paths[:] = ["reason", bad]
        assert _errors(doc), bad
    # Control: the bare string form is still valid, alone or mixed.
    paths[:] = ["reason", "timeOffset"]
    assert _valid(doc)
    paths[:] = ["reason", {"path": "timeOffset", "unit": "milliseconds"}]
    assert _valid(doc)


def test_an_unknown_member_of_a_typed_path_is_ignored_not_rejected():
    doc = _fixture()
    paths = _span0(doc)["wire"]["paths"]
    paths[:] = [{"path": "timeOffset", "unit": "milliseconds", "futurePathMember": 1}]
    assert _valid(doc)
    assert "spec.stateSpans.0.wire.paths.0.futurePathMember" in \
        sync_model.unknown_grammar_fields(doc, SCHEMA)


def test_generated_registrations_declare_the_established_units():
    loop = _committed("loop")["spec"]["stateSpans"][0]
    assert loop["kind"] == "TemporaryScheduleOverride"
    assert (loop["applied"]["durationField"], loop["applied"]["durationUnit"]) == (
        "override.duration", "seconds")
    assert loop["applied"]["timeField"] == "override.timestamp"
    assert loop["applied"]["activeField"] == "override.active"
    assert (loop["wire"]["durationField"], loop["wire"]["durationUnit"]) == (
        "duration", "minutes")
    aaps = _committed("androidaps")["spec"]["stateSpans"][0]
    assert aaps["kind"] == "ProfileSwitch"
    assert {"path": "timeshift", "unit": "milliseconds"} in aaps["wire"]["paths"]
    assert {"path": "originalTimeshift", "unit": "milliseconds"} in aaps["applied"]["paths"]


@pytest.mark.parametrize("key", GENERATED)
def test_generated_registrations_without_the_intent_forms_still_validate(key):
    # Projecting the additions away (path objects to strings, carrier units
    # off requested and applied) yields a registration the grammar accepts.
    registration = copy.deepcopy(_strip_x(_committed(key)))
    for span in registration["spec"]["stateSpans"]:
        for name in ("wire", "requested", "applied"):
            carrier = span.get(name)
            if not carrier:
                continue
            if "paths" in carrier:
                carrier["paths"] = [p["path"] if isinstance(p, dict) else p
                                    for p in carrier["paths"]]
            carrier.pop("timeField", None)
            carrier.pop("activeField", None)
            if name != "wire":
                carrier.pop("durationField", None)
                carrier.pop("durationUnit", None)
        for value in (span.get("initiators") or {}).get("values", []):
            assert isinstance(value, str)
    assert _valid(registration)
    assert sync_model.unknown_grammar_fields(registration, SCHEMA) == []


# SPEC-ACTIVE-STATE: a carrier names the field holding its record's own time.
@pytest.mark.parametrize("carrier", ["wire", "applied"])
@pytest.mark.parametrize("member", ["timeField", "activeField"])
def test_a_carrier_declares_its_time_and_active_fields(carrier, member):
    doc = _fixture()
    span = _span0(doc)
    span.setdefault(carrier, {"collection": "devicestatus"})
    span[carrier][member] = "override.timestamp"
    assert _valid(doc)
    for bad in ("", 5, None):
        span[carrier][member] = bad
        assert not _valid(doc), bad
