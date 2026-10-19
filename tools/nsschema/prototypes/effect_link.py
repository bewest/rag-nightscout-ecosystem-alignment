"""effect_link.py — prototype: how a command's outcome links to the record of its effect.

Commands CM7 says an enacted command's report carries "the identity of the
record that shows the effect". This prototype runs four ways of making that
link, and today's inference as a baseline, against one set of scenarios, for
the assessment in docs/30-design/platform/effect-link-prototype-2026-10-18.md.
It is not a hub and not the reference in nsschema/commands.py: it models one
controller, one hub and one channel, with the write step's re-send matching
(identity I5, section 3), soft delete, CM9's single final report and CM21's
decided set. Routing, tenants, expiry and hashes are left out: they do not
differ between the options.

  B0  today, inferred: a reader links a succeeded command to the earliest
      unclaimed record of each kind the command asked for, within a window
      after the command was made. Nothing is sent; this is the baseline.
  E1  effect[] on the report: the report lists the identities (I4 form:
      collection, identifier, else _id) of the records showing the effect;
      the hub records them as reported and resolves them when read.
  E2  commandId on the record: each effect record carries the commandId; the
      hub links by it, keeps it once stored, and refuses a different value.
  E3  both: links are the union, and the hub flags a pair one source gives
      and the other, able to speak, does not.
  E4  a reconciliation record: the controller writes a record of its own
      kind, one per command (identifier derived from the commandId), naming
      the effect identities; it goes through the write step like any record,
      so it can be re-sent and amended after the report is final.

Ground truth is kept beside the model: each scenario step that makes a record
says which command, if any, caused it. The link functions read only what the
hub stores. `measure(scenario, option)` compares the two.

Run `python3 -m nsschema.prototypes.effect_link --check` (from tools/) to
compare the generated tables in the note with the model; `--write` rewrites
them.
"""
import argparse
import copy
import re
import sys

OPTIONS = ("B0", "E1", "E2", "E3", "E4")
WINDOW = 15            # B0's window after a command is made, in model minutes

# What a controller does, unless a scenario says otherwise. `tags`: its record
# uploader can carry a commandId (E2, E3). `identifier`: it sends `identifier`
# on effect records. `keepsEffects`: it keeps each command's effect list across
# a restart until the report is accepted (E1, E4). `keepsMap`: it remembers
# which records a command caused for as long as they can change (E2's copy on
# repost, E4's update).
PROFILE = {"tags": True, "identifier": True, "keepsEffects": True, "keepsMap": True}

FINAL = {"succeeded", "failed", "refused"}

# Rules the options depend on, named so a test can weaken one and see it fail.
# keepTag: E2's hub keeps a stored commandId on merge and replace.
# tagOnlyEnacted: a controller tags only the records it writes while enacting.
RULES = {"keepTag": True, "tagOnlyEnacted": True}


