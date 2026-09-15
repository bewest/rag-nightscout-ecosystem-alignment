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

from nsschema import corpus, specload  # noqa: E402
from nsschema.emit import coercion_emit  # noqa: E402

ROOT = corpus.repo_root()
MODEL_DIR = ROOT / "specs/nsschema"

MODELLED = [c for c in specload.ROOT_SCHEMA
            if (MODEL_DIR / f"{c}.model.json").is_file()]


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


def test_missing_models_are_reported_not_skipped():
    """food and activity have no model, and the emitter must say so rather
    than emit an empty table that reads as 'nothing to coerce'."""
    tables = {c: coercion_emit.build(_model(c)) for c in MODELLED}
    rows = coercion_emit.drift(tables)
    nomodel = {c for c, _w, _f, _g, model, _note in rows if model == "no model"}
    assert {"food", "activity"} <= nomodel
