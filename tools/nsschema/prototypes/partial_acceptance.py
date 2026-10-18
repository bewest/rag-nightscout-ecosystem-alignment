"""partial_acceptance.py — prototype: binding an approval that accepts part of a plan.

Three ways a hub could bind an approval that accepts some elements of a
proposed plan and declines others (command queue note §5 decision 4; command
journeys PL1.3 and PL5.3). It is a prototype for the assessment in
docs/30-design/platform/partial-acceptance-prototype-2026-10-18.md, not a
hub and not the reference in nsschema/commands.py: it models only proposing,
approving, delivering and enacting, with CM14's self-approval refusal, CM13's
"only an open proposal changes" and CM21's "a controller decides each
commandId once". Routing, expiry, tenants and basedOn are left out because
they do not differ between the variants.

A plan payload is {"frame": {...}, "elements": [{"id": ..., "content": {...}}, ...]}:
the frame holds what every element shares (trigger, days, end date), and each
element is one separately acceptable part.

  V1  hash per element: the proposal carries a hash of the frame and of each
      element; the approval names the frame hash and each accepted element's
      id and hash; the controller recomputes each hash.
  V2  hash of the accepted subset: the approval sends the accepted subset;
      the hub checks it against the proposal and binds the command to the
      hash of the subset (in the proposal's order); the controller
      recomputes one hash, as CM10 does today.
  V3  no partial acceptance: an approval accepts the whole proposal (CM13 as
      written); declining part means rejecting and a new proposal.

Cases under specs/sync/prototypes/partial-acceptance/ drive all three
through one scenario runner, `run(case, variant)`.
"""
import copy
import hashlib

from nsschema.negotiate import canonical_json

VARIANTS = ("V1", "V2", "V3")


def h(value):
    """CM1's hash: sha256 over the RFC 8785 canonical JSON of the value."""
    return "sha256:%s" % hashlib.sha256(canonical_json(value)).hexdigest()


def ids_of(payload):
    return [e["id"] for e in payload["elements"]]


def restrict(payload, ids):
    """The plan with only the named elements, in the proposal's order."""
    return {"frame": payload["frame"],
            "elements": [e for e in payload["elements"] if e["id"] in ids]}


def refuse(status, code):
    return {"status": status, "code": code}


def _accepted_ok(ids):
    if not ids:
        return refuse(422, "nothing-accepted")
    if len(set(ids)) != len(ids):
        return refuse(422, "duplicate-element")
    return None


# --- what the hub binds a command to --------------------------------------

def bind_v1(payload):
    return {"frameHash": h(payload["frame"]),
            "elementHashes": {e["id"]: h(e) for e in payload["elements"]}}


def bind_whole(payload):
    return {"payloadHash": h(payload)}


# --- the hub's approval decision, one per variant -------------------------
# Each returns a refusal, or (payload for the command, what the approval named:
# {element id: hash}).

def approve_v1(proposal, msg):
    ids = [a["id"] for a in msg["accepted"]]
    bad = _accepted_ok(ids)
    if bad:
        return bad
    hashes = proposal["elementHashes"]
    if msg["frameHash"] != proposal["frameHash"]:
        return refuse(409, "hash-mismatch")
    for a in msg["accepted"]:
        if a["id"] not in hashes:
            return refuse(409, "unknown-element")
        if a["hash"] != hashes[a["id"]]:
            return refuse(409, "hash-mismatch")
    return restrict(proposal["payload"], ids), {a["id"]: a["hash"] for a in msg["accepted"]}


def approve_v2(proposal, msg):
    subset = msg["subset"]
    ids = ids_of(subset)
    bad = _accepted_ok(ids)
    if bad:
        return bad
    payload = proposal["payload"]
    if canonical_json(subset["frame"]) != canonical_json(payload["frame"]):
        return refuse(409, "hash-mismatch")
    by_id = {e["id"]: e for e in payload["elements"]}
    for e in subset["elements"]:
        if e["id"] not in by_id:
            return refuse(409, "unknown-element")
        if canonical_json(e) != canonical_json(by_id[e["id"]]):
            return refuse(409, "hash-mismatch")
    return restrict(payload, ids), {e["id"]: h(e) for e in subset["elements"]}


def approve_v3(proposal, msg):
    if set(msg["accepted"]) < set(ids_of(proposal["payload"])):
        return refuse(422, "partial-not-supported")
    if msg["payloadHash"] != proposal["payloadHash"]:
        return refuse(409, "hash-mismatch")
    payload = proposal["payload"]
    return payload, {e["id"]: h(e) for e in payload["elements"]}


# --- the controller's check before it enacts ------------------------------

def check_v1(received, binding):
    got = ids_of(received)
    bound = binding["elementHashes"]
    if h(received["frame"]) != binding["frameHash"]:
        return "hash-mismatch"
    if len(set(got)) != len(got):
        return "duplicate-element"
    if any(i not in bound for i in got):
        return "unbound-element"
    if any(i not in got for i in bound):
        return "missing-element"
    if any(h(e) != bound[e["id"]] for e in received["elements"]):
        return "hash-mismatch"
    return None


def check_whole(received, binding):
    return None if h(received) == binding["payloadHash"] else "hash-mismatch"


APPROVE = {"V1": approve_v1, "V2": approve_v2, "V3": approve_v3}
BIND = {"V1": bind_v1, "V2": bind_whole, "V3": bind_whole}
CHECK = {"V1": check_v1, "V2": check_whole, "V3": check_whole}


# --- the approver's client: what the person saw, as each variant sends it --

def _reversed_keys(value):
    """The same value with every object's keys in reverse order: different
    bytes, the same canonical JSON."""
    if isinstance(value, dict):
        return {k: _reversed_keys(value[k]) for k in reversed(list(value))}
    if isinstance(value, list):
        return [_reversed_keys(v) for v in value]
    return value


