"""Tests for nsprobe, on synthetic documents only.

Run: python3 -m pytest tools/nsprobe/test_nsprobe.py
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nsprobe import cli, family, layout, privacy, probes, sources  # noqa: E402
from nsschema import corpus  # noqa: E402

T0 = 1_750_000_000_000  # a fixed synthetic epoch, ms


def _site(i, aaps=False):
    """One synthetic site: 40 entries, a few treatments, devicestatus, profile."""
    dev = "openaps://Samsung SM-X" if aaps else "Trio"
    entries = [{"_id": f"e{i}-{k}", "sgv": 100 + k, "date": T0 + k * 300_000,
                "dateString": "2025-06-15T15:06:40.000Z", "type": "sgv",
                "device": dev, "utcOffset": 0} for k in range(40)]
    # A Share-style duplicate of reading 5, 2 s later, different _id.
    entries.append({"_id": f"dup{i}", "sgv": 105, "date": T0 + 5 * 300_000 + 2000,
                    "type": "sgv", "device": "share2"})
    treatments = [
        {"_id": f"t{i}-1", "eventType": "Correction Bolus" if aaps else "SMB",
         "insulin": 0.3, "type": "SMB" if aaps else None, "isSMB": True if aaps else None,
         "created_at": "2025-06-15T15:06:40.000Z", "enteredBy": "openaps://AndroidAPS" if aaps else "Trio"},
        {"_id": f"t{i}-2", "eventType": "Bolus", "insulin": 0.4, "automatic": True,
         "created_at": "2025-06-15T16:06:40.000Z", "enteredBy": dev},
        {"_id": f"t{i}-3", "eventType": "Temp Basal", "absolute": 0.5, "rate": 0.5,
         "duration": 30, "created_at": "2025-06-15T17:06:40.000Z", "enteredBy": dev},
        {"_id": f"t{i}-4", "eventType": f"Private label of site {i}", "created_at": "2025-06-15T18:00:00Z",
         "enteredBy": dev},
    ]
    ds = [{"_id": f"d{i}-{k}", "device": dev, "created_at": "2025-06-15T15:06:40.000Z",
           "openaps": {"iob": [{"iob": 1.0, "basaliob": 0.2}] if aaps else {"iob": 1.0},
                       "suggested": {"bg": 120, "ISF": 3.0 if i == 0 else 50, "targetBG": 100}}}
          for k in range(10)]
    profile = [{"_id": f"p{i}", "defaultProfile": "Default", "units": "mg/dl",
                "store": {"Default": {"units": "mmol" if i == 0 else "mg/dl"}}}]
    return {"entries": entries, "treatments": treatments, "devicestatus": ds,
            "profile": profile}


@pytest.fixture
def raw(tmp_path):
    src = tmp_path / "raw"
    names = ["alice.example.herokuapp.com", "bob-ns", "carol_site", "dave"]
    for i, name in enumerate(names):
        docs = _site(i, aaps=i % 2 == 1)
        d = src / name
        d.mkdir(parents=True)
        for coll, arr in docs.items():
            (d / f"{coll}.json").write_text(json.dumps(arr))
    # Site 0 also has a v3 export, wrapped in the v3 envelope, one new doc.
    v3 = src / names[0] / "v3"
    v3.mkdir()
    (v3 / "treatments.json").write_text(json.dumps({"status": 200, "result": [
        {"identifier": "t0-1", "eventType": "SMB", "insulin": 0.3, "isValid": True,
         "srvModified": T0, "created_at": "2025-06-15T15:06:40.000Z"},
        {"identifier": "fresh", "eventType": "Note", "isValid": False,
         "srvModified": T0, "created_at": "2025-06-15T15:06:40.000Z"}]}))
    return src


@pytest.fixture
def laid_out(raw, tmp_path):
    dest, key = tmp_path / "corpus", tmp_path / "private" / "key.json"
    layout.layout(raw, dest, key)
    return dest, key


# ── layout ──────────────────────────────────────────────────────────────

def test_layout_pseudonymises_and_keeps_key_out_of_corpus(laid_out):
    dest, key = laid_out
    labels = sorted(p.name for p in (dest / "v1").iterdir())
    assert labels == ["S001", "S002", "S003", "S004"]
    mapping = json.loads(key.read_text())
    assert "alice.example.herokuapp.com" in mapping.values()
    for f in dest.rglob("*"):
        assert "alice" not in str(f) and "herokuapp" not in str(f)


def test_layout_unwraps_v3_envelope(laid_out):
    dest, _ = laid_out
    docs = list(sources.iter_documents(dest / "v3" / "S001" / "treatments.json"))
    assert [d["identifier"] for d in docs] == ["t0-1", "fresh"]


def test_layout_refuses_key_inside_dest(raw, tmp_path):
    with pytest.raises(SystemExit):
        layout.layout(raw, tmp_path / "c", tmp_path / "c" / "key.json")


def test_discover_refuses_real_site_names(tmp_path):
    (tmp_path / "v1" / "my-nightscout").mkdir(parents=True)
    with pytest.raises(ValueError):
        sources.discover(tmp_path)


def test_ndjson_is_read(tmp_path):
    p = tmp_path / "x.json"
    p.write_text('{"a": 1}\n{"a": 2}\n')
    assert [d["a"] for d in sources.iter_documents(p)] == [1, 2]


# ── family ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("doc,coll,fam", [
    ({"device": "openaps://samsung SM-G991B"}, "devicestatus", "aaps"),
    ({"device": "openaps://myrig"}, "devicestatus", "oref0-rig"),
    ({"enteredBy": "openaps://AndroidAPS"}, "treatments", "aaps"),
    ({"device": "Trio"}, "devicestatus", "trio"),
    ({"device": "iAPS"}, "devicestatus", "iaps"),
    ({"device": "loop://iPhone", "loop": {}}, "devicestatus", "loop"),
    ({"device": "share2"}, "entries", "share"),
    ({"filtered": 1, "unfiltered": 2}, "entries", "xdrip"),
    ({}, "treatments", "unknown"),
])
def test_family_rules(doc, coll, fam):
    assert family.classify(doc, coll)[0] == fam


def test_family_signal_never_carries_the_value():
    _, signal = family.classify({"device": "openaps://rig-hostname-123"}, "devicestatus")
    assert "rig" not in signal.split(":")[1] or signal.endswith("openaps-host")
    assert "123" not in signal


# ── privacy ─────────────────────────────────────────────────────────────

def test_fold_hides_values_from_fewer_than_three_sites():
    folded = privacy.fold({"Bolus": {"a", "b", "c"}, "Alice's thing": {"a"}},
                          {"Bolus": 9, "Alice's thing": 1})
    assert "Bolus" in folded and "Alice's thing" not in folded
    assert folded["_other"]["documents"] == 1


@pytest.mark.parametrize("bad", [
    "https://x.herokuapp.com", "someone@example.org", "2025-06-15T15:06",
    "5f2b1c9e8d7a6b5c4d3e2f1a", "123e4567-e89b-12d3-a456-426614174000",
    "mysite.herokuapp.com", "1750000000000",
])
def test_validator_rejects_identifying_strings(bad):
    assert privacy.check_output({"result": {"x": bad}})


def test_validator_accepts_quarters_and_vocabulary():
    assert not privacy.check_output({"generated": "2026-09-23",
                                     "result": {"2025-Q2": {"Temp Basal": 3}}})


# ── probes, end to end ──────────────────────────────────────────────────

def _run(dest, tmp_path):
    out = tmp_path / "out"
    cli.main(["run", "--root", str(dest), "--out", str(out), "--contributor", "test"])
    return {p.stem: json.loads(p.read_text()) for p in (out / "nsprobe").glob("*.json")}


def test_run_outputs_pass_privacy_check(laid_out, tmp_path):
    dest, _ = laid_out
    _run(dest, tmp_path)
    files, problems = privacy.check_dir(tmp_path / "out")
    assert files and not problems


def test_no_real_site_name_or_private_label_reaches_output(laid_out, tmp_path):
    dest, _ = laid_out
    _run(dest, tmp_path)
    blob = "\n".join(p.read_text() for p in (tmp_path / "out").rglob("*.json"))
    for needle in ("alice", "herokuapp", "bob-ns", "carol", "Private label", "SM-X", "Samsung"):
        assert needle not in blob, needle


def test_smb_confusion_counts_trio_bolus_automatic_as_heuristic_only(laid_out, tmp_path):
    dest, _ = laid_out
    r = _run(dest, tmp_path)["smb_marking"]["result"]["explicit_marker_vs_automatic_lt5U_rule"]
    # Trio: eventType SMB (explicit, heuristic misses it) and an automatic
    # Bolus (heuristic calls it SMB, no explicit marker).
    assert r["trio"]["explicit=True|automatic_lt5U=False"]["documents"] == 2
    assert r["trio"]["explicit=False|automatic_lt5U=True"]["documents"] == 2


def test_duplicates_finds_cross_uploader_entry_pairs(laid_out, tmp_path):
    dest, _ = laid_out
    r = _run(dest, tmp_path)["duplicates"]["result"]["by_api_and_collection"]["v1:entries"]
    keys = [k for k in r if k.startswith("same_sgv:cross-device:<=5s:")]
    assert sum(r[k]["documents"] for k in keys) == 4
    assert not [k for k in r if k.startswith("same_sgv:same-device")]


def test_v3_envelope_and_overlap(laid_out, tmp_path):
    dest, _ = laid_out
    r = _run(dest, tmp_path)["v3_envelope"]["result"]
    assert r["envelope_fields"]["v3:treatments"]["isValid:false"]["documents"] == 1
    ov = r["v1_v3_identifier_overlap"]["treatments"]
    assert ov["v3_identifier_in_v1"]["documents"] == 1
    assert ov["v3_identifier_not_in_v1"]["documents"] == 1


def test_v1_preferred_so_sites_are_not_double_counted(laid_out, tmp_path):
    dest, _ = laid_out
    r = _run(dest, tmp_path)["event_types"]
    assert r["run"]["documents_by_collection"]["treatments"] == 16


def test_units_confusion_flags_mmol_isf(laid_out, tmp_path):
    dest, _ = laid_out
    r = _run(dest, tmp_path)["units"]["result"]["algorithm_value_vs_profile_units"]["isf"]
    assert r["profile=mmol|isf<15"]["documents"] == 10


def test_openaps_iob_container_type_split(laid_out, tmp_path):
    dest, _ = laid_out
    r = _run(dest, tmp_path)["openaps_shape"]["result"]["iob_container_type_by_family"]
    assert "array" in r["aaps"] and "object" in r["trio"]


def test_break_it_private_value_on_three_sites_would_surface(tmp_path):
    """Control: the fold is what hides the private label, not an accident.

    Give the same label to three sites and it must appear, which proves the
    other tests' absence check is not vacuous.
    """
    t = probes.Tally()
    for s in ("S001", "S002", "S003"):
        t.add("all", "Shared Custom Event", s)
    assert "Shared Custom Event" in t.emit(fold_keys=True)["all"]


# ── nsschema corpus override ────────────────────────────────────────────

def test_nsschema_corpus_env(monkeypatch, laid_out):
    dest, _ = laid_out
    monkeypatch.setenv("NSSCHEMA_CORPUS", f"v1={dest / 'v1'}:flat_site")
    found = corpus.discover(Path("/nonexistent"))
    assert {s.site for s in found} == {"S001", "S002", "S003", "S004"}
    assert {s.snapshot for s in found} == {"v1"}


def test_nsschema_corpus_env_rejects_bad_layout(monkeypatch):
    monkeypatch.setenv("NSSCHEMA_CORPUS", "v1=/x:weird")
    with pytest.raises(ValueError):
        corpus.snapshots()


def test_census_wrapper_runs_on_external_corpus(laid_out, tmp_path):
    dest, _ = laid_out
    out = tmp_path / "out"
    cli.main(["census", "--root", str(dest), "--out", str(out)])
    q = json.loads((out / "schema-census-v1" / "quirks.json").read_text())
    assert q["results"]
    census = json.loads((out / "schema-census-v1" / "treatments.census.json").read_text())
    assert census["sites"] == ["S001", "S002", "S003", "S004"]
    assert (out / "schema-census-v3" / "treatments.census.json").is_file()


def test_activity_search_ignores_insulin_activity():
    a = probes.Activity()

    class C:
        collection, site, family, api = "devicestatus", "S001", "trio", "v1"
    a.observe(C, {"openaps": {"iob": {"activity": 0.01, "iobWithZeroTemp": {"activity": 0}}},
                  "uploader": {"heartRate": 70}})
    found = {p for coll in a.anywhere.d.values() for p in coll}
    assert found == {"uploader.heartRate"}