class World:
    """One controller and one hub, for one option."""

    def __init__(self, scenario, option):
        self.option = option
        self.profile = dict(PROFILE, **scenario.get("controller", {}))
        self.faults = scenario.get("faults", {})
        self.truth = set()            # (commandId, record key)
        self.local = set()            # record keys made by a local action
        self.ctl = {}                 # key -> the controller's copy of a record
        self.effects = {}             # commandId -> [keys], the controller's list
        self.hub = []                 # stored records; "key" is model metadata
        self.commands = {}            # commandId -> the hub's command record
        self.recon = {}               # commandId -> stored reconciliation (E4)
        self.early = {"known": 0, "unknown": 0}
        self.recon_pending = set()    # E4: (commandId, key) whose identity came later
        self.last_enacted = None
        self.replies = []

    # --- what each option sends ------------------------------------------

    def _sends_report_effect(self):
        return self.option in ("E1", "E3")

    def _sends_tag(self):
        return self.option in ("E2", "E3") and self.profile["tags"]

    def _identity(self, key):
        """The I4 form the controller can give for one of its records."""
        r = self.ctl[key]
        if r.get("identifier"):
            return {"collection": r["collection"], "identifier": r["identifier"]}
        if r.get("_id"):
            return {"collection": r["collection"], "_id": r["_id"]}
        return None

    # --- the hub's write step (identity section 3, T2) -----------------------

    def _target(self, doc):
        live = [h for h in self.hub if not h["deleted"] and h["collection"] == doc["collection"]]
        if doc.get("identifier"):
            return next((h for h in live if h.get("identifier") == doc["identifier"]), None)
        return next((h for h in live if not h.get("identifier")
                     and h["at"] == doc["at"] and h["kind"] == doc["kind"]), None)

    def _write(self, key, doc):
        target = self._target(doc)
        if target is None:
            target = dict(doc, _id="oid%d" % (len(self.hub) + 1), deleted=False, key=key)
            self.hub.append(target)
            return target["_id"]
        stored = target.get("commandId")
        merged = dict(target, **{k: v for k, v in doc.items() if k != "commandId"})
        if doc.get("commandId") and not stored:
            merged["commandId"] = doc["commandId"]
        if not RULES["keepTag"]:
            merged.pop("commandId", None)
            if doc.get("commandId"):
                merged["commandId"] = doc["commandId"]
        target.update(merged)       # E2: a stored commandId is kept, never replaced
        return target["_id"]

    def _doc(self, key):
        r = self.ctl[key]
        doc = {"collection": r["collection"], "kind": r["kind"], "at": r["at"]}
        if r.get("identifier"):
            doc["identifier"] = r["identifier"]
        if r.get("tag") and self._sends_tag():
            doc["commandId"] = r["tag"]
        return doc

    # --- scenario steps ----------------------------------------------------

    def send(self, step):
        self.commands[step["command"]] = {
            "createdAt": step["at"], "kinds": list(step["kinds"]), "state": "sent", "effect": None}

    def _new_record(self, rec, at, cause):
        key = rec["key"]
        collection = rec.get("collection", "treatments")
        self.ctl[key] = {
            "kind": rec["kind"], "collection": collection, "at": rec.get("at", at),
            "identifier": ("app://%s/%s" % (rec["kind"], key)) if self.profile["identifier"] else None,
            "tag": cause, "_id": None}
        if cause:
            self.truth.add((cause, key))
            self.effects.setdefault(cause, []).append(key)
        else:
            self.local.add(key)
            if not RULES["tagOnlyEnacted"]:
                self.ctl[key]["tag"] = self.last_enacted

    def enact(self, step):
        cid = step["command"]
        self.last_enacted = cid
        for rec in step.get("records", []):
            self._new_record(rec, step["at"], cid)
        if "amends" in step:                 # a command whose effect is a change to a record
            key = step["amends"]
            self.truth.add((cid, key))
            self.effects.setdefault(cid, []).append(key)
            # one commandId per record: the controller keeps the first (E2's limit)
            self.ctl[key]["tag"] = self.ctl[key]["tag"] or cid
        if "replaces" in step:               # an edit that deletes a record and makes a new one
            self._delete(step["replaces"])

    def local_action(self, step):
        for rec in step["records"]:
            self._new_record(rec, step["at"], None)
            if self.faults.get("tagLocalWith"):
                self.ctl[rec["key"]]["tag"] = self.faults["tagLocalWith"]

    def upload(self, step):
        key, lost = step["record"], step.get("lost")
        if lost == "request":
            return
        oid = self._write(key, self._doc(key))
        if lost != "reply":
            self.ctl[key]["_id"] = oid
            self._update_recon(key)

    def report(self, step):
        cid, c = step["command"], self.commands[step["command"]]
        keys = list(self.effects.get(cid, []))
        if self.faults.get("reportNames"):
            keys = [self.faults["reportNames"]]
        ids = [i for i in (self._identity(k) for k in keys) if i]
        if self.option == "E4":
            # a record, written through the write step: a later write for the
            # same command matches it by identifier and replaces its effect list
            self.recon[cid] = {"effect": list(ids), "author": "destination"}
            self.recon_pending |= {(cid, k) for k in keys if self._identity(k) is None}
        if c["state"] in FINAL:
            self.replies.append(409)         # CM9 already-final
            return
        c["state"] = step["state"]
        if self._sends_report_effect():
            c["effect"] = ids
        stored = {h["key"] for h in self.hub}
        for k in keys:
            if k not in stored:
                carried = self.option in ("E1", "E3", "E4") and self._identity(k) is not None
                self.early["known" if carried else "unknown"] += 1
        self.replies.append(200)

    def _update_recon(self, key):
        """E4: an effect whose identity the controller learned after its report
        is added to the reconciliation record, which is a record and can change."""
        if self.option != "E4" or not self.profile["keepsMap"]:
            return
        for cid, k in sorted(self.recon_pending):
            if k == key and cid in self.recon:
                self.recon[cid]["effect"].append(self._identity(key))
                self.recon_pending.discard((cid, k))

    def restart(self, step):
        if not self.profile["keepsEffects"]:
            self.effects = {}

    def _delete(self, key):
        for h in self.hub:
            if h["key"] == key:
                h["deleted"] = True

    def delete(self, step):
        self._delete(step["record"])

    def repost(self, step):
        """An end written as delete and re-post (state and intent S6): a new
        record for the same instance."""
        old, new = step["record"], step["new"]
        self._delete(old)
        r = copy.deepcopy(self.ctl[old])
        causes = sorted(c for c, k in self.truth if k == old)
        self.ctl[new] = dict(r, at=step["at"], _id=None,
                             identifier=("app://%s/%s" % (r["kind"], new)) if r["identifier"] else None,
                             tag=r["tag"] if self.profile["keepsMap"] else None)
        for c in causes:
            self.truth.add((c, new))
            if self.option == "E4" and self.profile["keepsMap"] and c in self.recon:
                if self._identity(new):
                    self.recon[c]["effect"].append(self._identity(new))
                else:
                    self.recon_pending.add((c, new))

    def replace(self, step):
        """Another client replaces a stored record (v1 or v3 PUT) with a body
        that lacks commandId; E2's rule keeps the stored commandId."""
        for h in self.hub:
            if h["key"] == step["record"] and not h["deleted"] and not RULES["keepTag"]:
                h.pop("commandId", None)

    # --- links, from what the hub stores --------------------------------------

    def resolve(self, ident):
        return [h for h in self.hub if h["collection"] == ident["collection"] and (
            h.get("identifier") == ident["identifier"] if "identifier" in ident
            else h["_id"] == ident["_id"])]

    def _links_from(self, lists):
        out, dangling = set(), 0
        for cid, ids in lists.items():
            for ident in ids or []:
                found = self.resolve(ident)
                dangling += not found
                out |= {(cid, h["key"]) for h in found}
        return out, dangling

    def links_report(self):
        return self._links_from({cid: c["effect"] for cid, c in self.commands.items()})

    def links_tag(self):
        return {(h["commandId"], h["key"]) for h in self.hub
                if h.get("commandId") in self.commands}

    def links_recon(self):
        return self._links_from({cid: r["effect"] for cid, r in self.recon.items()})

    def links_inferred(self):
        out, claimed = set(), set()
        live = sorted((h for h in self.hub if not h["deleted"]), key=lambda h: (h["at"], h["_id"]))
        for cid, c in sorted(self.commands.items(), key=lambda kv: kv[1]["createdAt"]):
            if c["state"] != "succeeded":
                continue
            for kind in c["kinds"]:
                h = next((h for h in live if h["kind"] == kind and h["key"] not in claimed
                          and c["createdAt"] <= h["at"] <= c["createdAt"] + WINDOW), None)
                if h:
                    claimed.add(h["key"])
                    out.add((cid, h["key"]))
        return out

    def links(self):
        """(links, flagged pairs, dangling identities) for this world's option."""
        if self.option == "B0":
            return self.links_inferred(), set(), 0
        if self.option == "E1":
            links, dangling = self.links_report()
            return links, set(), dangling
        if self.option == "E2":
            return self.links_tag(), set(), 0
        if self.option == "E4":
            links, dangling = self.links_recon()
            return links, set(), dangling
        by_report, dangling = self.links_report()
        by_tag = self.links_tag()
        final_with_list = {cid for cid, c in self.commands.items()
                           if c["state"] in FINAL and c["effect"] is not None}
        flagged = {p for p in by_report - by_tag if self.profile["tags"] and p[1] in
                   {h["key"] for h in self.hub}} | {
                   p for p in by_tag - by_report if p[0] in final_with_list}
        return by_report | by_tag, flagged, dangling