def approver_view(proposal, step):
    """The frame and the accepted elements as the approver's display holds
    them. `alter` and `claimed` give content the display shows in place of the
    proposal's (a stale or tampered display, or an element that does not
    exist); `reorder` gives the same content with keys in another order;
    `reverseElements` lists the accepted elements in another order."""
    by_id = {e["id"]: e["content"] for e in proposal["payload"]["elements"]}
    alter = dict(step.get("claimed", {}), **step.get("alter", {}))
    frame = step.get("frameView", proposal["payload"]["frame"])
    accept = step.get("accept", ids_of(proposal["payload"]))
    elements = [{"id": i, "content": alter.get(i, by_id.get(i))} for i in accept]
    view = {"frame": frame, "elements": elements}
    if step.get("reorder"):
        view = _reversed_keys(view)
    if step.get("reverseElements"):
        view["elements"] = list(reversed(view["elements"]))
    return accept, view


def approval_message(variant, accept, view):
    if variant == "V1":
        return {"frameHash": h(view["frame"]),
                "accepted": [{"id": e["id"], "hash": h(e)} for e in view["elements"]]}
    if variant == "V2":
        return {"subset": view}
    return {"accepted": accept, "payloadHash": h(view)}


# --- tampering in transit -------------------------------------------------

def tamper(payload, op):
    p = copy.deepcopy(payload)
    kind = op["op"]
    if kind == "alter":
        for e in p["elements"]:
            if e["id"] == op["element"]:
                e["content"] = op["content"]
    elif kind == "add":
        p["elements"].append(op["element"])
    elif kind == "drop":
        p["elements"] = [e for e in p["elements"] if e["id"] != op["element"]]
    elif kind == "duplicate":
        p["elements"].extend(e for e in payload["elements"] if e["id"] == op["element"])
    elif kind == "reorder":
        p = _reversed_keys(p)
    else:
        raise ValueError(kind)
    return p


# --- the scenario runner --------------------------------------------------

class World:
    """One hub and one controller, for one variant."""

    def __init__(self, case, variant):
        self.case = case
        self.variant = variant
        self.proposals = {}
        self.commands = {}
        self.decided = set()       # CM21: commandIds the controller has decided
        self.enacted = {}          # commandId -> elements enacted

    def propose(self, step):
        payload = copy.deepcopy(self.case["plan"])
        if "elements" in step:
            payload = restrict(payload, step["elements"])
        if "duplicate" in step:
            payload["elements"] += [e for e in payload["elements"] if e["id"] == step["duplicate"]]
        if len(set(ids_of(payload))) != len(ids_of(payload)):
            return refuse(422, "duplicate-element")
        pid = "p%d" % (len(self.proposals) + 1)
        self.proposals[pid] = {
            "subject": step["subject"], "payload": payload, "state": "open",
            "payloadHash": h(payload), "frameHash": h(payload["frame"]),
            "elementHashes": {e["id"]: h(e) for e in payload["elements"]}}
        return {"status": 201, "proposalId": pid}

    def approve(self, step):
        p = self.proposals[step["proposal"]]
        if step["subject"] == p["subject"]:
            return refuse(403, "self-approval")                    # CM14
        if p["state"] != "open":
            return refuse(409, "proposal-closed")                  # CM13
        accept, view = approver_view(p, step)
        decided = APPROVE[self.variant](p, approval_message(self.variant, accept, view))
        if isinstance(decided, dict):
            return decided                                         # proposal stays open
        payload, named = decided
        if self.case.get("hubFault") == "include-declined":
            payload = p["payload"]                                 # a faulty hub
        p["state"] = "approved"
        p["accepted"] = [i for i in ids_of(p["payload"]) if i in named]
        p["declined"] = [i for i in ids_of(p["payload"]) if i not in named]
        cid = "c%d" % (len(self.commands) + 1)
        self.commands[cid] = {"proposalId": step["proposal"], "payload": payload,
                              "binding": BIND[self.variant](payload), "named": named}
        return {"status": 201, "commandId": cid}

    def reject(self, step):
        p = self.proposals[step["proposal"]]
        if p["state"] != "open":
            return refuse(409, "proposal-closed")
        p["state"] = "rejected"
        return {"status": 200}

    def deliver(self, step):
        cid = step["command"]
        c = self.commands[cid]
        received = tamper(c["payload"], step["tamper"]) if "tamper" in step else c["payload"]
        if cid in self.decided:
            return {"state": "ignored", "reason": "duplicate"}     # CM21
        self.decided.add(cid)
        reason = CHECK[self.variant](received, c["binding"])
        if reason:
            return {"state": "refused", "reason": reason}
        self.enacted[cid] = copy.deepcopy(received["elements"])
        return {"state": "succeeded", "elements": ids_of(received)}


def run(case, variant):
    """Replay a case's steps for one variant (skipping steps whose `only`
    names other variants); return each step's result and the final state."""
    world = World(case, variant)
    steps = [s for s in case["steps"] if variant in s.get("only", VARIANTS)]
    results = [getattr(world, s["kind"])(s) for s in steps]
    proposals = {}
    for pid, p in world.proposals.items():
        row = {"state": p["state"]}
        if p["state"] == "approved":
            row.update(accepted=p["accepted"], declined=p["declined"])
        proposals[pid] = row
    enacted = {cid: ids_of({"elements": els}) for cid, els in world.enacted.items()}
    return {"steps": results, "proposals": proposals, "enacted": enacted, "world": world}


def expected_for(case, variant):
    """Expectations are keyed by variant names joined with commas."""
    for key, want in case["expected"].items():
        if variant in key.split(","):
            return want
    raise KeyError(variant)
