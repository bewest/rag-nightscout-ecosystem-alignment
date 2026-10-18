"""plans.py — what a hub does with a plan (SPEC-PLANS).

A reference decision function for rules PN1-PN16 of
docs/30-design/platform/spec/plans.md, built on the command and proposal
reference in commands.py: a plan proposed as a proposal with elements, its
structural floors, an approval that accepts elements by id and hash, the
command that carries the accepted plan, the hub's read-only mirror of what the
controller reports, and the occurrence operations (confirm, approve, skip) and
ending. It checks the cases under specs/sync/conformance/plans/ (format in
FORMAT.md there); it is not a hub. It never creates a command at an
occurrence's time: every command comes from a call.
"""
from nsschema import commands
from nsschema.commands import FINAL, payload_hash, _route

STANDING_FLOOR = ("R3", "R4")


def element_hash(element):
    """PN2: an element's hash, by CM1's rule."""
    return payload_hash(element)


def _at(history, at, default=None):
    current = default
    for start, value in history or []:
        if start <= at:
            current = value
    return current


class Hub(commands.Hub):
    def __init__(self, case):
        super().__init__(case)
        self.plans = {}

    # --- helpers -------------------------------------------------------------

    def _definition(self, instance, at):
        inst = self.case["instances"][instance]
        return _at(inst.get("definitionChanges"), at, inst["definitionId"])

    def _risk(self, product, kind):
        """PN3: the definition's class; undeclared is R4."""
        return self.case.get("riskClasses", {}).get(product, {}).get(kind, "R4")

    def _channel_version(self, tenant, product, channel, at):
        history = self.case.get("channelVersions", {}).get(tenant, {}).get(product, {}).get(channel)
        return _at(history, at)

    def _is_person(self, call):
        return (self._subject(call) or {}).get("person", False)

    def _agent_proposal(self, p):
        return self.case["instances"][p["instance"]].get("agent", True)

    def _mirror(self, call):
        m = self.plans.get(call["plan"])
        if m is None or m["tenant"] != call["tenant"]:
            return None
        return m

    def _plan_command(self, call, m, payload, expires):
        made = dict(call, channel=m["channel"])
        result = self._new_command(made, payload, expires, routed=(m["destination"], None))
        result.pop("outstanding", None)  # PN8: plan operations answer without CM24's list
        return result

    # --- PN1-PN4: proposing ----------------------------------------------------

    def _floors(self, plan, product):
        ids = [e["id"] for e in plan["elements"]]
        if len(ids) != len(set(ids)) or not ids:
            return "invalid-plan"
        for e in plan["elements"]:
            risk = self._risk(product, e["kind"])
            if risk == "R6":
                return "local-only"
            if risk == "R5" and e["path"] == "standing":
                return "standing-not-allowed"
            if risk in STANDING_FLOOR and e["path"] == "standing":
                cond = e.get("standingConditions") or {}
                criteria = cond.get("withdrawal") or []
                if (not criteria or cond.get("mitigation") != "reduced-portion"
                        or not all(c.get("signal") and c.get("evaluatedBy") in ("controller", "agent")
                                   for c in criteria)):
                    return "standing-conditions-required"
        if plan.get("endsAt") is None or plan["endsAt"] <= plan["startsAt"]:
            return "ends-required"
        if plan["endsAt"] - plan["startsAt"] > self.case.get("maxPlanSeconds", 30 * 86400):
            return "plan-too-long"
        return None

    def proposePlan(self, call):
        """PN1-PN4, with CM11-CM12's checks."""
        if not self._permitted(call, "api:proposals:create"):
            return {"status": 403, "code": "not-authorised"}
        inst = self.case["instances"].get(call["instance"])
        if inst is None or inst["tenant"] != call["tenant"]:
            return {"status": 404}
        if inst["subject"] != call["subject"]:
            return {"status": 403, "code": "not-registration-owner"}
        if call["channel"] not in inst.get("proposes", []):
            return {"status": 403, "code": "role-not-granted"}
        if call.get("expiresAt") is None or call["expiresAt"] <= call["at"]:
            return {"status": 422, "code": "expiry-required"}
        if call["expiresAt"] - call["at"] > self.case.get("maxProposalSeconds", 14 * 86400):
            return {"status": 422, "code": "expiry-too-long"}
        if call.get("basedOn") is None:
            return {"status": 422, "code": "based-on-required"}
        if not call.get("product"):
            return {"status": 422, "code": "product-required"}
        bad = self._floors(call["plan"], call["product"])
        if bad:
            return {"status": 422, "code": bad}
        destination, code = _route(self.case, call["tenant"], call["channel"], call["product"],
                                   call["at"])
        if code:
            return {"status": 409, "code": code}
        pid = "p%d" % (len(self.proposals) + 1)
        self.proposals[pid] = dict(
            call, kind="plan", state="open", payload=call["plan"],
            payloadHash=payload_hash(call["plan"]), destination=destination,
            definitionId=self._definition(destination, call["at"]))
        return {"status": 201, "proposalId": pid}

    def evaluate(self, call):
        """CM16; PN6 counts a named review from a subject other than the proposer."""
        result = super().evaluate(call)
        if result.get("status") == 201 and call.get("review"):
            self.proposals[call["proposal"]].setdefault("reviews", []).append(
                (call["subject"], call["review"]))
        return result

    # --- PN5-PN8: approving ----------------------------------------------------

    def approvePlan(self, call):
        p = self._proposal(call)
        if p is None or p.get("kind") != "plan":
            return {"status": 404}
        if not self._permitted(call, "api:commands:create"):
            return {"status": 403, "code": "not-authorised"}
        if call["subject"] == p["subject"] and self._agent_proposal(p):
            return {"status": 403, "code": "self-approval"}
        elements = {e["id"]: e for e in p["payload"]["elements"]}
        accepts = call.get("accepts") or []
        if not accepts:
            return {"status": 422, "code": "nothing-accepted"}
        for a in accepts:
            if a["element"] not in elements:
                return {"status": 422, "code": "unknown-element"}
        if p["state"] == "expired":
            return {"status": 409, "code": "proposal-expired"}
        if p["state"] != "open":
            return {"status": 409, "code": "proposal-closed"}
        for a in accepts:
            if element_hash(elements[a["element"]]) != a["hash"]:
                return {"status": 409, "code": "hash-mismatch"}
        reviewed = {r for s, r in p.get("reviews", []) if s != p["subject"]}
        if any(r not in reviewed for r in p["payload"].get("requiredReviews", [])):
            return {"status": 409, "code": "review-required"}
        destination, code = _route(self.case, p["tenant"], p["channel"], p.get("product"), call["at"])
        if code:
            return {"status": 409, "code": code}
        if destination != p["destination"]:
            return {"status": 409, "code": "destination-changed"}
        if self._definition(destination, call["at"]) != p["definitionId"]:
            return {"status": 409, "code": "definition-changed"}
        product = self.case["instances"][destination]["product"]
        accepted_ids = [a["element"] for a in accepts]
        for eid in accepted_ids:
            channel = elements[eid]["channel"]
            if self._channel_version(p["tenant"], product, channel, call["at"]) \
                    != p["basedOn"].get(channel):
                return {"status": 409, "code": "state-changed"}
        p["state"] = "approved"
        accepted = [e for e in p["payload"]["elements"] if e["id"] in accepted_ids]
        payload = dict(p["payload"], elements=accepted, planId=call["proposal"])
        expires = min(p["payload"]["endsAt"], call["at"] + self.case.get("maxExpirySeconds", 3600))
        made = dict(call, channel=p["channel"])
        result = self._new_command(made, payload, expires, proposal_id=call["proposal"],
                                   routed=(destination, None))
        self.plans[call["proposal"]] = {
            "tenant": p["tenant"], "channel": p["channel"], "destination": destination,
            "state": "approved", "accepted": accepted_ids,
            "declined": [e for e in elements if e not in accepted_ids],
            "elements": {e["id"]: e for e in accepted}, "endsAt": p["payload"]["endsAt"],
            "proposer": p["subject"], "proposerInstance": p["instance"],
            "approver": call["subject"], "commandId": result["commandId"], "occurrences": {}}
        result.pop("outstanding", None)
        return result

    # --- PN9-PN11: the controller holds it; the mirror -------------------------

    def report(self, call):
        """CM7-CM9; PN9 moves the mirror from the plan command's outcome."""
        result = super().report(call)
        if result.get("status") == 200:
            for m in self.plans.values():
                if m["commandId"] == call["command"] and m["state"] == "approved":
                    if call["state"] == "succeeded":
                        m["state"] = "active"
                    elif call["state"] in ("refused", "failed"):
                        m["state"] = "refused"
        return result

    def planReport(self, call):
        """PN11, PN15: occurrence states and the plan's end, from the destination only."""
        m = self._mirror(call)
        if m is None:
            return {"status": 404}
        inst = self.case["instances"][m["destination"]]
        if inst["subject"] != call["subject"]:
            return {"status": 403, "code": "not-registration-owner"}
        if m["state"] not in ("active", "ending"):
            return {"status": 409, "code": "plan-not-active"}
        if call.get("planState") == "ended":
            m["state"] = "ended"
        if call.get("occurrence"):
            m["occurrences"][call["occurrence"]] = call["occurrenceState"]
        return {"status": 200}

    def readPlan(self, call):
        if not any(self._permitted(call, p) for p in
                   ("api:commands:read", "api:commands:create", "api:proposals:read")):
            return {"status": 403, "code": "not-authorised"}
        m = self._mirror(call)
        if m is None:
            return {"status": 404}
        return {"status": 200, "state": self._plan_state(m, call["at"]),
                "accepted": m["accepted"], "declined": m["declined"],
                "occurrences": dict(m["occurrences"])}

    def _plan_state(self, m, at):
        return m["state"]

    # --- PN12-PN14: occurrences ------------------------------------------------

    def _occurrence_guard(self, m, call):
        if m["state"] != "active":
            return {"status": 409, "code": "plan-not-active"}
        if call["at"] >= m["endsAt"]:
            return {"status": 409, "code": "plan-ended"}
        return None

    def confirm(self, call):
        """PN12: the proposer, from its proposing instance, under the plan's grant."""
        m = self._mirror(call)
        if m is None:
            return {"status": 404}
        if call["subject"] != m["proposer"] or call.get("instance") != m["proposerInstance"]:
            return {"status": 403, "code": "outside-grant"}
        bad = self._occurrence_guard(m, call)
        if bad:
            return bad
        m["occurrences"][call["occurrence"]] = "confirmed"
        payload = {"planId": call["plan"], "occurrence": call["occurrence"], "confirm": True}
        return self._plan_command(call, m, payload, call["occursAt"])

    def approveOccurrence(self, call):
        """PN13: a per-occurrence element, approved within the advance window."""
        m = self._mirror(call)
        if m is None:
            return {"status": 404}
        if not self._permitted(call, "api:commands:create"):
            return {"status": 403, "code": "not-authorised"}
        p = self.proposals[call["plan"]]
        if call["subject"] == p["subject"] and self._agent_proposal(p):
            return {"status": 403, "code": "self-approval"}
        bad = self._occurrence_guard(m, call)
        if bad:
            return bad
        element = m["elements"].get(call["element"])
        if element is None or element["path"] != "per-occurrence":
            return {"status": 409, "code": "not-per-occurrence"}
        if element_hash(element) != call["hash"]:
            return {"status": 409, "code": "hash-mismatch"}
        if call["at"] < call["occursAt"] - self.case.get("maxAdvanceApprovalSeconds", 43200):
            return {"status": 409, "code": "too-early"}
        if call["at"] >= call["occursAt"]:
            return {"status": 409, "code": "occurrence-passed"}
        m["occurrences"][call["occurrence"]] = "approved"
        payload = {"planId": call["plan"], "occurrence": call["occurrence"],
                   "element": element}
        return self._plan_command(call, m, payload, call["occursAt"])

    def _person_or_approver(self, call, m):
        return self._is_person(call) or call["subject"] == m["approver"]

    def skip(self, call):
        """PN14."""
        m = self._mirror(call)
        if m is None:
            return {"status": 404}
        if not self._person_or_approver(call, m):
            return {"status": 403, "code": "not-authorised"}
        bad = self._occurrence_guard(m, call)
        if bad:
            return bad
        m["occurrences"][call["occurrence"]] = "skip-requested"
        payload = {"planId": call["plan"], "occurrence": call["occurrence"], "skip": True}
        return self._plan_command(call, m, payload,
                                  call["at"] + self.case.get("maxExpirySeconds", 3600))

    # --- PN15-PN16: ending -------------------------------------------------------

    def endPlan(self, call):
        """PN16: the person or the approver ends an active plan."""
        m = self._mirror(call)
        if m is None:
            return {"status": 404}
        if not self._person_or_approver(call, m):
            return {"status": 403, "code": "not-authorised"}
        if m["state"] != "active":
            return {"status": 409, "code": "plan-not-active"}
        m["state"] = "ending"
        payload = {"planId": call["plan"], "end": True}
        return self._plan_command(call, m, payload,
                                  call["at"] + self.case.get("maxExpirySeconds", 3600))


def run(case):
    """Replay a case's calls; return each call's result and, at `end`, the
    states of commands, proposals and plan mirrors."""
    hub = Hub(case)
    results = [getattr(hub, call["kind"])(call) for call in case["calls"]]
    end = case.get("end", max(c["at"] for c in case["calls"]))
    cmds = {}
    for cid, c in hub.commands.items():
        cmds[cid] = {"state": hub._public(cid, end), "destination": c["destination"]}
        if c["proposalId"]:
            cmds[cid]["proposalId"] = c["proposalId"]
    proposals = {}
    for pid in hub.proposals:
        hub._proposal({"proposal": pid, "tenant": hub.proposals[pid]["tenant"], "at": end})
        proposals[pid] = {"state": hub.proposals[pid]["state"]}
    plans = {pid: {"state": m["state"], "accepted": m["accepted"], "declined": m["declined"],
                   "occurrences": dict(m["occurrences"])}
             for pid, m in hub.plans.items()}
    return {"calls": results, "commands": cmds, "proposals": proposals, "plans": plans,
            "hub": hub}
