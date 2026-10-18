"""The cursor a hub returns, and what a client receives (queue item SPEC-SYNC-TRANSPORT).

Sync-transport §4, rules T5, T6, T9 and T10. Each case under
specs/sync/conformance/sync-transport/ carries hand-authored expectations;
the reference in sync_cursor.py must reproduce every call's result and the
records the client ends up with.
"""
import pytest
import yaml

from nsschema import corpus, sync_cursor

ROOT = corpus.repo_root()
CASES_DIR = ROOT / "specs" / "sync" / "conformance" / "sync-transport"
CASES = {p.stem: yaml.safe_load(p.read_text()) for p in sorted(CASES_DIR.glob("*.yaml"))}


def test_there_are_cases():
    assert len(CASES) >= 8


@pytest.mark.parametrize("cid", sorted(CASES))
def test_case_id_matches_its_file(cid):
    assert CASES[cid]["id"] == cid


@pytest.mark.parametrize("cid", sorted(CASES))
def test_calls(cid):
    case = CASES[cid]
    assert sync_cursor.run(case)["calls"] == case["expected"]["calls"]


@pytest.mark.parametrize("cid", sorted(CASES))
def test_received(cid):
    case = CASES[cid]
    assert sync_cursor.run(case)["received"] == case["expected"]["received"]


@pytest.mark.parametrize("cid", sorted(CASES))
def test_nothing_written_is_lost(cid):
    # Every write visible by the last call's step reaches a client that reads
    # until complete: the property every rule here exists for.
    case = CASES[cid]
    if any(c.get("cursor") not in (None, "last", 0) for c in case["calls"]):
        pytest.skip("starts from a cursor past some writes")
    last = max([c["at"] for c in case["calls"] if c["kind"] == "history"] or [0])
    readable = case.get("readable", case["collections"])
    visible = sorted(w["id"] for w in case["writes"]
                     if w["committedAt"] <= last and w["collection"] in readable)
    assert sync_cursor.run(case)["received"] == visible


@pytest.mark.parametrize("cid", sorted(c for c in CASES if CASES[c].get("control")))
def test_control_exists(cid):
    assert CASES[cid]["control"] in CASES and CASES[cid]["control"] != cid
