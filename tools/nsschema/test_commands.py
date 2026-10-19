"""What a hub does with a command and a proposal (queue item SPEC-REG-COMMANDS).

Commands §2 and rules CM1-CM32. Each case under
specs/sync/conformance/commands/ carries hand-authored expectations; the
reference in commands.py must reproduce every call's result and the final
state of every command and proposal. The invariants below hold on every case,
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
    """Every command a fetch returned, with the call that did it. A signal
    delivers nothing (CM27)."""
    result = commands.run(case)
    hub = result["hub"]
    for call, got in zip(case["calls"], result["calls"]):
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


def _signals(case):
    result = commands.run(case)
    for call, got in zip(case["calls"], result["calls"]):
        if call["kind"] == "signal" and got.get("signalled"):
            yield call, got, result["hub"].commands[call["command"]]


@pytest.mark.parametrize("cid", sorted(c for c in CASES if CASES[c]["mode"] == "multi"))
def test_never_signalled_unbound(cid):
    # CM19: under multi, no signal is sent from a context with no tenant bound.
    for call, _, command in _signals(CASES[cid]):
        assert call.get("bound") == command["tenant"]


@pytest.mark.parametrize("cid", sorted(CASES))
def test_signal_carries_nothing_and_reaches_the_destination_only(cid):
    # CM27: a signal goes to the command's destination and carries nothing of it.
    for call, got, command in _signals(CASES[cid]):
        assert got["to"] == command["destination"]
        assert got["carries"] == {}
        assert call["at"] < command["expiresAt"]


@pytest.mark.parametrize("cid", sorted(CASES))
def test_fetch_bound_in_every_reply(cid):
    # CM30: every accepted command or approval names its destination's fetch bound,
    # and every outstanding list names each holder's.
    case = CASES[cid]
    result = commands.run(case)
    for call, got in zip(case["calls"], result["calls"]):
        if call["kind"] in ("command", "approve") and got.get("status") == 201:
            made = result["hub"].commands[got["commandId"]]
            bound = commands.fetch_bound(case, case["instances"][made["destination"]])
            assert got["fetchWithinSeconds"] == bound
            assert got.get("mayExpireUnfetched", False) == (made["expiresAt"] - call["at"] <= bound)
        if call["kind"] == "outstanding" and got.get("status") == 200:
            assert "destinations" in got


@pytest.mark.parametrize("cid", sorted(CASES))
def test_fetched_until_reported(cid):
    # CM26: while a fetched command has no report, is not past its expiry and its
    # destination holds the sink, every fetch by the destination returns it.
    case = CASES[cid]
    result = commands.run(case)
    fetched_at, reported = {}, set()
    for call, got in zip(case["calls"], result["calls"]):
        if call["kind"] == "report" and got.get("status") == 200:
            reported.add(call["command"])
        if call["kind"] == "cancel" and got.get("status") in (200, 202):
            reported.add(call["command"])  # a carried cancel stands in for the command
        if call["kind"] == "fetch" and got.get("status") == 200:
            for cid_, c in result["hub"].commands.items():
                if (cid_ in fetched_at and cid_ not in reported
                        and c["destination"] == call["instance"]
                        and call["at"] < c["expiresAt"]
                        and commands._holds(case["instances"][c["destination"]],
                                            c["channel"], call["at"])):
                    assert cid_ in got["commands"], (cid_, call["at"])
            for c in got["commands"]:
                fetched_at.setdefault(c, call["at"])


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


@pytest.mark.parametrize("cid", sorted(CASES))
def test_never_enacted_twice(cid):
    # CM21: a controller instance enacts each commandId at most once.
    case = CASES[cid]
    enacted = [(call["instance"], call["command"])
               for call, got in zip(case["calls"], commands.run(case)["calls"])
               if call["kind"] == "enact" and got.get("state") == "succeeded"]
    assert len(enacted) == len(set(enacted)), enacted


@pytest.mark.parametrize("cid", sorted(CASES))
def test_never_delivered_after_cancel(cid):
    # CM25: a command cancelled before hand-over is never fetched afterwards.
    case = CASES[cid]
    cancelled_at = {}
    for call, got in zip(case["calls"], commands.run(case)["calls"]):
        if call["kind"] == "cancel" and got.get("state") == "cancelled":
            cancelled_at[call["command"]] = call["at"]
        delivered = []
        if call["kind"] == "fetch" and got.get("status") == 200:
            delivered = got["commands"]
        for c in delivered:
            assert c not in cancelled_at, (c, call["at"])