STEP = {"send": "send", "enact": "enact", "local": "local_action", "upload": "upload",
        "report": "report", "restart": "restart", "delete": "delete", "repost": "repost",
        "replace": "replace"}


def run(scenario, option):
    world = World(scenario, option)
    for step in scenario["steps"]:
        getattr(world, STEP[step["do"]])(step)
    return world


def measure(scenario, option):
    """Links correct, wrong and missing against the scenario's ground truth,
    with the safety measures the note tables."""
    w = run(scenario, option)
    links, flagged, dangling = w.links()
    truth = w.truth
    linked_records = {k for _, k in links}
    caused = {k for _, k in truth}
    per_command = {}
    for cid, k in links:
        stored = next(h for h in w.hub if h["key"] == k)
        if not stored["deleted"]:
            per_command.setdefault((cid, stored["kind"]), set()).add(k)
    asked = {(cid, kind): c["kinds"].count(kind) for cid, c in w.commands.items() for kind in c["kinds"]}
    return {
        "correct": len(links & truth),
        "wrong": len(links - truth),
        "missing": len(truth - links),
        "flagged": len(flagged),
        "flaggedWrong": len(flagged - truth),
        "dangling": dangling,
        "localShownRemote": len(linked_records & w.local),
        "remoteShownLocal": len(caused - linked_records),
        "duplicateVisible": sum(len(v) > asked.get(ck, 0) for ck, v in per_command.items()),
        "earlyKnown": w.early["known"],
        "earlyUnknown": w.early["unknown"],
    }


