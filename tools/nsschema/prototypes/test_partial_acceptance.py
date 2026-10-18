"""Partial acceptance prototype: three ways to bind an approval that accepts
part of a plan (docs/30-design/platform/partial-acceptance-prototype-2026-10-18.md).

Each case under specs/sync/prototypes/partial-acceptance/ carries
hand-authored expectations for every variant; the prototype must reproduce
every step's result and the final state. Two invariants hold on every case
and on a generated sweep, except where a case declares a faulty hub, and
there they are expected to break in the variants that build a subset.
"""
import copy
import itertools
import json

import pytest
import yaml

from nsschema import corpus
from nsschema.prototypes import partial_acceptance as pa

CASES_DIR = corpus.repo_root() / "specs" / "sync" / "prototypes" / "partial-acceptance"
CASES = {p.stem: yaml.safe_load(p.read_text()) for p in sorted(CASES_DIR.glob("*.yaml"))}
PAIRS = [(cid, v) for cid in sorted(CASES) for v in pa.VARIANTS]


def test_there_are_cases():
    assert len(CASES) >= 10


@pytest.mark.parametrize("cid", sorted(CASES))
def test_case_id_matches_its_file(cid):
    assert CASES[cid]["id"] == cid


@pytest.mark.parametrize("cid", sorted(CASES))
def test_every_variant_expected_once(cid):
    named = [v for key in CASES[cid]["expected"] for v in key.split(",")]
    assert sorted(named) == sorted(pa.VARIANTS)


@pytest.mark.parametrize("cid,variant", PAIRS)
def test_steps(cid, variant):
    got = pa.run(CASES[cid], variant)["steps"]
    want = pa.expected_for(CASES[cid], variant)["steps"]
    for i, (g, w) in enumerate(zip(got, want)):
        assert g == w, i
    assert len(got) == len(want)


@pytest.mark.parametrize("cid,variant", PAIRS)
def test_final_state(cid, variant):
    result = pa.run(CASES[cid], variant)
    want = pa.expected_for(CASES[cid], variant)
    assert result["proposals"] == want["proposals"]
    assert result["enacted"] == want["enacted"]


def violations(world):
    """The two invariants: the controller never enacts an element no approval
    named, and every enacted element's hash is the hash its approval named."""
    found = []
    for cid, elements in world.enacted.items():
        named = world.commands[cid]["named"]
        for e in elements:
            if e["id"] not in named:
                found.append(("unnamed", cid, e["id"]))
            elif pa.h(e) != named[e["id"]]:
                found.append(("hash", cid, e["id"]))
    return found


@pytest.mark.parametrize("cid,variant", [(c, v) for c, v in PAIRS if not CASES[c].get("hubFault")])
def test_invariants(cid, variant):
    assert violations(pa.run(CASES[cid], variant)["world"]) == []


@pytest.mark.parametrize("variant", ["V1", "V2"])
def test_faulty_hub_breaks_the_invariant(variant):
    # Non-vacuity, and the CM10 limit: a hub that builds the command from the
    # whole proposal binds it consistently, and the controller cannot tell.
    found = violations(pa.run(CASES["declined-built-in-by-hub"], variant)["world"])
    assert found == [("unnamed", "c1", "meal")]


def test_faulty_hub_has_nothing_to_break_in_v3():
    assert violations(pa.run(CASES["declined-built-in-by-hub"], "V3")["world"]) == []


def test_reordered_keys_case_is_byte_different():
    # The reordered-keys case means something only if the bytes differ.
    case = CASES["reordered-keys"]
    proposed = case["plan"]["elements"][1]["content"]
    shown = case["steps"][1]["alter"]["meal"]
    assert json.dumps(proposed) != json.dumps(shown)
    assert pa.canonical_json(proposed) == pa.canonical_json(shown)


# --- a generated sweep: every acceptance, every tamper, every variant -----

PLAN = CASES["accept-all"]["plan"]
IDS = pa.ids_of(PLAN)
OTHER = {"kind": "meal", "time": "18:00", "carbs": {"grams": 70}, "bolus": "with-meal"}
TAMPERS = [None, {"op": "reorder"}, {"op": "add", "element": {"id": "snack", "content": OTHER}}] + [
    t for i in IDS for t in ({"op": "alter", "element": i, "content": OTHER},
                             {"op": "drop", "element": i}, {"op": "duplicate", "element": i})]
ACCEPTS = [list(s) for n in range(len(IDS) + 1) for s in itertools.combinations(IDS, n)]


@pytest.mark.parametrize("variant", pa.VARIANTS)
def test_sweep(variant):
    # A tamper that touches an element not in the command changes nothing; the
    # controller enacts exactly when the approval is accepted and what arrives
    # is canonically what the hub sent.
    enacted = 0
    for accept, tamper in itertools.product(ACCEPTS, TAMPERS):
        approved = bool(accept) and (variant != "V3" or accept == IDS)
        case = {"plan": copy.deepcopy(PLAN), "steps": [
            {"kind": "propose", "subject": "agent"},
            {"kind": "approve", "subject": "person", "proposal": "p1", "accept": accept}]}
        if approved:
            case["steps"].append(
                {"kind": "deliver", "command": "c1", **({"tamper": tamper} if tamper else {})})
        result = pa.run(case, variant)
        assert violations(result["world"]) == [], (accept, tamper)
        sent = pa.restrict(PLAN, accept)
        intact = tamper is None or pa.canonical_json(pa.tamper(sent, tamper)) == pa.canonical_json(sent)
        assert bool(result["enacted"]) == (approved and intact), (accept, tamper)
        if result["enacted"]:
            enacted += 1
            assert result["enacted"]["c1"] == accept
    assert enacted > 0
