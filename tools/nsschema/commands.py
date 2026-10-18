"""commands.py — what a hub does with a command and a proposal (SPEC-REG-COMMANDS).

A reference decision function for §2 and rules CM1-CM20 of
docs/30-design/platform/spec/commands.md: routing to the holder of a device
command sink on the command's own tenant, the command record and its states,
outcomes reported by the destination only, proposals and approvals bound to
one payload hash, and pushes sent only inside a request bound to the
command's tenant. It checks the cases under specs/sync/conformance/commands/
(format in FORMAT.md there); it is not a hub.

Routing is given, not computed: each instance states the channels on which
it holds a device command sink and over which interval.
"""
import hashlib

from nsschema.negotiate import canonical_json

FINAL = ("succeeded", "failed", "refused", "not-routed", "undeliverable", "expired")
HANDED_OVER = ("sent", "fetched")
CONTROLLER_STATES = ("acknowledged", "succeeded", "failed", "refused")
REASONS = ("hash-mismatch", "expired", "not-accepted", "limit")


def payload_hash(payload):
    """CM1: sha256 over the RFC 8785 canonical JSON of the payload."""
    return "sha256:%s" % hashlib.sha256(canonical_json(payload)).hexdigest()


def _holds(instance, channel, at):
    span = instance.get("sinks", {}).get(channel)
    if span is None:
        return False
    start, until = span
    return start <= at and (until is None or at < until)


def _route(case, tenant, channel, product, at):
    """§2: the live device holder on the command's tenant, or a refusal."""
    instances = case["instances"]
    declaring = case.get("declares", {}).get(tenant, {}).get(channel, [])
    if not declaring:
        return None, "no-command-destination"
    if product is None and channel not in case.get("shared", []):
        if len(declaring) > 1:
            return None, "ambiguous-command-destination"
        product = declaring[0]
    for name in sorted(instances):
        inst = instances[name]
        if inst["tenant"] != tenant or inst.get("simulated"):
            continue
        if product is not None and inst["product"] != product:
            continue
        if _holds(inst, channel, at):
            return name, None
    return None, "no-command-destination"


def _state_version(case, tenant, product, at):
    current = None
    for start, version in case.get("stateVersions", {}).get(tenant, {}).get(product, []):
        if start <= at:
            current = version
    return current


