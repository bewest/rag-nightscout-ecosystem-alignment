"""What a hub does with a plan (queue item SPEC-PLANS).

Plans PN1-PN16. Each case under specs/sync/conformance/plans/ carries
hand-authored expectations; the reference in plans.py must reproduce every
call's result and the final states of commands, proposals and plan mirrors.
Invariants hold on every case, whatever its expectations say.
"""
import copy

import pytest
import yaml

from nsschema import corpus, plans

ROOT = corpus.repo_root()
CASES_DIR = ROOT / "specs" / "sync" / "conformance" / "plans"
CASES = {p.stem: yaml.safe_load(p.read_text()) for p in sorted(CASES_DIR.glob("*.yaml"))}
CREATING = ("approvePlan", "confirm", "approveOccurrence", "skip", "endPlan", "command")


def resolved(case):
    """Replace `hash: element:<id>` by the hash of that element of the plan the
    call names, taking proposal ids from the hand-authored expectations."""
    case = copy.deepcopy(case)
    proposed = {}
    for call, want in zip(case["calls"], case["expected"]["calls"]):
        if call["kind"] == "proposePlan" and want.get("proposalId"):
            proposed[want["proposalId"]] = call["plan"]
    for call in case["calls"]:
        named = call.get("proposal") or (call.get("plan") if call["kind"] != "proposePlan" else None)
        plan = proposed.get(named)
        elements = {e["id"]: e for e in (plan or {}).get("elements", [])}

        def fix(h):
            if isinstance(h, str) and h.startswith("element:") and h[8:] in elements:
                return plans.element_hash(elements[h[8:]])
            return h
        for a in call.get("accepts", []):
            a["hash"] = fix(a["hash"])
        if "hash" in call:
            call["hash"] = fix(call["hash"])
    return case


RUNS = {cid: plans.run(resolved(c)) for cid, c in CASES.items()}


def test_there_are_cases():
    assert len(CASES) >= 20


@pytest.mark.parametrize("cid", sorted(CASES))
def test_case_id_matches_its_file(cid):
    assert CASES[cid]["id"] == cid


@pytest.mark.parametrize("cid", sorted(CASES))
def test_calls(cid):
    case = CASES[cid]
    got = RUNS[cid]["calls"]
    for i, (call, want) in enumerate(zip(case["calls"], case["expected"]["calls"])):
        assert got[i] == want, (i, call["kind"])
    assert len(got) == len(case["expected"]["calls"])


@pytest.mark.parametrize("cid", sorted(CASES))
def test_final_states(cid):
    want = CASES[cid]["expected"]
    got = RUNS[cid]
    assert got["commands"] == want.get("commands", {})
    assert got["proposals"] == want.get("proposals", {})
    assert got["plans"] == want.get("plans", {})


@pytest.mark.parametrize("cid", sorted(c for c in CASES if CASES[c].get("control")))
def test_control_exists_and_differs(cid):
    control = CASES[CASES[cid]["control"]]
    assert control["id"] != cid
    assert control["expected"] != CASES[cid]["expected"]


@pytest.mark.parametrize("cid", sorted(CASES))
def test_never_a_declined_element(cid):
    # PN5, PN8: no command carries an element its plan's approval did not name.
    hub = RUNS[cid]["hub"]
    for pid, m in hub.plans.items():
        declined = set(m["declined"])
        for c in hub.commands.values():
            payload = c["payload"]
            if not isinstance(payload, dict) or payload.get("planId") != pid:
                continue
            ids = {e["id"] for e in payload.get("elements", [])}
            if "element" in payload:
                ids.add(payload["element"]["id"])
            assert not ids & declined, (pid, ids & declined)


@pytest.mark.parametrize("cid", sorted(CASES))
def test_every_command_comes_from_a_call(cid):
    # PN10: the hub schedules nothing; every command was made by a call at its time.
    case = resolved(CASES[cid])
    made_at = {call["at"] for call in case["calls"] if call["kind"] in CREATING}
    for c in RUNS[cid]["hub"].commands.values():
        assert c["createdAt"] in made_at


@pytest.mark.parametrize("cid", sorted(CASES))
def test_standing_insulin_and_carbs_carry_conditions(cid):
    # PN4: an accepted standing R3 or R4 element carries withdrawal criteria and the mitigation.
    case = CASES[cid]
    hub = RUNS[cid]["hub"]
    for pid, m in hub.plans.items():
        product = hub.case["instances"][m["destination"]]["product"]
        for e in m["elements"].values():
            if e["path"] == "standing" and hub._risk(product, e["kind"]) in ("R3", "R4"):
                cond = e.get("standingConditions") or {}
                assert cond.get("withdrawal") and cond.get("mitigation") == "reduced-portion", (case["id"], pid)


@pytest.mark.parametrize("cid", sorted(CASES))
def test_occurrence_operations_only_on_an_active_plan(cid):
    # PN12-PN14: an occurrence command is made only after the controller reported holding
    # the plan, and not after the plan was ending or ended.
    case = resolved(CASES[cid])
    hub = RUNS[cid]["hub"]
    held, closed = {}, {}
    plan_of_command = {m["commandId"]: pid for pid, m in hub.plans.items()}
    for call, got in zip(case["calls"], RUNS[cid]["calls"]):
        if call["kind"] == "report" and got.get("status") == 200 and call["state"] == "succeeded" \
                and call["command"] in plan_of_command:
            held.setdefault(plan_of_command[call["command"]], call["at"])
        if (call["kind"] == "endPlan" and got.get("status") == 201) or \
                (call["kind"] == "planReport" and got.get("status") == 200
                 and call.get("planState") == "ended"):
            closed.setdefault(call["plan"], call["at"])
        if call["kind"] in ("confirm", "approveOccurrence", "skip") and got.get("status") == 201:
            assert call["plan"] in held and held[call["plan"]] <= call["at"], (call["kind"], call["at"])
            assert call["plan"] not in closed, (call["kind"], call["at"])


@pytest.mark.parametrize("cid", sorted(CASES))
def test_occurrence_approval_within_its_window(cid):
    # PN13: an occurrence approval is accepted only inside the advance window, never by
    # the agent that proposed the plan.
    case = resolved(CASES[cid])
    hub = RUNS[cid]["hub"]
    window = case.get("maxAdvanceApprovalSeconds", 43200)
    for call, got in zip(case["calls"], RUNS[cid]["calls"]):
        if call["kind"] == "approveOccurrence" and got.get("status") == 201:
            assert call["occursAt"] - window <= call["at"] < call["occursAt"]
            p = hub.proposals[call["plan"]]
            assert not (call["subject"] == p["subject"] and hub._agent_proposal(p))
