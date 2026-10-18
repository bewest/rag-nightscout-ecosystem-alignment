"""What a hub does with a command and a proposal (queue item SPEC-REG-COMMANDS).

Commands §2 and rules CM1-CM20. Each case under
specs/sync/conformance/commands/ carries hand-authored expectations; the
reference in commands.py must reproduce every call's result and the final
state of every command and proposal. Four invariants hold on every case,
whatever its expectations say.
"""
import pytest
import yaml

from nsschema import commands, corpus

ROOT = corpus.repo_root()
CASES_DIR = ROOT / "specs" / "sync" / "conformance" / "commands"
CASES = {p.stem: yaml.safe_load(p.read_text()) for p in sorted(CASES_DIR.glob("*.yaml"))}


def test_there_are_cases():
    assert len(CASES) >= 20


@pytest.mark.parametrize("cid", sorted(CASES))
def test_case_id_matches_its_file(cid):
    assert CASES[cid]["id"] == cid


@pytest.mark.parametrize("cid", sorted(CASES))
def test_calls(cid):
    case = CASES[cid]
    got = commands.run(case)["calls"]
    for i, (call, want) in enumerate(zip(case["calls"], case["expected"]["calls"])):
        assert got[i] == want, (i, call["kind"])
    assert len(got) == len(case["expected"]["calls"])


@pytest.mark.parametrize("cid", sorted(CASES))
def test_final_states(cid):
    case = CASES[cid]
    result = commands.run(case)
    assert result["commands"] == case["expected"].get("commands", {})
    assert result["proposals"] == case["expected"].get("proposals", {})


@pytest.mark.parametrize("cid", sorted(c for c in CASES if CASES[c].get("control")))
def test_control_exists_and_differs(cid):
    control = CASES[CASES[cid]["control"]]
    assert control["id"] != cid
    assert control["expected"] != CASES[cid]["expected"]


def _deliveries(case):
    """Every push that was sent and every command a fetch returned, with the
    call that did it."""
    result = commands.run(case)
    hub = result["hub"]
    for call, got in zip(case["calls"], result["calls"]):
        if call["kind"] == "push" and got.get("sent"):
            yield call, hub.commands[call["command"]]
        if call["kind"] == "fetch" and got.get("status") == 200:
            for cid in got["commands"]:
                yield call, hub.commands[cid]


@pytest.mark.parametrize("cid", sorted(CASES))
def test_never_another_tenant(cid):
    # CM6: nothing reaches an instance on another tenant.
    case = CASES[cid]
    for call, command in _deliveries(case):
        assert case["instances"][command["destination"]]["tenant"] == command["tenant"]
        if call["kind"] == "fetch":
            assert call["tenant"] == command["tenant"]


@pytest.mark.parametrize("cid", sorted(CASES))
def test_never_after_expiry(cid):
    # CM3: nothing is sent or fetched at or after its expiry.
    for call, command in _deliveries(CASES[cid]):
        assert call["at"] < command["expiresAt"]


@pytest.mark.parametrize("cid", sorted(c for c in CASES if CASES[c]["mode"] == "multi"))
def test_never_pushed_unbound(cid):
    # CM19: under multi, nothing is sent from a context with no tenant bound.
    for call, command in _deliveries(CASES[cid]):
        if call["kind"] == "push":
            assert call.get("bound") == command["tenant"]


@pytest.mark.parametrize("cid", sorted(CASES))
def test_approved_command_carries_approved_hash(cid):
    # CM13: a command made by an approval carries the payload hash its approval
    # named. What a controller receives is the case's `enact.received`, so a
    # hub that swapped the payload at delivery is shown by CM10's cases, not here.
    case = CASES[cid]
    result = commands.run(case)
    for call, got in zip(case["calls"], result["calls"]):
        if call["kind"] == "approve" and got.get("commandId"):
            made = result["hub"].commands[got["commandId"]]
            assert made["payloadHash"] == commands.payload_hash(call["approves"])
