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
    # The latest version of every readable record visible by the last
    # history read reaches the client, when it reads from the start.
    case = CASES[cid]
    reads = [c for c in case["calls"] if c["kind"] == "history"]
    if not reads or reads[0].get("cursor") not in (0, None, "last"):
        pytest.skip("starts from a cursor past some writes")
    last = max(c["at"] for c in reads)
    readable = case.get("readable", case["collections"])
    latest = {}
    for w in case["writes"]:
        if w["collection"] in readable and w.get("committedAt") is not None and w["committedAt"] <= last:
            if w["id"] not in latest or w["srvModified"] > latest[w["id"]]:
                latest[w["id"]] = w["srvModified"]
    received = set(sync_cursor.run(case)["received"])
    assert {"%s@%s" % kv for kv in latest.items()} <= received


@pytest.mark.parametrize("cid", sorted(c for c in CASES if CASES[c].get("control")))
def test_control_exists(cid):
    assert CASES[cid]["control"] in CASES and CASES[cid]["control"] != cid
