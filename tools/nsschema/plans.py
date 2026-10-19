"""plans.py — what a hub does with a plan (SPEC-PLANS).

A reference decision function for rules PN1-PN18 of
docs/30-design/platform/spec/plans.md, built on the command and proposal
reference in commands.py: a plan proposed as a proposal with elements, its
structural floors, an approval that accepts elements by id and hash, the
command that carries the accepted plan, the hub's read-only mirror of what the
controller reports, and the occurrence operations (confirm, approve, skip) and
ending. It checks the cases under specs/sync/conformance/plans/ (format in
FORMAT.md there); it is not a hub. It has no code path driven by time: every
command comes from a call.
"""
from nsschema import commands
from nsschema.commands import FINAL, payload_hash, _route

RANK = {"R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4, "R5": 5, "R6": 6}
CLOSED = ("skip-requested", "skipped", "ran", "withdrawn", "refused", "missed")
HOLDS = ("approved", "active", "ending")  # the controller may hold the plan


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
        """PN3: the class the destination's definition declares; undeclared is R4."""
        return RANK[self.case.get("riskClasses", {}).get(product, {}).get(kind, "R4")]

    def _channel_version(self, tenant, product, channel, at):
        history = self.case.get("channelVersions", {}).get(tenant, {}).get(product, {}).get(channel)
        return _at(history, at)

    def _flag(self, call, name):
        return (self._subject(call) or {}).get(name, False)

    def _human_approver(self, call):
        """PN6: a person, or a delegate acting for them, never an agent's credential."""
        return self._flag(call, "person") or self._flag(call, "delegate")

    def _agent_proposal(self, p):
        return self.case["instances"][p["instance"]].get("agent", True)

    def _mirror(self, call):
        m = self.plans.get(call["plan"])
        if m is None or m["tenant"] != call["tenant"]:
            return None
        return m

    def _product(self, m):
        return self.case["instances"][m["destination"]]["product"]

    def _plan_command(self, call, m, payload, expires):
        made = dict(call, channel=m["channel"])
        result = self._new_command(made, payload, expires, routed=(m["destination"], None))
        result.pop("outstanding", None)  # PN8: plan operations answer without CM24's list
        return result

    def _cancel_occurrence_commands(self, plan, at, occurrence=None):
        """PN14, PN16: what is queued for an occurrence, or for the whole plan, is
        cancelled as CM25 cancels: final before hand-over, a request after it."""
        for cid, c in self.commands.items():
            payload = c["payload"]
            if not isinstance(payload, dict) or payload.get("planId") != plan:
                continue
            if "occurrence" not in payload or payload.get("skip"):
                continue
            if occurrence is not None and payload["occurrence"] != occurrence:
                continue
            state = self._settle(cid, at)
            if state == "pending":
                c["state"] = "cancelled"
            elif state not in FINAL:
                c["cancelRequested"] = True
                c.setdefault("cancelRequestedAt", at)

    def _outstanding(self, tenant, channel, at, exclude=None):
        """CM24, with PN8: an occurrence command is listed under each channel its
        plan's elements act on, as well as under the plan channel."""
        listed = super()._outstanding(tenant, channel, at, exclude)
        for cid, c in self.commands.items():
            payload = c["payload"]
            if cid == exclude or cid in listed["commands"] or c["tenant"] != tenant:
                continue
            m = self.plans.get(payload.get("planId")) if isinstance(payload, dict) else None
            if m is None or "occurrence" not in payload:
                continue
            if any(e["channel"] == channel for e in m["elements"].values()) \
                    and self._settle(cid, at) not in FINAL:
                listed["commands"].append(cid)
        return listed

    # --- PN1-PN4: proposing ----------------------------------------------------

    def _floors(self, plan, product):
        elements = plan["elements"]
        ids = [e["id"] for e in elements]
        if len(ids) != len(set(ids)) or not ids:
            return "invalid-plan"
        for e in elements:
            risk = self._risk(product, e["kind"])
            if risk == 6:
                return "local-only"
            if risk == 5 and e["path"] == "standing":
                return "standing-not-allowed"
            if risk in (3, 4) and e["path"] == "standing":
                cond = e.get("standingConditions") or {}
                criteria = cond.get("withdrawal") or []
                if (not criteria or cond.get("mitigation") != "reduced-portion"
                        or cond.get("companion") not in ids
                        or not all(c.get("signal") and c.get("evaluatedBy") in ("controller", "agent")
                                   for c in criteria)):
                    return "standing-conditions-required"
        bad = self._accepted_floors(elements, product)
        if bad:
            return bad
        if plan.get("endsAt") is None or plan["endsAt"] <= plan["startsAt"]:
            return "ends-required"
        if plan["endsAt"] - plan["startsAt"] > self.case.get("maxPlanSeconds", 30 * 86400):
            return "plan-too-long"
        return None

    def _accepted_floors(self, elements, product):
        """PN4: a standing R3 element only beside a standing R4 element, and a
        standing R3 or R4 element only beside its companion."""
        ids = {e["id"] for e in elements}
        standing = [e for e in elements if e["path"] == "standing"]
        if any(self._risk(product, e["kind"]) == 3 for e in standing) and \
                not any(self._risk(product, e["kind"]) == 4 for e in standing):
            return "standing-carbs-without-insulin"
        for e in standing:
            if self._risk(product, e["kind"]) in (3, 4) and \
                    (e.get("standingConditions") or {}).get("companion") not in ids:
                return "companion-declined"
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
        for e in call["plan"]["elements"]:
            holder, none = _route(self.case, call["tenant"], e["channel"], call["product"], call["at"])
            if not none and holder != destination:
                return {"status": 409, "code": "element-destination-differs"}
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
        product = p["product"]
        named = [elements[a["element"]] for a in accepts if a["element"] in elements]
        top = max([self._risk(product, e["kind"]) for e in named] or [0])
        if top >= 3 and not self._human_approver(call):
            return {"status": 403, "code": "not-person-or-delegate"}
        if not accepts:
            return {"status": 422, "code": "nothing-accepted"}
        for a in accepts:
            if a["element"] not in elements:
                return {"status": 422, "code": "unknown-element"}
        bad = self._accepted_floors(named, product)
        if bad:
            return {"status": 422, "code": bad}
        if p["state"] == "expired":
            return {"status": 409, "code": "proposal-expired"}
        if p["state"] != "open":
            return {"status": 409, "code": "proposal-closed"}
        for a in accepts:
            if element_hash(elements[a["element"]]) != a["hash"]:
                return {"status": 409, "code": "hash-mismatch"}
        reviewed = {r for s, r in p.get("reviews", []) if s != p["subject"]}
        required = list(p["payload"].get("requiredReviews", []))
        if any(r not in reviewed for r in required) or (top >= 3 and not reviewed):
            return {"status": 409, "code": "review-required"}
        destination, code = _route(self.case, p["tenant"], p["channel"], product, call["at"])
        if code:
            return {"status": 409, "code": code}
        if destination != p["destination"]:
            return {"status": 409, "code": "destination-changed"}
        if self._definition(destination, call["at"]) != p["definitionId"]:
            return {"status": 409, "code": "definition-changed"}
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
            "elements": {e["id"]: e for e in accepted}, "startsAt": p["payload"]["startsAt"],
            "endsAt": p["payload"]["endsAt"],
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

    def cancel(self, call):
        """CM25, with PN16: an end command is never cancelled."""
        c = self.commands.get(call["command"])
        if c is not None and c["tenant"] == call["tenant"] and isinstance(c["payload"], dict) \
                and c["payload"].get("end") and c["payload"].get("planId") in self.plans:
            return {"status": 409, "code": "not-cancellable"}
        return super().cancel(call)

    def planReport(self, call):
        """PN11, PN15: occurrence states and the plan's end, from the destination only.
        A report on a plan the controller may hold also shows that it holds it."""
        m = self._mirror(call)
        if m is None:
            return {"status": 404}
        inst = self.case["instances"][m["destination"]]
        if inst["subject"] != call["subject"]:
            return {"status": 403, "code": "not-registration-owner"}
        if m["state"] not in HOLDS:
            return {"status": 409, "code": "plan-not-active"}
        if m["state"] == "approved":
            m["state"] = "active"
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
        return {"status": 200, "state": m["state"],
                "accepted": m["accepted"], "declined": m["declined"],
                "occurrences": dict(m["occurrences"])}

    # --- PN12-PN14: occurrences ------------------------------------------------

    def _occurrence_checks(self, m, call):
        """PN12's 409s, in order: the plan, then the occurrence's time, then its state."""
        if m["state"] != "active":
            return {"status": 409, "code": "plan-not-active"}
        if call["at"] >= m["endsAt"]:
            return {"status": 409, "code": "plan-ended"}
        return None

    def _occurrence_time(self, m, call):
        if not m["startsAt"] <= call["occursAt"] < m["endsAt"]:
            return {"status": 409, "code": "occurrence-outside-plan"}
        if call["at"] < call["occursAt"] - self.case.get("maxAdvanceApprovalSeconds", 43200):
            return {"status": 409, "code": "too-early"}
        if call["at"] >= call["occursAt"]:
            return {"status": 409, "code": "occurrence-passed"}
        if m["occurrences"].get(call["occurrence"]) in CLOSED:
            return {"status": 409, "code": "occurrence-closed"}
        return None

    def confirm(self, call):
        """PN12: the proposer, from its proposing instance, under the plan's grant."""
        m = self._mirror(call)
        if m is None:
            return {"status": 404}
        if call["subject"] != m["proposer"] or call.get("instance") != m["proposerInstance"]:
            return {"status": 403, "code": "outside-grant"}
        inst = self.case["instances"][m["proposerInstance"]]
        proposes = _at(inst.get("proposesChanges"), call["at"], inst.get("proposes", []))
        if not self._permitted(call, "api:proposals:create") or m["channel"] not in proposes:
            return {"status": 403, "code": "role-not-granted"}
        bad = self._occurrence_checks(m, call) or self._occurrence_time(m, call)
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
        element = m["elements"].get(call["element"])
        risk = self._risk(self._product(m), element["kind"]) if element else 0
        if risk >= 3 and not self._human_approver(call):
            return {"status": 403, "code": "not-person-or-delegate"}
        if risk == 5 and not self._flag(call, "person"):
            return {"status": 403, "code": "person-required"}
        bad = self._occurrence_checks(m, call)
        if bad:
            return bad
        if element is None or element["path"] != "per-occurrence":
            return {"status": 409, "code": "not-per-occurrence"}
        if element_hash(element) != call["hash"]:
            return {"status": 409, "code": "hash-mismatch"}
        bad = self._occurrence_time(m, call)
        if bad:
            return bad
        m["occurrences"][call["occurrence"]] = "approved"
        payload = {"planId": call["plan"], "occurrence": call["occurrence"],
                   "element": element}
        return self._plan_command(call, m, payload, call["occursAt"])

    def _may_stop(self, call, m):
        """PN14, PN16: the person, the plan's approver, or its proposer from its instance."""
        return (self._flag(call, "person") or call["subject"] == m["approver"]
                or (call["subject"] == m["proposer"]
                    and call.get("instance") == m["proposerInstance"]))

    def skip(self, call):
        """PN14."""
        m = self._mirror(call)
        if m is None:
            return {"status": 404}
        if not self._may_stop(call, m):
            return {"status": 403, "code": "not-authorised"}
        if m["state"] not in ("approved", "active"):
            return {"status": 409, "code": "plan-not-active"}
        if call["at"] >= m["endsAt"]:
            return {"status": 409, "code": "plan-ended"}
        if m["occurrences"].get(call["occurrence"]) in CLOSED:
            return {"status": 409, "code": "occurrence-closed"}
        m["occurrences"][call["occurrence"]] = "skip-requested"
        self._cancel_occurrence_commands(call["plan"], call["at"], call["occurrence"])
        payload = {"planId": call["plan"], "occurrence": call["occurrence"], "skip": True}
        return self._plan_command(call, m, payload,
                                  call["at"] + self.case.get("maxExpirySeconds", 3600))

    # --- PN15-PN16: ending -------------------------------------------------------

    def endPlan(self, call):
        """PN16: the person, the approver or the proposer ends a plan the controller may
        hold; while it is ending, each end sends the command again."""
        m = self._mirror(call)
        if m is None:
            return {"status": 404}
        if not self._may_stop(call, m):
            return {"status": 403, "code": "not-authorised"}
        if m["state"] not in HOLDS:
            return {"status": 409, "code": "plan-not-active"}
        m["state"] = "ending"
        self._cancel_occurrence_commands(call["plan"], call["at"])
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