def from_record_alone(scenario, option):
    """Can a reader that holds only the stored record documents (an export, a
    second hub, a reader that shows unknown fields) tell which were remote?"""
    w = run(scenario, option)
    return bool(w.truth) and all(
        bool(h.get("commandId")) == (h["key"] not in w.local) for h in w.hub)


# --- scenarios ---------------------------------------------------------------
# Times are model minutes. Every record is synthetic; kinds stand for the
# carrier a controller writes (a bolus treatment, a carb treatment, an override).

def _s(*steps, **kw):
    return dict(kw, steps=list(steps))


def send(c, at, *kinds):
    return {"do": "send", "command": c, "at": at, "kinds": list(kinds)}


def enact(c, at, *records, **kw):
    return dict({"do": "enact", "command": c, "at": at,
                 "records": [{"key": k, "kind": kind} for k, kind in records]}, **kw)


def up(r, lost=None):
    return {"do": "upload", "record": r, **({"lost": lost} if lost else {})}


def report(c, state="succeeded"):
    return {"do": "report", "command": c, "state": state}


SCENARIOS = {
    "bolus-one-record": _s(
        send("A", 0, "bolus"), enact("A", 2, ("r1", "bolus")), up("r1"), report("A"),
        about="enacted bolus, one dose record"),
    "override-ended-by-amend": _s(
        send("A", 0, "override"), enact("A", 1, ("r1", "override")), up("r1"), report("A"),
        up("r1"),
        about="override enacted, then ended early by amending its duration (same record)"),
    "override-ended-by-repost": _s(
        send("A", 0, "override"), enact("A", 1, ("r1", "override")), up("r1"), report("A"),
        {"do": "repost", "record": "r1", "new": "r2", "at": 40}, up("r2"),
        about="override enacted, then ended by delete and re-post (a new record for the same instance)"),
    "override-then-remote-cancel": _s(
        send("A", 0, "override"), enact("A", 1, ("r1", "override")), up("r1"), report("A"),
        send("B", 30, "override"), enact("B", 31, amends="r1"), up("r1"), report("B"),
        about="override enacted by A, ended by a remote cancel B; one record shows both effects"),
    "carbs-edited-by-command": _s(
        send("A", 0, "carbs"), enact("A", 1, ("r1", "carbs")), up("r1"), report("A"),
        send("B", 20, "carbs"), enact("B", 21, ("r2", "carbs"), replaces="r1"),
        up("r2"), report("B"),
        about="carbs entered by A, edited by B: the edit deletes r1 and makes r2"),
    "upload-request-lost-resent": _s(
        send("A", 0, "bolus"), enact("A", 2, ("r1", "bolus")), up("r1", "request"),
        report("A"), up("r1"),
        about="the record's upload is lost, the report goes, the record is re-sent"),
    "upload-reply-lost-no-identifier": _s(
        send("A", 0, "bolus"), enact("A", 2, ("r1", "bolus")), up("r1", "reply"),
        report("A"), up("r1"),
        controller={"identifier": False},
        about="no identifier; the write reply is lost, so the controller has no _id when it reports"),
    "report-before-record": _s(
        send("A", 0, "bolus"), enact("A", 2, ("r1", "bolus")), report("A"), up("r1"),
        about="the report reaches the hub before the record"),
    "report-after-record": _s(
        send("A", 0, "bolus"), enact("A", 2, ("r1", "bolus")), up("r1"), report("A"),
        {"do": "upload", "record": "r1"},
        about="the record reaches the hub before the report, and is re-sent after"),
    "restart-effects-kept": _s(
        send("A", 0, "bolus"), enact("A", 2, ("r1", "bolus")), {"do": "restart"}, up("r1"),
        report("A"),
        about="the controller restarts between enacting and reporting, and keeps its effect list"),
    "restart-effects-not-kept": _s(
        send("A", 0, "bolus"), enact("A", 2, ("r1", "bolus")), {"do": "restart"}, up("r1"),
        report("A"),
        controller={"keepsEffects": False},
        about="the same, with a controller that keeps only CM21's decided ids across a restart"),
    "refused-then-local-dose": _s(
        send("A", 0, "bolus"), report("A", "refused"),
        {"do": "local", "at": 3, "records": [{"key": "r1", "kind": "bolus"}]}, up("r1"),
        about="the command is refused; the person then doses on the phone"),
    "local-dose-after-command": _s(
        send("A", 0, "bolus"), enact("A", 2, ("r1", "bolus")), up("r1"), report("A"),
        {"do": "local", "at": 6, "records": [{"key": "r9", "kind": "bolus"}]}, up("r9"),
        about="a command is enacted; minutes later the person doses on the phone"),
    "local-dose-while-command-in-flight": _s(
        send("A", 0, "bolus"),
        {"do": "local", "at": 1, "records": [{"key": "r9", "kind": "bolus"}]}, up("r9"),
        enact("A", 4, ("r1", "bolus")), up("r1"), report("A"),
        about="a local dose on the phone lands between the command and its enactment"),
    "meal-part-enacted": _s(
        send("A", 0, "carbs", "bolus"), enact("A", 1, ("r1", "carbs")), up("r1"),
        report("A", "failed"),
        about="a meal command: carbs stored, bolus refused by the controller's limit; report failed"),
    "meal-two-records": _s(
        send("A", 0, "carbs", "bolus"), enact("A", 1, ("r1", "carbs"), ("r2", "bolus")),
        up("r1"), up("r2"), report("A"),
        about="one command, two records (carbs and bolus)"),
    "effect-amended": _s(
        send("A", 0, "bolus"), enact("A", 2, ("r1", "bolus")), up("r1"), report("A"), up("r1"),
        about="the dose record is amended later (the delivered amount differs)"),
    "effect-deleted": _s(
        send("A", 0, "bolus"), enact("A", 2, ("r1", "bolus")), up("r1"), report("A"),
        {"do": "delete", "record": "r1"},
        about="the person deletes the dose record later"),
    "effect-replaced-by-follower": _s(
        send("A", 0, "bolus"), enact("A", 2, ("r1", "bolus")), up("r1"), report("A"),
        {"do": "replace", "record": "r1"},
        about="a follower's editor replaces the stored record with a body that has no commandId"),
    "controller-cannot-tag": _s(
        send("A", 0, "bolus"), enact("A", 2, ("r1", "bolus")), up("r1"), report("A"),
        controller={"tags": False},
        about="a controller whose new command module reports, but whose record uploader cannot tag"),
    "two-commands-close": _s(
        send("A", 0, "bolus"), send("B", 1, "bolus"),
        enact("B", 2, ("rb", "bolus")), enact("A", 3, ("ra", "bolus")),
        up("rb"), up("ra"), report("B"), report("A"),
        about="two commands on one channel a minute apart, enacted in the other order"),
    "enacted-twice": _s(
        send("A", 0, "bolus"), enact("A", 2, ("r1", "bolus")), up("r1"), report("A"),
        {"do": "restart"}, enact("A", 5, ("r2", "bolus")), up("r2"), report("A"),
        controller={"keepsEffects": False},
        about="a controller without CM21 enacts a second delivery after a restart; its second report is refused"),
    "fault-report-names-local-record": _s(
        send("A", 0, "bolus"), enact("A", 2, ("r1", "bolus")),
        {"do": "local", "at": 3, "records": [{"key": "r9", "kind": "bolus"}]},
        up("r1"), up("r9"), report("A"),
        faults={"reportNames": "r9"},
        about="fault: the report path names a local dose instead of the command's"),
    "fault-tag-on-local-record": _s(
        send("A", 0, "bolus"), enact("A", 2, ("r1", "bolus")),
        {"do": "local", "at": 3, "records": [{"key": "r9", "kind": "bolus"}]},
        up("r1"), up("r9"), report("A"),
        faults={"tagLocalWith": "A"},
        about="fault: the tagging path puts the current commandId on a local dose"),
}