class Hub:
    def __init__(self, case):
        self.case = case
        self.commands = {}
        self.proposals = {}
        self.request_ids = {}
        # CM21: what each controller instance has decided, kept across restarts.
        self.decided = {}

    def _subject(self, call):
        subject = self.case["subjects"].get(call["subject"])
        if subject is None or subject["tenant"] != call["tenant"]:
            return None
        return subject

    def _permitted(self, call, permission):
        subject = self._subject(call)
        return subject is not None and permission in subject.get("permissions", [])

    def _effective(self, cid, at):
        """CM2, CM3: hub-set states are evaluated lazily at a time. A command
        never handed over ends undeliverable or expired; one that was handed
        over becomes unconfirmed, because the controller may have enacted it."""
        c = self.commands[cid]
        state = c["state"]
        if state in FINAL or state in CONTROLLER_STATES or state == "unconfirmed":
            return state
        inst = self.case["instances"][c["destination"]]
        if state == "pending":
            if not _holds(inst, c["channel"], at):
                return "undeliverable"
            if at >= c["expiresAt"]:
                return "expired"
        if state == "sent" and not _holds(inst, c["channel"], at):
            return "unconfirmed"
        if state in HANDED_OVER and at >= c["expiresAt"]:
            return "unconfirmed"
        return state

    def _settle(self, cid, at):
        self.commands[cid]["state"] = self._effective(cid, at)
        return self.commands[cid]["state"]

    def _new_command(self, call, payload, expires, proposal_id=None, product=None, routed=None):
        tenant = call["tenant"]
        cid = "c%d" % (len(self.commands) + 1)
        destination, code = routed or _route(self.case, tenant, call["channel"], product, call["at"])
        self.commands[cid] = {
            "tenant": tenant, "channel": call["channel"], "destination": destination,
            "payload": payload, "payloadHash": payload_hash(payload), "expiresAt": expires,
            "proposalId": proposal_id, "subject": call["subject"],
            "state": "pending" if destination else "not-routed", "code": code}
        if code:
            return {"status": 409, "code": code, "commandId": cid}
        return {"status": 201, "commandId": cid, "state": "pending"}

    def _expiry(self, call):
        if call.get("expiresAt") is None or call["expiresAt"] <= call["at"]:
            return "expiry-required"
        if call["expiresAt"] - call["at"] > self.case.get("maxExpirySeconds", 3600):
            return "expiry-too-long"
        return None

    def command(self, call):
        if not self._permitted(call, "api:commands:create"):
            return {"status": 403, "code": "not-authorised"}
        bad = self._expiry(call)
        if bad:
            return {"status": 422, "code": bad}
        if len(canonical_json(call["payload"])) > self.case.get("maxPayloadBytes", 4096):
            return {"status": 413, "code": "payload-too-large"}
        key = (call["tenant"], call["subject"], call.get("requestId"))
        if call.get("requestId") is not None and key in self.request_ids:
            cid, request = self.request_ids[key]
            if request != (call["channel"], call.get("product"), payload_hash(call["payload"])):
                return {"status": 409, "code": "request-id-reused"}
            return {"status": 200, "commandId": cid, "state": self._public(cid, call["at"])}
        result = self._new_command(call, call["payload"], call["expiresAt"],
                                   product=call.get("product"))
        if call.get("requestId") is not None:
            self.request_ids[key] = (result["commandId"], (
                call["channel"], call.get("product"), payload_hash(call["payload"])))
        return result

    def _public(self, cid, at):
        return self._settle(cid, at)

    def push(self, call):
        c = self.commands[call["command"]]
        if self.case["mode"] == "multi" and call.get("bound") != c["tenant"]:
            return {"sent": False, "reason": "withheld"}
        state = self._settle(call["command"], call["at"])
        if state == "expired":
            return {"sent": False, "reason": "expired"}
        if state not in ("pending", "sent"):
            return {"sent": False, "reason": "not-pending"}
        c["state"] = "sent"
        return {"sent": True}

    def fetch(self, call):
        inst = self.case["instances"].get(call["instance"])
        if inst is None or inst["tenant"] != call["tenant"]:
            return {"status": 404}
        if inst["subject"] != call["subject"]:
            return {"status": 403, "code": "not-registration-owner"}
        got = []
        for cid, c in self.commands.items():
            if c["destination"] != call["instance"] or c["tenant"] != call["tenant"]:
                continue
            if self._settle(cid, call["at"]) in ("pending", "sent"):
                c["state"] = "fetched"
                got.append(cid)
        return {"status": 200, "commands": got}

    def enact(self, call):
        """CM10 and CM21: the controller's own checks before it enacts. A commandId
        the instance has already decided is not decided again."""
        c = self.commands[call["command"]]
        decided = self.decided.setdefault(call["instance"], set())
        if call["command"] in decided:
            return {"state": "ignored", "reason": "duplicate"}
        decided.add(call["command"])
        received = call.get("received", c["payload"])
        if payload_hash(received) != c["payloadHash"]:
            return {"state": "refused", "reason": "hash-mismatch"}
        if call["at"] >= c["expiresAt"]:
            return {"state": "refused", "reason": "expired"}
        return {"state": "succeeded"}

    def restart(self, call):
        """CM21: a controller restart; what it decided is kept."""
        return {}

    def report(self, call):
        c = self.commands.get(call["command"])
        if c is None or c["tenant"] != call["tenant"]:
            return {"status": 404}
        inst = self.case["instances"].get(c["destination"]) if c["destination"] else None
        if inst is None or inst["subject"] != call["subject"]:
            return {"status": 403, "code": "not-registration-owner"}
        if call["state"] not in CONTROLLER_STATES:
            return {"status": 422, "code": "invalid-state"}
        reason = call.get("reason")
        if reason is not None and not (reason in REASONS or (
                isinstance(reason, dict) and reason.get("value") == "other"
                and reason.get("controllerTerm"))):
            return {"status": 422, "code": "invalid-reason"}
        state = self._settle(call["command"], call["at"])
        if state in FINAL:
            return {"status": 409, "code": "already-final"}
        c["state"] = call["state"]
        c["reportedHash"] = payload_hash(call.get("checked", c["payload"]))
        c["hashMismatch"] = c["reportedHash"] != c["payloadHash"]
        return {"status": 200}

    def read(self, call):
        c = self.commands.get(call["command"])
        if c is None or c["tenant"] != call["tenant"]:
            return {"status": 404}
        return {"status": 200, "state": self._public(call["command"], call["at"])}

    def propose(self, call):
        if not self._permitted(call, "api:proposals:create"):
            return {"status": 403, "code": "not-authorised"}
        inst = self.case["instances"].get(call["instance"])
        if inst is None or inst["tenant"] != call["tenant"]:
            return {"status": 404}
        if inst["subject"] != call["subject"]:
            return {"status": 403, "code": "not-registration-owner"}
        if call["channel"] not in inst.get("proposes", []):
            return {"status": 403, "code": "role-not-granted"}
        if len(canonical_json(call["payload"])) > self.case.get("maxPayloadBytes", 4096):
            return {"status": 413, "code": "payload-too-large"}
        bad = self._expiry(call)
        if bad:
            return {"status": 422, "code": bad}
        if call.get("basedOn") is None:
            return {"status": 422, "code": "based-on-required"}
        destination, code = _route(self.case, call["tenant"], call["channel"], call.get("product"),
                                   call["at"])
        if code:
            return {"status": 409, "code": code}
        named = call.get("instanceId")
        if named and (named not in self.case["instances"]
                      or self.case["instances"][named]["tenant"] != call["tenant"]):
            return {"status": 404}
        if named and named != destination:
            return {"status": 409, "code": "destination-changed"}
        pid = "p%d" % (len(self.proposals) + 1)
        self.proposals[pid] = dict(call, state="open", payloadHash=payload_hash(call["payload"]),
                                   destination=destination)
        return {"status": 201, "proposalId": pid}

    def _proposal(self, call):
        p = self.proposals.get(call["proposal"])
        if p is None or p["tenant"] != call["tenant"]:
            return None
        if p["state"] == "open" and call["at"] >= p["expiresAt"]:
            p["state"] = "expired"
        return p

    def approve(self, call):
        p = self._proposal(call)
        if p is None:
            return {"status": 404}
        if not self._permitted(call, "api:commands:create"):
            return {"status": 403, "code": "not-authorised"}
        if call["subject"] == p["subject"]:
            return {"status": 403, "code": "self-approval"}
        if p["state"] == "expired":
            return {"status": 409, "code": "proposal-expired"}
        if p["state"] != "open":
            return {"status": 409, "code": "proposal-closed"}
        if payload_hash(call["approves"]) != p["payloadHash"]:
            return {"status": 409, "code": "hash-mismatch"}
        destination, code = _route(self.case, p["tenant"], p["channel"], p.get("product"), call["at"])
        if code:
            return {"status": 409, "code": code}
        if destination != p["destination"]:
            return {"status": 409, "code": "destination-changed"}
        product = self.case["instances"][destination]["product"]
        if _state_version(self.case, p["tenant"], product, call["at"]) != p["basedOn"]:
            return {"status": 409, "code": "state-changed"}
        p["state"] = "approved"
        made = dict(call, channel=p["channel"])
        return self._new_command(made, p["payload"], p["expiresAt"], proposal_id=call["proposal"],
                                 routed=(destination, None))

    def reject(self, call):
        p = self._proposal(call)
        if p is None:
            return {"status": 404}
        if not self._permitted(call, "api:commands:create"):
            return {"status": 403, "code": "not-authorised"}
        if p["state"] != "open":
            return {"status": 409, "code": "proposal-expired" if p["state"] == "expired"
                    else "proposal-closed"}
        p["state"] = "rejected"
        return {"status": 200}

    def withdraw(self, call):
        p = self._proposal(call)
        if p is None:
            return {"status": 404}
        if call["subject"] != p["subject"]:
            return {"status": 403, "code": "not-authorised"}
        if p["state"] != "open":
            return {"status": 409, "code": "proposal-expired" if p["state"] == "expired"
                    else "proposal-closed"}
        p["state"] = "withdrawn"
        return {"status": 200}

    def evaluate(self, call):
        p = self._proposal(call)
        if p is None or self._subject(call) is None:
            return {"status": 404}
        if not (self._permitted(call, "api:proposals:read")
                or self._permitted(call, "api:commands:create")):
            return {"status": 403, "code": "not-authorised"}
        p.setdefault("evaluations", []).append(call.get("note"))
        return {"status": 201}


def run(case):
    """Replay a case's calls in order; return each call's result and the final
    states of commands and proposals at `end`."""
    hub = Hub(case)
    results = [getattr(hub, call["kind"])(call) for call in case["calls"]]
    end = case.get("end", max(c["at"] for c in case["calls"]))
    commands = {}
    for cid, c in hub.commands.items():
        row = {"state": hub._public(cid, end), "destination": c["destination"]}
        if c["proposalId"]:
            row["proposalId"] = c["proposalId"]
        if c.get("hashMismatch"):
            row["hashMismatch"] = True
        commands[cid] = row
    proposals = {}
    for pid in hub.proposals:
        hub._proposal({"proposal": pid, "tenant": hub.proposals[pid]["tenant"], "at": end})
        proposals[pid] = {"state": hub.proposals[pid]["state"]}
    return {"calls": results, "commands": commands, "proposals": proposals, "hub": hub}
