"""Unit tests for the nsschema evidence pipeline.

Run: python3 -m pytest tools/nsschema/test_nsschema.py
"""

import json
import re
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nsschema import census, corpus, diff, redact, specload, tiers  # noqa: E402


# ── redaction ───────────────────────────────────────────────────────────

def test_identifying_field_names_are_denied():
    for path in ("_id", "treatments._id", "enteredBy", "loopSettings.deviceToken",
                 "notes", "pump.pumpID", "store.{}.name", "apiSecret"):
        assert redact.is_denied(path), path


def test_enum_like_field_names_are_allowed():
    for path in ("direction", "eventType", "type", "units", "insulinType",
                 "pump.manufacturer", "temp"):
        assert not redact.is_denied(path), path


def test_scrub_masks_identifying_substructure():
    # Runs of four or more digits are masked; shorter runs are model and
    # version numbers (a Medtronic 754, a Loop 3.12) and are kept.
    assert redact.scrub("Medtronic-754-12345678") == "Medtronic-754-<n>"
    assert redact.scrub("https://site.example.com/x") == "<url>"
    assert redact.scrub("person@example.com") == "<email>"
    assert redact.scrub("deadbeefdeadbeefdead") == "<hex>"


def test_long_strings_are_not_recordable():
    assert not redact.recordable("direction", "x" * 200)
    assert redact.recordable("direction", "Flat")


def test_census_never_records_a_denied_field_value():
    stat = census.FieldStat()
    stat.observe("enteredBy", "a name that would identify someone", "a", "s")
    stat.observe("enteredBy", "a name that would identify someone", "b", "s")
    stat.observe("enteredBy", "a name that would identify someone", "c", "s")
    out = stat.to_dict("enteredBy", 1, {"a": 1})
    assert out["string"]["distinct_values"] is None


def test_census_drops_values_once_cardinality_is_exceeded():
    stat = census.FieldStat()
    for i in range(redact.MAX_DISTINCT + 5):
        stat.observe("device", f"dev-{i}", "a", "s")
    out = stat.to_dict("device", 1, {"a": 1})
    assert out["string"]["distinct_values"] is None


def test_a_value_seen_on_one_site_only_is_withheld():
    # A neutral field name, so only the corroboration rule can catch this.
    stat = census.FieldStat()
    stat.observe("theme", "a-value-only-this-site-uses", "a", "s")
    out = stat.to_dict("theme", 1, {"a": 1})
    assert out["string"]["distinct_values"] is None
    assert "fewer than" in out["string"]["value_note"]


def test_dashboard_label_fields_are_denied_outright():
    # settings.frameName1/frameName2 held two people's first names on one
    # site. Neither value matches any personal shape; the field name rule
    # and the corroboration rule each catch it independently. The value
    # below is invented — a test must not reproduce what it protects.
    stat = census.FieldStat()
    for site in ("a", "b", "c"):
        stat.observe("settings.frameName1", "A-Persons-Name", site, "s")
    out = stat.to_dict("settings.frameName1", 3, {"a": 1, "b": 1, "c": 1})
    assert out["string"]["distinct_values"] is None
    assert "identifying field name" in out["string"]["value_note"]


def test_a_value_written_by_several_sites_is_recorded():
    stat = census.FieldStat()
    for site in ("a", "b", "c", "d"):
        stat.observe("direction", "Flat", site, "s")
    out = stat.to_dict("direction", 4, {"a": 1, "b": 1, "c": 1, "d": 1})
    assert out["string"]["distinct_values"] == ["Flat"]


def test_corroboration_keeps_shared_values_and_drops_private_ones():
    stat = census.FieldStat()
    for site in ("a", "b", "c"):
        stat.observe("units", "mg/dl", site, "s")
    stat.observe("units", "a-private-value", "a", "s")
    out = stat.to_dict("units", 4, {"a": 2, "b": 1, "c": 1})
    assert out["string"]["distinct_values"] == ["mg/dl"]
    assert "1 value(s) withheld" in out["string"]["value_note"]


# ── walking ─────────────────────────────────────────────────────────────

def _walk_paths(doc, map_paths=frozenset()):
    seen = []
    census._walk(doc, "", map_paths, lambda p, v: seen.append(p))
    return seen


def test_walk_uses_bracket_notation_for_arrays():
    paths = _walk_paths({"a": [{"b": 1}, {"b": 2}]})
    assert paths.count("a[].b") == 2
    assert "a[]" in paths


def test_walk_collapses_map_keyed_objects():
    doc = {"store": {"Default": {"dia": 5}, "Weekend": {"dia": 6}}}
    paths = set(_walk_paths(doc, map_paths={"store"}))
    assert "store.{}.dia" in paths
    assert "store.Default.dia" not in paths


def test_map_detection_flags_user_keyed_objects_not_wide_records():
    # A wide record: many keys, all present on every occurrence.
    wide = {"suggested": {f"k{i}": i for i in range(40)}}
    # A user-keyed map: few keys per document, many distinct across documents.
    class FakeSource:
        def __init__(self, docs):
            self.docs = docs
    docs = [wide] + [{"store": {f"profile-{i}": {"dia": 5}}} for i in range(40)]

    monkey = census.corpus.iter_documents
    census.corpus.iter_documents = lambda path: iter(docs)
    try:
        maps, detected = census.detect_map_paths([type("S", (), {"path": "x"})()])
    finally:
        census.corpus.iter_documents = monkey
    assert "store" in maps
    assert "suggested" not in detected


def test_integer_and_float_are_distinct_json_types():
    stat = census.FieldStat()
    stat.observe("date", 1743465600000, "a", "s")
    stat.observe("date", 1743465600000.25, "a", "s")
    out = stat.to_dict("date", 2, {"a": 2})
    assert out["types"] == {"integer": 1, "number": 1}


def test_booleans_are_not_counted_as_integers():
    stat = census.FieldStat()
    stat.observe("automatic", True, "a", "s")
    out = stat.to_dict("automatic", 1, {"a": 1})
    assert out["types"] == {"boolean": 1}
    assert "numeric" not in out


# ── document iteration ──────────────────────────────────────────────────

def test_iter_documents_reads_an_array(tmp_path):
    p = tmp_path / "x.json"
    p.write_text('[{"a":1},\n {"a":2}, {"a":3}]')
    assert [d["a"] for d in corpus.iter_documents(p)] == [1, 2, 3]