# --- costs: each list is what the option needs; the tables count them ---------

# Record carriers a command reaches today, as commands section 3 and 8 and state
# and intent section 3 read them (Loop, Trio, AndroidAPS client control).
EFFECT_CARRIERS = [
    ("bolus", "treatments: bolus (Loop, Trio, AndroidAPS)"),
    ("carbs", "treatments: carbs (Loop, Trio, AndroidAPS)"),
    ("loop-override", "treatments: Temporary Override (Loop)"),
    ("trio-override", "treatments: Exercise, Trio's override"),
    ("temporary-target", "treatments: Temporary Target (Trio, AndroidAPS)"),
    ("profile-switch", "treatments: Profile Switch (AndroidAPS)"),
    ("running-mode", "treatments: OpenAPS Offline, running mode (AndroidAPS)"),
    ("temp-basal", "treatments: Temp Basal (AndroidAPS)"),
    ("extended-bolus", "treatments: Combo Bolus, extended (AndroidAPS)"),
    ("therapy-event", "treatments: therapy events (AndroidAPS)"),
    ("scene", "settings: scene (AndroidAPS dev)"),
    ("loop-mode", "profile: loop mode (Loop, via LoopCaregiver)"),
]

COSTS = {
    "E1": {
        "schemas": ["outcome report: effect[]"],
        "hub": ["effect[] stored as reported",
                "index: effect identity to commandId"],
        "invariants": ["an effect identity is stored as reported and resolved when read; one that resolves to nothing is shown as not received"],
        "controller": ["each command's effect identities, kept with CM21's decided id until the report is accepted",
                       "an identifier on each effect record, or the _id from its write reply"],
        "cases": ["report-effect-accepted", "report-effect-shape-invalid", "report-effect-on-failed",
                  "report-effect-before-record", "report-effect-unresolved", "read-record-shows-command",
                  "report-effect-other-tenant-record"],
    },
    "E2": {
        "schemas": ["a well-known commandId field"] + ["carrier: " + c for _, c in EFFECT_CARRIERS],
        "hub": ["commandId on every effect carrier",
                "index: commandId on each collection that holds effect records"],
        "invariants": ["a commandId names a command routed to the writing instance",
                       "a stored commandId is kept on merge and replace, and a different value is refused",
                       "a record from a local action carries no commandId"],
        "controller": ["the commandId on each effect record in its own store, for every re-send, amendment and re-post",
                       "an uploader for every carrier that writes the field"],
        "cases": ["tag-accepted-" + slug for slug, _ in EFFECT_CARRIERS] + [
                  "tag-unknown-command", "tag-other-instance-refused", "tag-kept-on-merge",
                  "tag-kept-on-replace", "tag-changed-refused", "read-command-shows-records"],
    },
    "E4": {
        "schemas": ["reconciliation record kind"],
        "hub": ["a reconciliation collection or kind",
                "index: effect identity to commandId"],
        "invariants": ["a reconciliation record is accepted only from the destination's bound subject",
                       "one reconciliation per command, its identifier derived from the commandId",
                       "its outcome and the command's final state are shown together, and a difference is flagged"],
        "controller": ["each command's effect identities, as for E1",
                       "the command-to-records map for as long as the records can change"],
        "cases": ["recon-accepted", "recon-other-subject-refused", "recon-resend-matches",
                  "recon-amended-after-final", "recon-unresolved", "recon-outcome-differs-flagged",
                  "read-record-shows-command", "recon-other-tenant-record"],
    },
}
COSTS["E3"] = {
    k: COSTS["E1"][k] + COSTS["E2"][k] + (
        ["a pair one source gives and the other, able to speak, does not, is flagged and never resolved by the hub"]
        if k == "invariants" else ["flag-report-without-tag", "flag-tag-without-report"] if k == "cases" else [])
    for k in COSTS["E1"]}


