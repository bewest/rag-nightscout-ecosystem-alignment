"""Tests for the query-coercion emitter.

Run: python3 -m pytest tools/nsschema/test_coercion.py

The plan's T0.5 says "a test asserts the emitted table matches the model for
every collection". That is the first group below. The second group pins the
decisions the emitter makes that are not mechanical -- what it refuses to
coerce, and why -- because those are the ones a later change could quietly
reverse.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nsschema import corpus  # noqa: E402
from nsschema.emit import coercion_emit  # noqa: E402

ROOT = corpus.repo_root()
MODEL_DIR = ROOT / "specs/nsschema"

# Every model on disk, not the four in ROOT_SCHEMA. activity and food gained
# models in T2.2 (69e6bc54) after this emitter was written, and iterating
# ROOT_SCHEMA skipped them without saying so.
MODELLED = coercion_emit.modelled_collections(MODEL_DIR)


def _model(collection):
    return json.loads((MODEL_DIR / f"{collection}.model.json").read_text())


def _leaves(node, prefix=""):
    for name, child in node.get("children", {}).items():
        if name in ("[]", "{}"):
            continue
        path = f"{prefix}.{name}" if prefix else name
        kids = {k: v for k, v in child.get("children", {}).items()
                if k not in ("[]", "{}")}
        if kids:
            yield from _leaves(child, path)
        else:
            yield path, child


# ── the table agrees with the model, for every collection ───────────────

@pytest.mark.parametrize("collection", MODELLED)
def test_every_coercible_leaf_matches_its_declared_type(collection):
    table = coercion_emit.build(_model(collection))
    for path, node in _leaves(_model(collection)["root"]):
        types = [t for t in node.get("types", []) if t != "null"]
        kinds = {coercion_emit.TYPE_KIND[t] for t in types
                 if t in coercion_emit.TYPE_KIND}
        if len(kinds) == 1:
            assert table["fields"][path]["kind"] == kinds.pop(), path
        else:
            assert path not in table["fields"], path


@pytest.mark.parametrize("collection", MODELLED)
def test_every_leaf_is_accounted_for(collection):
    """No leaf may be silently dropped: it is either coerced or explicitly
    recorded as uncoerced. A field that appears in neither list is one the
    query layer will treat as a string without anyone having decided that."""
    table = coercion_emit.build(_model(collection))
    covered = set(table["fields"]) | set(table["uncoerced"])
    for path, _node in _leaves(_model(collection)["root"]):
        assert path in covered, f"{collection}.{path} is in neither list"


@pytest.mark.parametrize("collection", MODELLED)
def test_nullable_is_carried(collection):
    """`nullable` is not decoration. Three-arm validation found that comparisons
    against null are where the two backends diverge, so the query layer has to
    be able to tell a legitimate null from a failed coercion."""
    model = _model(collection)
    table = coercion_emit.build(model)
    for path, node in _leaves(model["root"]):
        if path not in table["fields"]:
            continue
        nullable = bool(node.get("nullable")) or "null" in node.get("types", [])
        assert table["fields"][path].get("nullable", False) == nullable, path


# ── the non-mechanical decisions ────────────────────────────────────────

def test_multi_typed_fields_are_left_uncoerced():
    """A field observed as more than one scalar type must NOT be coerced.
    Picking one would make the other shape unqueryable, and the model saying
    two types is the ecosystem disagreeing, not noise to round off."""
    table = coercion_emit.build({
        "collection": "t",
        "root": {"children": {
            "mixed": {"types": ["number", "string"], "children": {}},
            "plain": {"types": ["number"], "children": {}}}}})
    assert "mixed" not in table["fields"]
    assert table["uncoerced"]["mixed"] == ["number", "string"]
    assert table["fields"]["plain"]["kind"] == "number"


def test_objects_and_arrays_are_left_uncoerced():
    table = coercion_emit.build({
        "collection": "t",
        "root": {"children": {
            "blob": {"types": ["object"], "children": {}},
            "list": {"types": ["array"], "children": {}}}}})
    assert table["fields"] == {}
    assert set(table["uncoerced"]) == {"blob", "list"}


def test_wildcard_segments_are_not_emitted():
    """`[]` and `{}` cannot be addressed from a query string, so an entry for
    one would never be consulted."""
    table = coercion_emit.build({
        "collection": "t",
        "root": {"children": {
            "store": {"types": ["object"], "children": {
                "{}": {"types": ["object"], "children": {
                    "dia": {"types": ["number"], "children": {}}}}}}}}})
    assert table["fields"] == {}
    # `store` itself is recorded as an uncoerced object -- honest, since it is a
    # real leaf of the traversal once the wildcard is skipped. What must never
    # appear is a path CONTAINING a wildcard segment.
    assert not any("{}" in k or "[]" in k
                   for k in (*table["fields"], *table["uncoerced"]))
    assert "store" in table["uncoerced"]


def test_datelike_strings_are_flagged():
    """BF-01 is a date bound arriving as the wrong type. The flag is what lets
    the query layer inject a window that actually bounds anything."""
    table = coercion_emit.build({
        "collection": "t",
        "root": {"children": {
            "created_at": {"types": ["string"], "children": {}},
            "notes": {"types": ["string"], "children": {}}}}})
    assert table["fields"]["created_at"]["datelike"] is True
    assert "datelike" not in table["fields"]["notes"]


# ── the drift the shipping walkers still carry ──────────────────────────

def test_known_over_coercions_are_detected():
    """The three treatments fields BF-02 names, plus entries. If this stops
    firing, either the walker was fixed (delete the row) or the detector broke."""
    tables = {c: coercion_emit.build(_model(c)) for c in MODELLED}
    rows = coercion_emit.drift(tables)
    over = {(c, f) for c, _w, f, _g, _m, note in rows if note.startswith("OVER")}
    for field in ("insulin", "carbs", "glucose"):
        assert ("treatments", field) in over, field


def test_collections_with_no_walker_are_reported_as_under_coerced():
    tables = {c: coercion_emit.build(_model(c)) for c in MODELLED}
    rows = coercion_emit.drift(tables)
    under = {c for c, _w, _f, _g, _m, note in rows if note.startswith("UNDER")}
    assert "devicestatus" in under
    assert "profile" in under


def test_food_is_reported_as_having_no_query_path():
    """EXPECTATION CHANGED 2026-09-15, deliberately. This test previously read
    `test_missing_models_are_reported_not_skipped` and asserted that food and
    activity have NO model, because when it was written they did not. T2.2
    (69e6bc54) gave both a model, so the old assertion now encodes a fact that
    stopped being true, and keeping it would have hidden the finding below.

    What is true of food is different and worse for BF-03: food has a model,
    but it reaches no `lib/server/query.js` call at all. `lib/server/food.js`
    exposes list(fn)/listquickpicks(fn)/listregular(fn) -- none take query
    options -- and `lib/api/food/index.js` passes none. So v1 /food accepts no
    filters, and there is no under-coercion on food to fix."""
    for collection in ("food", "activity"):
        assert (MODEL_DIR / f"{collection}.model.json").is_file()
        assert collection in MODELLED

    tables = {c: coercion_emit.build(_model(c)) for c in MODELLED}
    rows = coercion_emit.drift(tables)
    nopath = {c for c, _w, _f, _g, _m, note in rows
              if note.startswith("NO QUERY PATH")}
    assert nopath == {"food"}


def test_activity_has_no_numeric_field_to_coerce():
    """Also for BF-03, which names activity as under-coerced. The activity
    model has exactly two leaves, `_id` and `created_at`, both strings, so
    schema-driven coercion cannot give activity a numeric filter that works.
    The collection is open-bodied -- the server stores what it is handed -- so
    a deployment may well hold numbers there, but nothing declares them and
    this table will not guess."""
    table = coercion_emit.build(_model("activity"))
    assert set(table["fields"]) == {"_id", "created_at"}
    assert all(e["kind"] == "string" for e in table["fields"].values())
    assert coercion_emit.bundle({"activity": table})["collections"]["activity"] == {}


def test_no_orphan_rows_because_bf_12_does_not_reproduce():
    """BF-12 says `entries.rawbg` is coerced but absent from the model. The
    walker transcription it was raised from was wrong: `lib/server/entries.js`
    coerces `rssi`, not `rawbg`, and has never contained the string "rawbg" on
    any branch. `rssi` IS in the model, as an integer, so it is a correct entry.
    There is no stale walker entry, on any collection."""
    assert "rawbg" not in coercion_emit.SHIPPING_WALKERS["entries"]["walker"]
    assert "rssi" in coercion_emit.SHIPPING_WALKERS["entries"]["walker"]
    assert coercion_emit.build(_model("entries"))["fields"]["rssi"]["kind"] == "integer"

    tables = {c: coercion_emit.build(_model(c)) for c in MODELLED}
    orphans = [r for r in coercion_emit.drift(tables) if r[5].startswith("ORPHAN")]
    assert orphans == []


# -- the bundle the server actually loads --------------------------------

BUNDLE_PATH = ROOT / "specs/generated/coercion/query-coercion.json"


def _fresh_bundle():
    return coercion_emit.bundle({c: coercion_emit.build(_model(c)) for c in MODELLED})


def test_checked_in_bundle_matches_a_fresh_emit():
    """The anti-drift link. If a model changes and nobody reruns `make
    schema-emit`, this fails."""
    assert json.loads(BUNDLE_PATH.read_text()) == _fresh_bundle()


def test_bundle_covers_exactly_the_collections_with_a_query_path():
    assert set(_fresh_bundle()["collections"]) == set(coercion_emit.QUERY_COLLECTIONS)
    assert "food" not in _fresh_bundle()["collections"]


def test_bundle_kinds_are_only_the_ones_the_query_layer_acts_on():
    """`string` is identity on a value that arrived as text, so a string entry
    would be dead weight in a file the server parses on every boot."""
    for collection, fields in _fresh_bundle()["collections"].items():
        for field, kind in fields.items():
            assert kind in coercion_emit.COERCED_KINDS, f"{collection}.{field}"


@pytest.mark.parametrize("collection", coercion_emit.QUERY_COLLECTIONS)
def test_bundle_agrees_with_the_per_collection_table(collection):
    table = coercion_emit.build(_model(collection))
    shipped = _fresh_bundle()["collections"][collection]
    for field, entry in table["fields"].items():
        if entry["kind"] in coercion_emit.COERCED_KINDS:
            assert shipped[field] == entry["kind"], field
        else:
            assert field not in shipped, field


# -- the copy vendored into cgm-remote-monitor ---------------------------

VENDORED = ROOT / "externals/work/crm-bf-coercion/lib/server/query-coercion.json"


@pytest.mark.skipif(not VENDORED.is_file(),
                    reason="cgm-remote-monitor worktree not checked out here")
def test_vendored_copy_matches_the_emitted_bundle():
    """cgm-remote-monitor has to carry the table to load it at runtime; this
    repo owns the emitter (decision D12). That is two copies, so something has
    to hold them together, and this is it."""
    assert json.loads(VENDORED.read_text()) == _fresh_bundle()