def test_iter_documents_reads_a_bare_object(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text('{"units":"mg/dl"}')
    assert [d["units"] for d in corpus.iter_documents(p)] == ["mg/dl"]


def test_iter_documents_handles_an_empty_array(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("[]")
    assert list(corpus.iter_documents(p)) == []


# ── tiering ─────────────────────────────────────────────────────────────

def _field(**kw):
    base = {"site_count": 1, "doc_frequency": 0.5, "docs_present": 1000,
            "site_frequency": {"a": 0.5}}
    base.update(kw)
    return base


def test_universal_requires_every_site():
    f = _field(site_count=11, doc_frequency=1.0, site_frequency={c: 1.0 for c in "abcdefghijk"})
    assert tiers.classify(f, 11)[0] == "universal"
    assert tiers.classify(_field(site_count=10, doc_frequency=1.0), 11)[0] != "universal"


def test_one_busy_site_does_not_make_a_field_core():
    f = _field(site_count=1, doc_frequency=0.9, site_frequency={"b": 0.9})
    assert tiers.classify(f, 11)[0] == "vendor"


def test_rare_wins_over_everything():
    f = _field(site_count=11, doc_frequency=1.0, docs_present=3)
    assert tiers.classify(f, 11)[0] == "rare"


# ── spec loading and reconciliation ─────────────────────────────────────

def test_declared_number_accepts_observed_integer():
    assert diff._covers(["number"], "integer")


def test_declared_integer_rejects_observed_number():
    assert not diff._covers(["integer"], "number")


def test_declared_type_never_accepts_null_implicitly():
    assert not diff._covers(["number"], "null")


def test_untyped_node_accepts_anything():
    assert diff._covers([], "string")


@pytest.mark.parametrize("collection", sorted(specload.ROOT_SCHEMA))
def test_every_spec_flattens(collection):
    root = corpus.repo_root()
    _, name, flat = specload.load(root, collection)
    assert flat, f"{collection} ({name}) flattened to nothing"
    assert all(isinstance(i["types"], list) for i in flat.values())


def test_profile_store_flattens_to_map_notation():
    _, _, flat = specload.load(corpus.repo_root(), "profile")
    assert "store.{}.basal[].value" in flat


def test_reconcile_reports_a_type_conflict():
    cen = {
        "documents": 10, "sites": ["a"],
        "fields": [{
            "path": "date", "count": 10, "docs_present": 10, "doc_frequency": 1.0,
            "sites": ["a"], "site_count": 1, "site_frequency": {"a": 1.0},
            "types": {"number": 10}, "tier": "universal", "tier_reason": "",
        }],
    }
    flat = {"date": {"path": "date", "types": ["integer"], "required": False,
                     "enum": None, "minimum": None, "maximum": None,
                     "format": None, "description": "", "schema_name": None,
                     "additional_properties": None}}
    out = diff.reconcile(cen, flat, "entries")
    assert out["summary"]["type_conflicts"] == 1
    assert out["type_conflicts"][0]["uncovered_values"] == 10


def test_v3_metadata_absence_is_reported_separately():
    cen = {"documents": 1, "sites": ["a"], "fields": []}
    flat = {p: {"path": p, "types": ["string"], "required": False, "enum": None,
                "minimum": None, "maximum": None, "format": None,
                "description": "", "schema_name": None, "additional_properties": None}
            for p in ("identifier", "somethingElse")}
    out = diff.reconcile(cen, flat, "entries")
    assert out["summary"]["v3_metadata_absent"] == 1
    assert out["summary"]["unobserved"] == 1


# ── model ───────────────────────────────────────────────────────────────

from nsschema import model as nsmodel  # noqa: E402
from nsschema.emit import (  # noqa: E402
    jsonschema_emit, mongoose_emit, pyarrow_emit, zod_emit,
)


def test_tokenize_separates_array_and_map_structure():
    assert nsmodel.tokenize("store.{}.basal[].value") == [
        "store", "{}", "basal", "[]", "value"]
    assert nsmodel.tokenize("a[][]") == ["a", "[]", "[]"]


def _census(fields, sites=("a",), documents=100):
    return {"documents": documents, "sites": list(sites), "fields": fields}


def _cfield(path, types, **kw):
    base = {"path": path, "count": 100, "docs_present": 100, "doc_frequency": 1.0,
            "sites": ["a"], "site_count": 1, "site_frequency": {"a": 1.0},
            "types": types, "tier": "universal", "tier_reason": ""}
    base.update(kw)
    return base


def _decl(types, **kw):
    base = {"types": types, "required": False, "enum": None, "minimum": None,
            "maximum": None, "format": None, "description": "",
            "schema_name": None, "additional_properties": None}
    base.update(kw)
    return base


def test_model_widens_integer_to_number_when_data_is_fractional():
    tree = nsmodel.build(
        _census([_cfield("date", {"integer": 10, "number": 90})]),
        {"date": _decl(["integer"])}, "entries")
    node = tree.children["date"]
    assert node.types == ["number"]
    assert any("widened integer" in n for n in node.notes)


def test_model_does_not_invent_an_enum_from_observation():
    # loop.version has few distinct values in one corpus; that does not make
    # the set closed.
    tree = nsmodel.build(
        _census([_cfield("version", {"string": 100},
                         string={"distinct_values": ["3.2.3", "3.6.4"]})]),
        {}, "devicestatus")
    node = tree.children["version"]
    assert node.enum is None
    assert node.observed_values == ["3.2.3", "3.6.4"]


def test_model_extends_a_declared_enum_with_observed_values():
    tree = nsmodel.build(
        _census([_cfield("direction", {"string": 100},
                         string={"distinct_values": ["Flat", "NONE"]})]),
        {"direction": _decl(["string"], enum=["Flat"])}, "entries")
    node = tree.children["direction"]
    assert node.enum == ["Flat", "NONE"]
    assert any("enum extended" in n for n in node.notes)


def test_model_marks_nullable_from_observed_nulls():
    tree = nsmodel.build(
        _census([_cfield("carbs", {"number": 4, "null": 96})]),
        {"carbs": _decl(["number"])}, "treatments")
    assert tree.children["carbs"].nullable


def test_server_assigned_fields_are_required_on_read_only():
    tree = nsmodel.build(
        _census([_cfield("_id", {"string": 100})]),
        {"_id": _decl(["string"])}, "entries")
    node = tree.children["_id"]
    assert node.required_read and not node.required_write


def test_a_write_requirement_is_not_invented_from_evidence():
    # Universal in a Loop-dominant corpus is not grounds for rejecting
    # another client's write.
    tree = nsmodel.build(
        _census([_cfield("sysTime", {"string": 100})]),
        {"sysTime": _decl(["string"], required=False)}, "entries")
    node = tree.children["sysTime"]
    assert node.required_read
    assert not node.required_write
    assert node.candidate_required_write


def test_a_declared_write_requirement_survives():
    tree = nsmodel.build(
        _census([_cfield("date", {"integer": 100})]),
        {"date": _decl(["integer"], required=True)}, "entries")
    assert tree.children["date"].required_write


def test_weak_evidence_is_placed_in_the_extension_bag():
    field = _cfield("glucose", {"integer": 50}, site_count=1, doc_frequency=0.06,
                    site_frequency={"b": 0.86}, tier="vendor")
    tree = nsmodel.build(_census([field], sites="abcdefghijk"), {}, "entries")
    assert tree.children["glucose"].placement == "extension"


# ── emitters ────────────────────────────────────────────────────────────

def _model_doc(tree):
    return {"collection": "entries", "source_spec": "x.yaml", "census": "y.json",
            "root": nsmodel.to_dict(tree)}


def _fractional_date_model():
    return _model_doc(nsmodel.build(
        _census([_cfield("date", {"integer": 10, "number": 90}),
                 _cfield("vendorish", {"string": 5}, site_count=1,
                         doc_frequency=0.05, site_frequency={"b": 0.9},
                         tier="vendor")],
                sites="abcdefghijk"),
        {"date": _decl(["integer"], required=True)}, "entries"))


@pytest.mark.parametrize("strictness", jsonschema_emit.STRICTNESS)
def test_jsonschema_emits_every_strictness(strictness):
    schema = jsonschema_emit.emit(_fractional_date_model(), "write", strictness)
    assert schema["$schema"] == jsonschema_emit.DIALECT
    assert schema["properties"]["date"]["type"] == "number"


def test_permissive_allows_unknown_fields_and_strict_does_not():
    m = _fractional_date_model()
    assert jsonschema_emit.emit(m, "write", "permissive")["additionalProperties"] is True
    assert jsonschema_emit.emit(m, "write", "strict")["additionalProperties"] is False


def test_strict_drops_undeclared_fields_entirely():
    schema = jsonschema_emit.emit(_fractional_date_model(), "write", "strict")
    assert "vendorish" not in schema["properties"]


def test_extension_bag_relocates_weak_fields():
    schema = jsonschema_emit.emit(_fractional_date_model(), "write", "extension-bag")
    assert "vendorish" not in schema["properties"]
    assert "vendorish" in schema["properties"][jsonschema_emit.EXTENSION_KEY]["properties"]


def test_tolerant_keeps_weak_fields_where_clients_write_them():
    schema = jsonschema_emit.emit(_fractional_date_model(), "write", "tolerant")
    assert "vendorish" in schema["properties"]
    assert schema["additionalProperties"] is False


def test_generated_schemas_compile_as_json():
    schema = jsonschema_emit.emit(_fractional_date_model(), "read", "tolerant")
    json.loads(json.dumps(schema))


def test_zod_marks_nullable_fields_nullable():
    m = _model_doc(nsmodel.build(
        _census([_cfield("carbs", {"number": 4, "null": 96})]),
        {"carbs": _decl(["number"])}, "treatments"))
    out = zod_emit.emit(m)
    assert "carbs: z.number().nullable().optional()" in out


def test_mongoose_does_not_cast_a_type_union():
    m = _model_doc(nsmodel.build(
        _census([_cfield("mills", {"string": 200, "integer": 2})]), {}, "profile"))
    out = mongoose_emit.emit(m)
    assert "Schema.Types.Mixed" in out


def test_pyarrow_widens_a_union_rather_than_truncating():
    tree = nsmodel.build(
        _census([_cfield("mills", {"string": 200, "integer": 2})]), {}, "profile")
    arrow, note = pyarrow_emit.arrow_type(nsmodel.to_dict(tree.children["mills"]))
    assert arrow == "pa.large_string()"
    assert "widened" in note


def test_pyarrow_maps_a_user_keyed_object_to_an_arrow_map():
    tree = nsmodel.build(
        _census([_cfield("store", {"object": 100}),
                 _cfield("store.{}", {"object": 100}),
                 _cfield("store.{}.dia", {"number": 100})]), {}, "profile")
    arrow, _ = pyarrow_emit.arrow_type(nsmodel.to_dict(tree.children["store"]))
    assert arrow.startswith("pa.map_(pa.large_string()")


# ── value-shape redaction ───────────────────────────────────────────────

@pytest.mark.parametrize("value", [
    "2026-03-29T17:18:36.569Z",       # exact moment a profile was edited
    "<n>-03-29T17:18:36.569Z",        # the same, after digit masking
    "00:00", "22:30",                 # a person's insulin schedule
    "com.ZZRU3JT3YW.loopkit.Loop",    # an Apple Developer Team ID
    "org.turing.loop83.Loop",
    "Japan", "Etc/GMT+4",             # location
    "\U0001F680",                     # a user's own override-preset emoji
])
def test_personal_value_shapes_are_rejected(value):
    assert redact.is_personal_shape(value), value


@pytest.mark.parametrize("value", [
    "3.12.0.2", "0.6.0",              # version numbers, not bundle ids
    "loop://iPhone", "Sony SO-53B",   # device vocabulary
    "mg/dL", "mmol/L",                # the units finding depends on these
    "Flat", "Temp Basal", "absolute", "Insulet", "Comms Issue",
])
def test_vocabulary_values_survive(value):
    assert not redact.is_personal_shape(value), value


def test_a_personal_shaped_value_withholds_the_whole_field():
    stat = census.FieldStat()
    stat.observe("created_at", "2026-03-29T17:18:36.569Z", "a", "s")
    stat.observe("created_at", "2026-03-29T17:18:36.569Z", "b", "s")
    stat.observe("created_at", "2026-03-29T17:18:36.569Z", "c", "s")
    out = stat.to_dict("created_at", 1, {"a": 1})
    assert out["string"]["distinct_values"] is None
    assert "personal-shaped" in out["string"]["value_note"]


def test_small_sample_numeric_ranges_are_withheld():
    stat = census.FieldStat()
    stat.observe("mills", 1774199071000, "a", "s")
    out = stat.to_dict("mills", 1, {"a": 1})
    assert "min" not in out["numeric"]
    assert "withheld" in out["numeric"]["range_note"]


def test_large_sample_numeric_ranges_are_reported():
    stat = census.FieldStat()
    for i in range(census.MIN_NUMERIC_SAMPLES):
        stat.observe("sgv", 100 + i, "a", "s")
    out = stat.to_dict("sgv", 1, {"a": 1})
    assert out["numeric"]["min"] == 100


@pytest.mark.parametrize("path", [
    "extendedSettings.loop.apnsDeveloperTeamId",   # an Apple Developer Team ID
    "loopSettings.bundleIdentifier",
    "transmitterId", "sensorId", "pump.pumpID",
    "settings.frameName1", "settings.customTitle",
    "settings.baseURL", "uploader.name",
])
def test_identity_shaped_field_names_are_denied_by_suffix(path):
    assert redact.is_denied(path), path


@pytest.mark.parametrize("path", [
    "direction", "eventType", "type", "units", "insulinType",
    "pump.manufacturer", "pump.model", "temp", "runtimeState",
    "loopSettings.dosingStrategy",
])
def test_vocabulary_field_names_survive_the_suffix_rule(path):
    assert not redact.is_denied(path), path


def test_a_declared_enum_is_not_enforced_when_values_were_withheld():
    # The privacy rule can hide observed values. An enum we know to be
    # incomplete rejects real documents, so it must not be emitted.
    tree = nsmodel.build(
        _census([_cfield("eventType", {"string": 100},
                         string={"distinct_values": ["Meal Bolus"],
                                 "distinct_value_count": 14,
                                 "values_withheld": 8})]),
        {"eventType": _decl(["string"], enum=["Meal Bolus"])}, "treatments")
    node = tree.children["eventType"]
    assert node.enum is None
    assert any("not enforced" in n for n in node.notes)


def test_a_declared_enum_is_enforced_when_nothing_was_withheld():
    tree = nsmodel.build(
        _census([_cfield("type", {"string": 100},
                         string={"distinct_values": ["sgv"],
                                 "distinct_value_count": 1})]),
        {"type": _decl(["string"], enum=["sgv", "mbg"])}, "entries")
    assert tree.children["type"].enum == ["mbg", "sgv"]


# ── scanning committed files ────────────────────────────────────────────

from nsschema import scan_pii  # noqa: E402


def test_scanner_grades_a_credential_above_an_identifier():
    assert scan_pii.categorize("loopSettings.deviceToken", "abc") == "credential"
    assert scan_pii.categorize("extendedSettings.loop.apnsDeveloperTeamId",
                               "ABCDEFGHIJ") == "credential"
    assert scan_pii.categorize("profile[]._id", "69c85c022b390b80") == "identity"


def test_scanner_flags_an_opaque_token_under_a_neutral_name():
    assert scan_pii.categorize("payload", "0" * 64) == "credential"


def test_scanner_grades_a_timezone_as_a_quasi_identifier():
    assert scan_pii.categorize("theme", "Europe/Belgrade") == "quasi-identifier"


def test_scanner_does_not_flag_ecosystem_vocabulary():
    # Without this, every `enteredBy: "Loop"` is a finding and the real ones
    # are lost in the noise.
    assert scan_pii.categorize("[].enteredBy", "Loop") is None
    assert scan_pii.categorize("[].defaultProfile", "Default") is None


def test_scanner_passes_ordinary_vocabulary():
    for path, value in (("eventType", "Temp Basal"), ("units", "mg/dl"),
                        ("direction", "Flat"), ("manufacturer", "Insulet")):
        assert scan_pii.categorize(path, value) is None, (path, value)


def test_scanner_reports_paths_but_never_values(tmp_path):
    secret = "a-value-that-must-not-be-echoed"
    doc = tmp_path / "f.json"
    doc.write_text(json.dumps([{"deviceToken": secret}]))
    findings, error = scan_pii.scan_file(doc)
    assert error is None
    assert ("[].deviceToken", "credential") in findings
    # The scanner's own report must not become a second copy of the leak.
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        scan_pii.main([str(doc), "--count"])
    assert secret not in buf.getvalue()


# ── sanitizing committed files ──────────────────────────────────────────

from nsschema import sanitize  # noqa: E402


def test_rule_matching_covers_digit_suffixed_names():
    assert sanitize.rule_for("settings.frameName1") == "label"
    assert sanitize.rule_for("settings.frameUrl8") == "url"


def test_credential_replacement_preserves_length_and_alphabet():
    m = sanitize.Masker()
    token = "150b7fba0285a0d1cad422ec9eef38518b62539f7217"
    out = m.credential(token)
    assert len(out) == len(token)
    assert out != token
    assert all(c in "0123456789abcdef" for c in out)


def test_masking_is_deterministic_so_joins_survive():
    a, b = sanitize.Masker(), sanitize.Masker()
    oid = "69c85c022b390b801650a69a"
    assert a.opaque_id(oid) == b.opaque_id(oid)


def test_objectid_shape_is_preserved():
    out = sanitize.Masker().opaque_id("69c85c022b390b801650a69a")
    assert len(out) == 24 and all(c in "0123456789abcdef" for c in out)


def test_uuid_shape_is_preserved():
    out = sanitize.Masker().opaque_id("535D272E-B815-4893-BDB4-5F62FBE1B10C")
    assert re.match(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
                    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$", out)


@pytest.mark.parametrize("value,expected", [
    ("com.ZZRU3JT3YW.loopkit.Loop", "com.example.Loop"),
    # Trio's format puts the Team ID third; an earlier rule kept it.
    ("org.nightscout.GSLNR9RJSR.trio", "com.example.trio"),
    # A personal build namespace is identifying even without a Team ID.
    ("org.turing.loop83.Loop", "com.example.Loop"),
])
def test_bundle_identifier_keeps_only_the_app_name(value, expected):
    assert sanitize.Masker().bundle_id(value) == expected


def test_a_treatment_note_is_masked_but_an_algorithm_reason_is_not():
    # A real note read: "Failed to enact bolus. Details: User: <a name>."
    assert sanitize.rule_for("[].notes") == "label"
    assert sanitize.rule_for("[].reason") == "label"
    assert sanitize.rule_for("[].openaps.suggested.reason") is None


def test_low_entropy_values_use_counters_not_hashes():
    # A person's override name is guessable from a hash; a counter is not.
    m = sanitize.Masker()
    assert m.label("Cardio") == "Label 1"
    assert m.label("Weights") == "Label 2"
    assert m.label("Cardio") == "Label 1"


def test_client_vocabulary_survives_but_a_rig_name_does_not():
    m = sanitize.Masker()
    assert m.entered_by("Loop") == "Loop"
    assert m.entered_by("loop://iPhone") == "loop://iPhone"
    assert m.entered_by("xDrip4iOS") == "xDrip4iOS"
    assert m.entered_by("OZQT18").startswith("uploader-")


def test_therapy_values_and_timestamps_are_left_alone():
    doc = {"store": {"Default": {"basal": [{"time": "05:00", "value": 0.85}]},
                     "timezone": "Japan"},
           "created_at": "2026-03-29T17:18:36.569Z", "sgv": 142}
    assert sanitize.transform(doc, sanitize.Masker()) == doc


def test_lockfile_and_schema_urls_are_not_masked():
    # A blanket "any http(s) value" rule rewrote workspace.lock.json clone
    # URLs and JSON Schema $id keywords. Those are load-bearing, not personal.
    doc = {"$schema": "https://json-schema.org/draft/2020-12/schema",
           "repos": [{"url": "https://github.com/nightscout/Trio.git"}]}
    assert sanitize.transform(doc, sanitize.Masker()) == doc


def test_a_dashboard_frame_url_is_masked():
    doc = {"settings": {"frameUrl1": "https://a-personal-site.example/x"}}
    out = sanitize.transform(doc, sanitize.Masker())
    assert out["settings"]["frameUrl1"] == "https://example.invalid/frame"


def test_sanitizing_removes_what_the_scanner_flags(tmp_path):
    doc = [{"_id": "69c85c022b390b801650a69a",
            "loopSettings": {"deviceToken": "0145ce85934cdae539b64e7aedcd08ea",
                             "bundleIdentifier": "com.ZZRU3JT3YW.loopkit.Loop",
                             "overridePresets": [{"name": "Cardio", "symbol": "X"}]}}]
    p = tmp_path / "f.json"
    p.write_text(json.dumps(doc))
    sanitize.sanitize_file(p, write=True)
    after = json.loads(p.read_text())
    settings = after[0]["loopSettings"]
    assert settings["deviceToken"] != doc[0]["loopSettings"]["deviceToken"]
    assert "ZZRU3JT3YW" not in json.dumps(after)
    assert settings["overridePresets"][0]["name"] == "Label 1"


@pytest.mark.parametrize("value,expected", [
    ("Dexcom G7 DXCM3Y", "Dexcom G7"),      # transmitter serial appended
    ("Dexcom G6", "Dexcom G6"),             # model tokens are too short
    ("share2", "share2"),
    ("loop://iPhone", "loop://iPhone"),
    ("com.dexcom.g7app", "com.dexcom.g7app"),
    ("openaps://AAPS", "openaps://AAPS"),
])
def test_device_strings_keep_the_model_and_lose_the_serial(value, expected):
    assert sanitize.Masker().device_string(value) == expected


def test_a_conformance_test_name_is_not_treated_as_an_identifier():
    # Vectors name their cases COB-001, IOB-003, LV-175-2026-02-03. Masking
    # those destroys the vector's readability and protects nobody.
    m = sanitize.Masker()
    for name in ("COB-001", "IOB-003", "LV-175-2026-02-03", "odc-1611964958000"):
        assert m.opaque_id(name) == name


def test_machine_identifiers_are_still_masked():
    m = sanitize.Masker()
    for value in ("69c85c022b390b801650a69a",
                  "535D272E-B815-4893-BDB4-5F62FBE1B10C",
                  "0145ce85934cdae539b64e7aedcd08eaf54f0b92f9ff"):
        assert m.opaque_id(value) != value


def test_expected_outputs_in_conformance_vectors_are_left_alone():
    # `reason` under an expected/comparison block is the value a test
    # asserts on, not a person's words.
    assert sanitize.rule_for("testCases[].expected.reason") is None
    assert sanitize.rule_for("files[].testResults[].comparison.reason") is None
    assert sanitize.rule_for("test_cases[].notes") is None
    # ...but a treatment's own note still is.
    assert sanitize.rule_for("treatments[].notes") == "label"


def test_a_devicestatus_override_name_is_masked():
    # Found by reviewing the baseline: `[].override.name` held a real
    # user-chosen override name that earlier rules missed.
    assert sanitize.rule_for("[].override.name") == "label"


@pytest.mark.parametrize("value", ["175F78A9", "208850", "17AA00C5"])
def test_short_hardware_serials_are_masked_despite_the_shape_guard(value):
    # Found by reviewing the baseline: pump serials are shorter than the
    # opaque-id shape guard's threshold, so they need their own rule.
    out = sanitize.Masker().serial(value)
    assert out != value
    assert len(out) == len(value)


def test_serial_fields_use_the_serial_rule():
    for path in ("[].pump.pumpID", "[].pumpSerial", "[].transmitterId"):
        assert sanitize.rule_for(path) == "serial"


# ── quirks registry ─────────────────────────────────────────────────────

from nsschema import quirks as quirks_mod  # noqa: E402


def test_resolve_walks_arrays_and_maps():
    doc = {"store": {"Default": {"basal": [{"value": 1.0}, {"value": 2.0}]},
                     "Weekend": {"basal": [{"value": 3.0}]}}}
    assert sorted(quirks_mod.resolve(doc, "store.{}.basal[].value")) == [1.0, 2.0, 3.0]


def test_resolve_returns_nothing_for_a_missing_path():
    assert quirks_mod.resolve({"a": 1}, "b.c") == []


def test_is_fractional_distinguishes_a_whole_float():
    detect = {"path": "date", "test": "is-fractional"}
    assert quirks_mod.evaluate(detect, {"date": 1743465600000.25})
    assert not quirks_mod.evaluate(detect, {"date": 1743465600000.0})
    assert not quirks_mod.evaluate(detect, {"date": 1743465600000})


def test_is_null_is_not_the_same_as_absent():
    assert quirks_mod.evaluate({"path": "carbs", "test": "is-null"}, {"carbs": None})
    assert not quirks_mod.evaluate({"path": "carbs", "test": "is-null"}, {})
    assert quirks_mod.evaluate({"path": "carbs", "test": "absent"}, {})
    assert not quirks_mod.evaluate({"path": "carbs", "test": "absent"}, {"carbs": None})


def test_exists_fires_on_a_null_value():
    # A key written as null is present on the wire, which is the whole point
    # of QUIRK-TREATMENTS-001.
    assert quirks_mod.evaluate({"path": "carbs", "test": "exists"}, {"carbs": None})


def test_equals_matches_the_deadbeef_sentinel():
    detect = {"path": "reservoir", "test": "equals", "value": 3735928559}
    assert quirks_mod.evaluate(detect, {"reservoir": 3735928559})
    assert not quirks_mod.evaluate(detect, {"reservoir": 42.5})


def test_in_matches_any_listed_value():
    detect = {"path": "eventType", "test": "in", "values": ["Bolus", "Carbs"]}
    assert quirks_mod.evaluate(detect, {"eventType": "Carbs"})
    assert not quirks_mod.evaluate(detect, {"eventType": "Meal Bolus"})


def test_registry_loads_and_every_detector_is_known():
    registry = quirks_mod.load_registry(corpus.repo_root() / "specs" / "quirks")
    assert registry
    for quirk in registry:
        assert quirk["detect"]["test"] in quirks_mod.TESTS
        for required in ("id", "title", "status", "kind", "path",
                         "reader_guidance", "references"):
            assert quirk.get(required), f"{quirk['id']} missing {required}"


def test_registry_ids_are_unique():
    registry = quirks_mod.load_registry(corpus.repo_root() / "specs" / "quirks")
    ids = [q["id"] for q in registry]
    assert len(ids) == len(set(ids))


def test_an_unknown_detector_is_rejected_at_load(tmp_path):
    (tmp_path / "x.yaml").write_text(
        "collection: entries\nquirks:\n  - id: Q\n    title: t\n    status: active\n"
        "    path: p\n    kind: type-union\n    detect: {path: p, test: nonsense}\n")
    with pytest.raises(ValueError, match="unknown test"):
        quirks_mod.load_registry(tmp_path)


def test_check_fails_a_quirk_that_vanished():
    rows = [{"id": "Q-1", "status": "active", "documents": 0, "share": 0.0,
             "sites": 0, "expect": {"min_share": 0.5}}]
    assert quirks_mod.check(rows) == [("Q-1", "no longer observed in the corpus")]


def test_check_fails_a_collapsed_share():
    rows = [{"id": "Q-1", "status": "active", "documents": 5, "share": 0.01,
             "sites": 9, "expect": {"min_share": 0.5, "min_sites": 8}}]
    failures = quirks_mod.check(rows)
    assert len(failures) == 1 and "below claimed minimum" in failures[0][1]


def test_check_ignores_a_historical_quirk():
    rows = [{"id": "Q-1", "status": "historical", "documents": 0, "share": 0.0,
             "sites": 0, "expect": {"min_share": 0.5}}]
    assert quirks_mod.check(rows) == []


# ── granular-primitive decomposition ────────────────────────────────────

from nsschema import decompose  # noqa: E402


@pytest.mark.parametrize("event,branch", [
    ("Temp Basal", "temp-basal"),
    ("TempBasal", "temp-basal"),
    ("temp basal start", "temp-basal"),       # comparison is case-insensitive
    ("Meal Bolus", "meal-bolus"),
    ("Snack Bolus", "meal-bolus"),
    ("SMB", "correction-bolus"),
    ("Correction Bolus", "correction-bolus"),
    ("Bolus", "plain-bolus"),
    ("Carb Correction", "carb-correction"),
    ("BG Check", "bg-check"),
    ("Site Change", "device-event"),
    ("Profile Switch", "profile-switch"),
    ("Temporary Override", "override"),
    ("Exercise", "note"),
])
def test_treatments_route_to_their_primitive(event, branch):
    assert decompose.classify({"eventType": event})[0] == branch


def test_an_unknown_event_type_falls_back_to_the_data():
    branch, reason = decompose.classify({"eventType": "Something New", "insulin": 1.5})
    assert branch == "data-fallback" and "insulin" in reason


def test_a_null_valued_field_is_not_data():
    # carbs and insulin are present-but-null on most treatments
    # (QUIRK-TREATMENTS-001); treating presence as data would route
    # everything to the fallback branch.
    branch, _ = decompose.classify({"eventType": "Something New",
                                    "insulin": None, "carbs": None})
    assert branch == "unroutable"


def test_a_zero_dose_is_not_data():
    branch, _ = decompose.classify({"eventType": "Something New",
                                    "insulin": 0, "carbs": 0})
    assert branch == "unroutable"


def test_a_boolean_is_not_a_number():
    assert not decompose._number(True)
    assert decompose._number(1.5)


def test_suspend_pump_is_unroutable_which_is_the_finding():
    # Nightscout's documented eventType, and the only spelling in the
    # corpus, is "Suspend Pump". Nocturne's V4 decomposition routes through
    # TreatmentTypes.PumpSuspend = "Pump Suspend" — the reversed word order
    # — so it skips these, while the rest of that codebase recognises them.
    assert decompose.classify({"eventType": "Suspend Pump"})[0] == "unroutable"
    assert decompose.classify({"eventType": "Pump Suspend"})[0] == "device-event"


def test_every_branch_declares_what_it_produces():
    for branch in decompose.BRANCHES:
        assert branch in decompose.BRANCHES
    assert decompose.BRANCHES["unroutable"] == []
    assert decompose.BRANCHES["meal-bolus"] == ["Bolus", "CarbIntake"]


# ── Nocturne model coverage ─────────────────────────────────────────────

from nsschema import nocturne_model  # noqa: E402

_NOCTURNE = corpus.repo_root() / nocturne_model.MODELS_DIR
_HAS_NOCTURNE = _NOCTURNE.is_dir()
_skip_nocturne = pytest.mark.skipif(not _HAS_NOCTURNE,
                                    reason="externals/nocturne not checked out")


@pytest.fixture(scope="module")
def nocturne_classes():
    return nocturne_model.parse_models(_NOCTURNE)


@_skip_nocturne
@pytest.mark.parametrize("cls,prop", [
    # Expression-bodied properties: an earlier regex required `{ get;` and
    # reported all of these as undeclared.
    ("Entry", "date"), ("Entry", "dateString"), ("Profile", "srvModified"),
    # Plain auto-properties.
    ("PumpStatus", "reservoir"), ("UploaderStatus", "battery"),
    ("Profile", "loopSettings"),
])
def test_parser_finds_properties_that_exist(nocturne_classes, cls, prop):
    assert prop in nocturne_classes[cls]["props"], f"{cls}.{prop}"


@_skip_nocturne
@pytest.mark.parametrize("cls,prop", [
    # The corpus's majority flat pump shape; Nocturne declares only the
    # nested `pump.status.*` form.
    ("PumpStatus", "bolusing"), ("PumpStatus", "suspended"),
    ("PumpStatus", "pumpID"), ("PumpStatus", "secondsFromGMT"),
    ("UploaderStatus", "timestamp"),
])
def test_parser_reports_properties_that_really_are_missing(nocturne_classes, cls, prop):
    assert prop not in nocturne_classes[cls]["props"], f"{cls}.{prop}"


@_skip_nocturne
def test_only_the_top_level_document_keeps_unknown_keys(nocturne_classes):
    # This is why a nested vendor field is dropped rather than captured:
    # [JsonExtensionData] is on DeviceStatus, not on PumpStatus.
    assert nocturne_classes["DeviceStatus"]["extension"]
    for nested in ("PumpStatus", "UploaderStatus", "LoopStatus", "PumpBattery"):
        assert not nocturne_classes[nested]["extension"], nested


@_skip_nocturne
def test_resolution_verdicts(nocturne_classes):
    resolve = nocturne_model.resolve
    assert resolve(nocturne_classes, "Entry", "sgv")[0] == "retained"
    assert resolve(nocturne_classes, "DeviceStatus", "pump.reservoir")[0] == "retained"
    assert resolve(nocturne_classes, "DeviceStatus", "pump.bolusing")[0] == "dropped"
    # Treatment carries [JsonExtensionData], so an unknown key survives.
    assert resolve(nocturne_classes, "Treatment", "somethingNobodyDeclared")[0] == "captured"


def test_element_type_unwraps_collections():
    assert nocturne_model._element_type("List<TimeValue>") == "TimeValue"
    assert nocturne_model._element_type("Dictionary<string, ProfileData>") == "ProfileData"
    assert nocturne_model._element_type("double") is None


# ── dosing-input recoverability ─────────────────────────────────────────

from nsschema import dosing_inputs  # noqa: E402


def test_dosing_input_map_loads_and_is_well_formed():
    mapping = yaml.safe_load(
        (corpus.repo_root() / dosing_inputs.MAP).read_text())
    assert mapping["inputs"]
    for entry in mapping["inputs"]:
        assert entry["kind"] in dosing_inputs.KIND_ORDER, entry["input"]
        assert entry.get("confidence") in ("high", "medium", "low"), entry["input"]
        if entry["kind"] in ("recorded", "partial"):
            assert entry.get("sources"), f"{entry['input']} claims a source"
        if entry["kind"] == "absent":
            assert not entry.get("sources"), f"{entry['input']} claims absent"


def test_check_flags_a_source_that_does_not_exist():
    mapping = {"inputs": [{"input": "x", "kind": "recorded",
                           "collection": "devicestatus",
                           "sources": ["nope.not.here"], "confidence": "high"}]}
    rows = dosing_inputs.check(mapping, {"devicestatus": {}})
    assert rows[0]["verdict"] == "claim-unsupported"


def test_check_flags_an_absent_claim_the_data_contradicts():
    mapping = {"inputs": [{"input": "x", "kind": "absent",
                           "collection": "devicestatus",
                           "sources": ["pump.reservoir"], "confidence": "high"}]}
    census = {"devicestatus": {"pump.reservoir": {
        "doc_frequency": 0.5, "site_count": 9}}}
    rows = dosing_inputs.check(mapping, census)
    assert rows[0]["verdict"] == "claim-contradicted"


# ── vendor wire surfaces ────────────────────────────────────────────────

from nsschema import vendor_surface  # noqa: E402


def test_swift_wire_names_come_from_coding_keys():
    # `case tdd = "TDD"` ships as TDD. Reading property names instead
    # reported Trio's tdd as never-written when the corpus carries TDD.
    text = """
    struct Determination: Codable {
        var tdd: Decimal?
        var minGuardBG: Decimal?
        var reasonParts: [String] { parts() }
        private enum CodingKeys: String, CodingKey {
            case tdd = "TDD"
            case minGuardBG
        }
    }
    """
    assert vendor_surface._swift_coding_keys(text) == {"TDD", "minGuardBG"}


def test_computed_properties_are_not_wire_fields():
    # Trio's Determination.swift says in a comment that reasonParts and
    # reasonConclusion are excluded from CodingKeys "so the serialized JSON
    # is unchanged". A surface that lists them is wrong.
    text = """
    struct X: Codable {
        var a: Int
        var b: String { compute() }
        private enum CodingKeys: String, CodingKey { case a }
    }
    """
    assert vendor_surface._swift_coding_keys(text) == {"a"}


def test_a_swift_type_without_coding_keys_falls_back_to_stored_properties(tmp_path):
    src = tmp_path / "externals" / "x" / "Y.swift"
    src.parent.mkdir(parents=True)
    src.write_text("struct Y: Codable {\n    var iob: Double\n"
                   "    var computed: Double { iob * 2 }\n}\n")
    names = vendor_surface.extract(tmp_path, "x/Y.swift", "swift-coding-keys")
    assert names == ["iob"]


def test_extraction_can_stop_before_an_unrelated_model(tmp_path):
    # Trio's NightscoutStatus.swift also defines its *profile* upload models;
    # without a bound, dia and deviceToken look like devicestatus fields.
    src = tmp_path / "externals" / "x" / "Y.swift"
    src.parent.mkdir(parents=True)
    src.write_text("struct Status {\n    let reservoir: Decimal\n}\n"
                   "struct ScheduledNightscoutProfile {\n    let dia: Decimal\n}\n")
    names = vendor_surface.extract(tmp_path, "x/Y.swift", r'^\s*let\s+(\w+)\s*:',
                                   stop_at="struct ScheduledNightscoutProfile")
    assert names == ["reservoir"]


def test_a_missing_source_is_reported_not_guessed(tmp_path):
    assert vendor_surface.extract(tmp_path, "nope/Missing.kt", r'(\w+)') is None


@pytest.mark.parametrize("value,expected", [
    ("Dexcom G7 DXCM3Y", "Dexcom G7"),          # appended serial, stripped
    # Everything else survives. Each of these was masked by an earlier
    # vocabulary rule and each was a false positive: a bridge app, a phone
    # model, and a placeholder in a public research export.
    ("Zukka (LibreLinkUp)", "Zukka (LibreLinkUp)"),
    ("Sony SO-53B", "Sony SO-53B"),
    ("device", "device"),
    ("xDrip-WebFollower", "xDrip-WebFollower"),
    ("xDrip4iOS via Nightscout", "xDrip4iOS via Nightscout"),
    ("loop://iPhone", "loop://iPhone"),
    ("com.dexcom.g7app", "com.dexcom.g7app"),
])
def test_device_strings_keep_everything_but_serials(value, expected):
    assert sanitize.Masker().device_string(value) == expected


def test_a_device_string_is_never_graded_as_identity():
    # It is evidence first. Grading it identity invites masking it.
    assert scan_pii.categorize("[].device", "Zukka (LibreLinkUp)") is None
    assert scan_pii.categorize("[].device", "loop://iPhone") is None


def test_an_unrecognised_device_token_is_raised_for_review_not_masked():
    assert scan_pii.categorize("[].device", "Someones Phone") == "review"
    assert scan_pii._device_tokens_for_review("Zukka (LibreLinkUp)") == []
    assert scan_pii._device_tokens_for_review("Dexcom G7") == []


def test_only_restricts_which_rules_run(monkeypatch):
    # Adding a rule later must not re-mask what earlier passes settled.
    monkeypatch.setattr(sanitize, "_ONLY_RULES", frozenset({"device-string"}))
    doc = {"device": "Dexcom G7 DXCM3Y", "_id": "69c85c022b390b801650a69a"}
    out = sanitize.transform(doc, sanitize.Masker())
    assert out["device"] == "Dexcom G7"
    assert out["_id"] == doc["_id"]


# ── observability profile ───────────────────────────────────────────────

from nsschema import observability  # noqa: E402


def test_observability_profile_loads_and_is_well_formed():
    profile = observability.load_profile(corpus.repo_root())
    assert profile["obligations"] and profile["roles"]
    for obligation in profile["obligations"]:
        for required in ("id", "role", "level", "collection", "path",
                         "test", "title", "rationale"):
            assert obligation.get(required), f"{obligation['id']} missing {required}"


def test_obligation_ids_are_unique():
    profile = observability.load_profile(corpus.repo_root())
    ids = [o["id"] for o in profile["obligations"]]
    assert len(ids) == len(set(ids))


def test_an_unknown_role_is_rejected(tmp_path):
    (tmp_path / "p.yaml").write_text(
        "roles: [{id: r, title: t, detect: {collection: entries, path: p, test: exists}}]\n"
        "obligations: [{id: O, role: nope, level: MUST, collection: entries,\n"
        "  path: p, test: exists, title: t, rationale: r}]\n")
    with pytest.raises(ValueError, match="unknown role"):
        observability.load_profile(tmp_path, "p.yaml")


def test_an_unknown_level_is_rejected(tmp_path):
    (tmp_path / "p.yaml").write_text(
        "roles: [{id: r, title: t, detect: {collection: entries, path: p, test: exists}}]\n"
        "obligations: [{id: O, role: r, level: OUGHT, collection: entries,\n"
        "  path: p, test: exists, title: t, rationale: r}]\n")
    with pytest.raises(ValueError, match="unknown level"):
        observability.load_profile(tmp_path, "p.yaml")


def test_the_controller_role_is_not_detected_by_what_it_is_asked_to_write():
    # Detecting a controller by "it wrote a devicestatus" would make the
    # profile unfalsifiable: a system that uploads nothing would be
    # classified as not-a-controller and therefore conformant.
    profile = observability.load_profile(corpus.repo_root())
    controller = next(r for r in profile["roles"] if r["id"] == "aid-controller")
    detectors = controller["detect_any"]
    assert any(d["collection"] == "treatments" for d in detectors), \
        "the controller role must be detectable from evidence of dosing"


def test_both_algorithm_input_sets_are_present():
    mapping = yaml.safe_load(
        (corpus.repo_root() / dosing_inputs.MAP).read_text())
    algorithms = {e.get("algorithm") for e in mapping["inputs"]}
    assert algorithms == {"oref0", "loop"}, algorithms


def test_loop_inputs_match_the_algorithm_protocol():
    # The Loop set is source-derived from AlgorithmInput.swift. If that
    # protocol gains or loses a member, this map is stale.
    protocol = (corpus.repo_root() / "externals" / "LoopAlgorithm" / "Sources" /
                "LoopAlgorithm" / "AlgorithmInput.swift")
    if not protocol.is_file():
        pytest.skip("externals/LoopAlgorithm not checked out")
    declared = set(re.findall(r'var\s+(\w+)\s*:\s*[^\n]+\{\s*get\s*\}',
                              protocol.read_text()))
    mapping = yaml.safe_load(
        (corpus.repo_root() / dosing_inputs.MAP).read_text())
    mapped = {e["input"] for e in mapping["inputs"]
              if e.get("algorithm") == "loop"}
    missing = declared - mapped
    assert not missing, f"AlgorithmInput members with no source mapping: {sorted(missing)}"


# ── controller state-model registrations ────────────────────────────────

from nsschema import sync_model  # noqa: E402
import jsonschema  # noqa: E402


def test_registration_schema_is_valid():
    schema = json.loads((corpus.repo_root() / sync_model.SCHEMA).read_text())
    jsonschema.Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("key", sorted(sync_model.CONTROLLERS))
def test_generated_registrations_validate(key):
    root = corpus.repo_root()
    schema = json.loads((root / sync_model.SCHEMA).read_text())
    registration = sync_model.build(root, key, sync_model.CONTROLLERS[key])
    checked = {k: v for k, v in registration.items() if not k.startswith("x-")}
    jsonschema.Draft202012Validator(schema).validate(checked)


def test_a_controller_is_discriminated_structurally_not_by_device_string():
    # The device string is free text, is the field most effort went into
    # de-identifying, and is unreliable: one site's device strings read like
    # a controller while its treatments show no automated dosing.
    root = corpus.repo_root()
    for key, spec in sync_model.CONTROLLERS.items():
        registration = sync_model.build(root, key, spec)
        for document in registration["spec"]["documents"]:
            disc = document.get("discriminator")
            if disc:
                assert disc["path"] != "device", key


def test_an_unrecorded_input_is_declared_with_a_null_path():
    # "Declared and unrecorded" has to be expressible, or completeness is
    # a guess. Loop's automaticBolusApplicationFactor is the case.
    root = corpus.repo_root()
    registration = sync_model.build(root, "loop", sync_model.CONTROLLERS["loop"])
    absent = [r for r in registration["spec"]["replayInputs"]
              if r["status"] == "absent"]
    assert absent, "Loop has absent inputs and they must appear"
    assert all(r["path"] is None for r in absent)


def test_completeness_is_reported_not_assumed():
    root = corpus.repo_root()
    stats = sync_model.completeness(
        sync_model.build(root, "loop", sync_model.CONTROLLERS["loop"]))
    assert 0.0 < stats["recorded_share"] < 1.0
    assert stats["replayable_share"] >= stats["recorded_share"]


# ── therapy effects ─────────────────────────────────────────────────────

from nsschema import effects  # noqa: E402


def test_effect_and_motivation_are_classified_separately():
    assert effects.classify(
        {"insulinNeedsScaleFactor": 1.2, "reason": "Cardio"}) == "effect+motivation"
    assert effects.classify({"insulinNeedsScaleFactor": 1.2}) == "effect-only"
    # Trio's Exercise: a label and a duration, and no idea what it did.
    assert effects.classify({"duration": 90, "notes": "run"}) == "motivation-only"
    assert effects.classify({"duration": 90}) == "neither"


def test_an_empty_string_motivation_is_not_a_motivation():
    assert effects.classify({"insulinNeedsScaleFactor": 1.2,
                             "reason": ""}) == "effect-only"


def test_therapy_effect_schema_is_valid_and_effect_only_needs_no_motivation():
    schema = json.loads(
        (corpus.repo_root() / "specs/sync/therapy-effect.schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate({
        "startTimestamp": "2026-09-11T08:00:00Z",
        "effect": {"insulinNeedsScaleFactor": 1.2},
        "disclosure": "effect-only",
    })


def test_a_label_is_not_required_at_any_disclosure_level():
    schema = json.loads(
        (corpus.repo_root() / "specs/sync/therapy-effect.schema.json").read_text())
    motivation = schema["properties"]["motivation"]
    assert "required" not in motivation, "motivation must never require a label"


def test_basal_and_insulin_needs_scale_factors_stay_distinct():
    # An AAPS profile-switch percentage scales basal; a Loop override
    # multiplier scales overall insulin needs, moving ISF and CR too.
    # Collapsing them would misprice every replayed dose.
    schema = json.loads(
        (corpus.repo_root() / "specs/sync/therapy-effect.schema.json").read_text())
    effect = schema["properties"]["effect"]["properties"]
    assert "basalScaleFactor" in effect and "insulinNeedsScaleFactor" in effect


def test_remapping_rules_declare_their_lossiness():
    rules = yaml.safe_load(
        (corpus.repo_root() / "specs/sync/effect-remapping.yaml").read_text())
    for rule in rules["rules"]:
        assert "lossy" in rule, rule["id"]
        assert rule.get("evidence") or rule.get("note"), rule["id"]
    trio = next(r for r in rules["rules"] if r["id"] == "MAP-TRIO-EXERCISE")
    assert trio["lossy"] and trio["to"]["effect"] == {}


# ── sensitivity labels and projections ──────────────────────────────────

from nsschema import sensitivity as sens  # noqa: E402


def test_vocabulary_loads_and_levels_match_the_code():
    sens.load_vocabulary(corpus.repo_root())


def test_unlabelled_defaults_to_identifying():
    # A field must be argued down, never silently up: the opposite default
    # fails open on the next schema change.
    label = sens.label("somethingNobodyHasSeen", None)
    assert label["sensitivity"] == "identifying"


def test_credentials_outrank_identifiers():
    assert sens.label("loopSettings.deviceToken", None)["sensitivity"] == "secret"
    assert sens.label("loopSettings.bundleIdentifier", None)["sensitivity"] == "identifying"


def test_a_numeric_timestamp_is_not_freely_publishable():
    # `date` is a number, and the numeric rule alone called it descriptive.
    field = {"path": "date", "types": {"number": 10}, "numeric": {"count": 10}}
    label = sens.label("date", field)
    assert label["category"] == "temporal"
    assert label["sensitivity"] == "quasi-identifying"


def test_a_span_is_not_an_instant():
    # A duration says how long, not when. Treating it as temporal stripped
    # it from projections that need it - a replay cannot price a temp basal
    # without its duration.
    for path in ("duration", "absorptionTime", "store.{}.basal[].timeAsSeconds"):
        label = sens.label(path, {"numeric": {"count": 99}})
        assert label["category"] == "therapy-setting", path
        assert label["sensitivity"] == "descriptive", path


def test_a_utc_offset_is_location_not_time():
    assert sens.label("utcOffset", {"numeric": {"count": 9}})["category"] == "location"
    assert sens.label("pump.secondsFromGMT",
                      {"numeric": {"count": 9}})["category"] == "location"


def test_corroborated_values_are_vocabulary_and_withheld_ones_are_not():
    shared = {"string": {"distinct_values": ["Flat", "NONE"]}}
    private = {"string": {"distinct_values": None,
                          "value_note": "withheld: personal-shaped or over-long values"}}
    assert sens.label("direction", shared)["sensitivity"] == "descriptive"
    assert sens.label("direction", private)["sensitivity"] == "quasi-identifying"


def test_projection_is_a_whitelist():
    # An unlabelled path must not appear in a projection.
    profile = {"max_sensitivity": "descriptive", "categories": ["*"]}
    labels = {"known": {"sensitivity": "descriptive", "category": "vocabulary"}}
    out = sens.project({"known": 1, "brandNew": 2}, labels, profile)
    assert out == {"known": 1}


def test_projection_strips_credentials_and_identity_below_full():
    root = corpus.repo_root()
    labels = sens.label_census(root)["profile"]
    profiles = {p["id"]: p for p in sens.load_vocabulary(root)["profiles"]}
    doc = {"_id": "x", "units": "mg/dl",
           "loopSettings": {"deviceToken": "t", "maximumBolus": 9}}
    full = sens.project(doc, labels, profiles["full"])
    clinical = sens.project(doc, labels, profiles["clinical"])
    assert full["loopSettings"]["deviceToken"] == "t"
    assert "_id" not in clinical
    assert "deviceToken" not in clinical["loopSettings"]
    assert clinical["loopSettings"]["maximumBolus"] == 9


def test_effect_only_drops_timestamps_but_keeps_the_dose():
    root = corpus.repo_root()
    labels = sens.label_census(root)["devicestatus"]
    profiles = {p["id"]: p for p in sens.load_vocabulary(root)["profiles"]}
    doc = {"created_at": "2026-09-11T08:00:00Z",
           "loop": {"iob": {"iob": 1.4}}, "override": {"multiplier": 1.2}}
    out = sens.project(doc, labels, profiles["effect-only"])
    assert "created_at" not in out
    assert out["loop"]["iob"]["iob"] == 1.4
    assert out["override"]["multiplier"] == 1.2


def test_generated_schemas_carry_the_label():
    schema = json.loads((corpus.repo_root() / "specs/jsonschema/generated"
                         / "profile.write.tolerant.schema.json").read_text())
    token = schema["properties"]["loopSettings"]["properties"]["deviceToken"]
    assert token["x-sensitivity"] == "secret"
    assert token["x-data-category"] == "credential"


def test_registrations_declare_a_withholding_default():
    root = corpus.repo_root()
    for key, spec in sync_model.CONTROLLERS.items():
        block = sync_model.build(root, key, spec)["spec"]["sensitivity"]
        assert block["unlabelledPolicy"] == "withhold", key
        assert block["defaultProfile"] != "full", key


def test_vendor_extraction_accepts_both_kotlin_serialization_styles():
    # AAPS moved to Kotlin Multiplatform and from Gson to
    # kotlinx.serialization during 2026: @SerializedName became @SerialName
    # and the file moved from src/main to src/commonMain. Matching only the
    # old pair made a refreshed pin report an empty surface, which would
    # have read as "AAPS declares nothing".
    pattern = next(entry[2] for entry in vendor_surface.SOURCES
                   if entry[0] == "AndroidAPS")
    assert re.search(pattern, '@SerializedName("device")')
    assert re.search(pattern, '@SerialName("device")')


def test_a_moved_source_file_is_found_at_either_root(tmp_path):
    base = tmp_path / "externals" / "p" / "commonMain"
    base.mkdir(parents=True)
    (base / "M.kt").write_text('@SerialName("sgv") val sgv: Int')
    names = vendor_surface.extract(
        tmp_path, ["p/main/M.kt", "p/commonMain/M.kt"],
        r'@Serial(?:ized)?Name\(\s*"([^"]+)"\s*\)')
    assert names == ["sgv"]


# ── the proposal's worked example ───────────────────────────────────────

def test_the_proposal_tutorial_still_runs_as_printed():
    """PROPOSAL-controller-descriptions-2026-09-11.md §5 prints output.

    A tutorial that has rotted is worse than none, because a reader who
    tries it and gets something else stops trusting the rest.
    """
    root = corpus.repo_root()
    reg = yaml.safe_load(
        (root / "specs/sync/registrations/loop.yaml").read_text())
    absent = [i["input"] for i in reg["spec"]["replayInputs"]
              if i["status"] == "absent"]
    assert len(absent) == 8, f"the proposal says 8, got {len(absent)}"
    assert absent[:3] == ["automaticBolusApplicationFactor",
                          "carbAbsorptionModel", "gradualTransitionsThreshold"]

    inputs = {i["input"]: i for i in reg["spec"]["replayInputs"]}
    assert inputs["maxBolus"] == {
        "input": "maxBolus", "path": "loopSettings.maximumBolus",
        "collection": "profile", "status": "recorded"}
    # "declared and unpublished" must stay expressible, or the example's
    # whole point goes with it.
    assert inputs["automaticBolusApplicationFactor"]["status"] == "absent"
    assert inputs["automaticBolusApplicationFactor"]["path"] is None

    document = reg["spec"]["documents"][0]
    assert document["discriminator"] == {"path": "loop", "test": "is-object"}
    assert document["decomposesTo"] == [
        "ApsSnapshot", "PumpSnapshot", "UploaderSnapshot"]


def test_the_proposal_headline_numbers_match_their_reports():
    root = corpus.repo_root()
    census_dir = root / "reports" / "schema-census"

    coverage = json.loads((census_dir / "nocturne-coverage.json").read_text())
    ds = coverage["collections"]["devicestatus"]
    assert ds["summary"]["dropped"] == 56 and ds["paths"] == 166

    dosing = json.loads((census_dir / "dosing-inputs.json").read_text())
    loop = dosing["by_algorithm"]["loop"]
    assert loop["recorded"] == 4 and loop["absent"] == 8
    assert sum(loop.values()) == 20

    effects_report = json.loads((census_dir / "effects.json").read_text())
    treatments = effects_report["treatments"]
    assert treatments["total"] == 3415
    assert treatments["by_verdict"]["effect+motivation"] == 2934
    assert treatments["by_verdict"]["motivation-only"] == 481


# ── primitive catalogue and settings schema ─────────────────────────────

from nsschema import primitives, settings_schema  # noqa: E402


def test_every_named_primitive_is_defined():
    # Five documents referenced `decomposesTo: [...]` and nothing defined
    # those types. The catalogue closes that, so the registrations and the
    # catalogue must not drift apart.
    root = corpus.repo_root()
    catalogue, _gaps = primitives.build(root)
    named = set()
    for path in (root / "specs" / "sync" / "registrations").glob("*.yaml"):
        registration = yaml.safe_load(path.read_text())
        for document in registration["spec"]["documents"]:
            named.update(document["decomposesTo"])
    missing = named - set(catalogue)
    assert not missing, f"registrations name undefined primitives: {sorted(missing)}"


def test_catalogue_grades_every_field():
    root = corpus.repo_root()
    catalogue, _ = primitives.build(root)
    for name, primitive in catalogue.items():
        for field in primitive["fields"]:
            assert field["evidence"] in ("measured", "declared"), (name, field)
            assert field["why"], (name, field["name"])


def test_decomposer_assignments_are_read_from_source():
    # Name-level matching under-counted: V4 renames on the way in (Mgdl from
    # sgv) and a generic name like `programmed` was suppressed. The
    # decomposer states the mapping outright, so it is the better evidence.
    root = corpus.repo_root()
    assignments = primitives._decomposer_sources(root)
    assert "Sgv" in assignments.get("Mgdl", set())
    assert "Basal" in assignments.get("Entries", set())


def test_settings_schema_is_valid_and_accepts_a_partial_publication():
    root = corpus.repo_root()
    schema, _unmapped, _excluded = settings_schema.build(root)
    jsonschema.Draft202012Validator.check_schema(schema)
    # A controller publishes what it has; absent is not the same as default.
    jsonschema.Draft202012Validator(schema).validate({
        "effectiveFrom": "2026-09-11T08:00:00Z",
        "controller": {"product": "Loop", "version": "3.12.1"},
        "settings": {"maxBolus": 9.0},
    })


def test_settings_schema_requires_a_build_version():
    root = corpus.repo_root()
    schema, _, _ = settings_schema.build(root)
    controller = schema["properties"]["controller"]
    assert "version" in controller["required"], (
        "algorithm behaviour changes between releases; a setting without a "
        "build cannot be replayed against the right code")


def test_per_cycle_state_is_kept_out_of_settings():
    root = corpus.repo_root()
    schema, _unmapped, excluded = settings_schema.build(root)
    properties = schema["properties"]["settings"]["properties"]
    assert excluded, "the settings/state boundary must be stated, not implied"
    for name in ("flatBGsDetected", "mealCOB", "slopeFromMaxDeviation"):
        assert name not in properties, f"{name} is per-cycle state"