# --- tables for the note ---------------------------------------------------------

def totals(option):
    keys = ("correct", "wrong", "missing", "flagged", "flaggedWrong", "dangling", "localShownRemote",
            "remoteShownLocal", "duplicateVisible", "earlyKnown", "earlyUnknown")
    out = dict.fromkeys(keys, 0)
    for s in SCENARIOS.values():
        m = measure(s, option)
        for k in keys:
            out[k] += m[k]
    return out


def _cell(m):
    text = "%d/%d/%d" % (m["correct"], m["wrong"], m["missing"])
    if m["flagged"]:
        text += " f%d" % m["flagged"]
    return text


def table_results():
    rows = ["| scenario | links | " + " | ".join(OPTIONS) + " |",
            "|---|---:|" + "---|" * len(OPTIONS)]
    for name, s in SCENARIOS.items():
        truth = len(run(s, "E1").truth)
        rows.append("| `%s` | %d | %s |" % (name, truth, " | ".join(_cell(measure(s, o)) for o in OPTIONS)))
    return "\n".join(rows)


def table_totals():
    t = {o: totals(o) for o in OPTIONS}
    alone = {o: sum(from_record_alone(s, o) for s in SCENARIOS.values()) for o in OPTIONS}
    lines = [
        ("links correct", "correct"), ("links wrong", "wrong"), ("links missing", "missing"),
        ("pairs flagged", "flagged"),
        ("flagged pairs that are wrong links", "flaggedWrong"),
        ("a local record shown as remote", "localShownRemote"),
        ("a remote record shown as local", "remoteShownLocal"),
        ("a command with more live records than it asked for", "duplicateVisible"),
        ("an effect in flight known to the hub", "earlyKnown"),
        ("an effect in flight not known to the hub", "earlyUnknown"),
    ]
    rows = ["| measure (over %d scenarios) | %s |" % (len(SCENARIOS), " | ".join(OPTIONS)),
            "|---|" + "---:|" * len(OPTIONS)]
    for label, k in lines:
        rows.append("| %s | %s |" % (label, " | ".join(str(t[o][k]) for o in OPTIONS)))
    rows.append("| scenarios with a remote record where the stored records alone show which were remote | %s |"
                % " | ".join(str(alone[o]) for o in OPTIONS))
    return "\n".join(rows)


def table_costs():
    opts = ("E1", "E2", "E3", "E4")
    lines = [("schemas or carriers touched", "schemas"), ("hub fields and indexes", "hub"),
             ("new invariants", "invariants"), ("controller must keep or write", "controller"),
             ("conformance cases", "cases")]
    rows = ["| | " + " | ".join(opts) + " |", "|---|" + "---:|" * len(opts)]
    for label, k in lines:
        rows.append("| %s | %s |" % (label, " | ".join(str(len(COSTS[o][k])) for o in opts)))
    return "\n".join(rows)


BLOCKS = {"effect-link-results": table_results, "effect-link-totals": table_totals,
          "effect-link-costs": table_costs}

BLOCK_RE = re.compile(r"(<!-- BEGIN GENERATED: (effect-link-[a-z]+) -->\n).*?(<!-- END GENERATED: \2 -->)", re.S)


def note_path():
    from nsschema import corpus
    return corpus.repo_root() / "docs" / "30-design" / "platform" / "effect-link-prototype-2026-10-18.md"


def render(text):
    return BLOCK_RE.sub(lambda m: m.group(1) + BLOCKS[m.group(2)]() + "\n" + m.group(3), text)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    path = note_path()
    text = path.read_text()
    new = render(text)
    if args.write:
        path.write_text(new)
        return 0
    if new != text:
        print("%s: generated tables are stale; run with --write" % path, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
