"""verification-record.py — capture the VERIFICATION RECORD for a named release.

    python3 tools/queue/verification-record.py \
        --release cgm-remote-monitor-15.0.9 \
        --captured-at 2026-09-15T23:10:00Z \
        --parcel phase0 \
        --out-dir releases/cgm-remote-monitor-15.0.9

    python3 tools/queue/verification-record.py --from-json <record.json> --out-dir <dir>
    python3 tools/queue/verification-record.py --check --from-json <record.json>
    python3 tools/queue/verification-record.py --self-test --captured-at <ts> --parcel phase0

The seventh tool under `tools/queue/`, beside ``manifest.py`` (schema),
``validate.py`` (the schema check), ``emit.py`` (the generated view),
``status.py`` (the gate runner) and ``vacuity.py`` (the negative controls). It
reuses ``status.py``'s executor rather than shelling out to it, so the result
in a record is the same measurement ``make queue-status`` prints, not a second
implementation that can drift from it.

WHAT A VERIFICATION RECORD IS

The quality-system record of what was actually checked when a release was cut.
Not a plan, not a claim, not a changelog. For each item in the release it
carries the branch and the commit SHA it resolved to, every gate and what that
gate ACTUALLY said when it was run, the register entries the release touches
with each entry's BASIS, the test commands with their output summaries, and —
mandatory — what was NOT verified and why.

THE THREE INVARIANTS THIS FILE EXISTS TO ENFORCE

  1. **THE GAPS SECTION MAY NOT BE EMPTY.** If ``not_verified`` comes out empty
     the generator writes nothing and exits 2. A record that omits its own gaps
     is worse than no record: it reads like completeness. There is no flag to
     turn this off, because the flag would be used.

  2. **THE TIMESTAMP COMES IN FROM OUTSIDE.** ``--captured-at`` is required and
     nothing in this file calls a clock, so a record can be re-derived and
     diffed rather than trusted.

     **How far that reproducibility actually goes, measured rather than
     assumed, and corrected once.** Two captures of the same release, same
     inputs, same manifest and register digests, were diffed field by field.
     What is STABLE: resolved SHAs, commits-ahead counts, every gate outcome,
     every item verdict, every register closure state and basis, the counted
     test summaries (passing/failing/pending), and all 76 entries in the gaps
     section -- byte-identical across captures. What MOVES: the gate
     TRANSCRIPTS ``output_tail``, ``output_bytes`` and ``output_sha256`` (25 of
     164 transcript fields moved between the two captures), because the
     commands themselves are not deterministic -- mocha prints ``5 passing
     (17ms)`` then ``(18ms)``, node prints its pid in a deprecation warning.

     **And one field that is a conclusion, not a transcript, moves with them:**
     ``output_summary.last_line``. An earlier draft of this docstring claimed
     test summaries were byte-identical without qualification; the diff refuted
     it. P0-D's coercion benchmark ends its output with ``duration_ms
     282.795205`` on one capture and ``278.901709`` on the next, and that line
     is carried verbatim into both the gate's ``output_summary`` and
     ``test_evidence``. The counted fields either side of it do not move. So:
     diff two captures on outcomes, verdicts, bases and gaps; do NOT diff them
     on digests or on a ``last_line`` that quotes a duration. The digest exists
     to let a reader bind a full log they hold to THIS capture, not to let two
     captures be compared byte for byte. The record says all of this in its own
     gaps section rather than leaving the stronger claim standing.

  3. **THE MARKDOWN IS GENERATED FROM THE JSON, NEVER BESIDE IT.** ``render()``
     takes the record dict and nothing else; ``--from-json`` re-renders an
     existing record to prove it. A hand-edited Markdown record is how the
     machine-readable half quietly becomes decorative.

AND THE RULE THE WHOLE FILE SERVES

Rule 3 of this programme: READ-DERIVED VERSUS REPRODUCED. Measured across the
programme, every register claim that had to be retracted was derived from
reading source; not one that began with a reproduction has been. So the record
labels each register entry, and where the register does not say, it records
``unstated`` and lists the entry in the gaps section. ``unstated`` is not a
failure of this tool. It is the finding.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import manifest  # noqa: E402
import status  # noqa: E402

RECORD_VERSION = 1
GENERATOR = "tools/queue/verification-record.py"

# Repo name (the manifest's `repo` field) -> checkout that owns the branches.
#
# `cgm-remote-monitor` is externals/cgm-remote-monitor-OFFICIAL. The sibling
# directory externals/cgm-remote-monitor is a 2014 commit on a different fork
# (bewest/cgm-remote-monitor-1) and holds none of this programme's work. An
# earlier briefing had this wrong, a record built against the wrong checkout
# would resolve every branch to MISSING, and the record would say so rather
# than being silently empty -- but it would still be the wrong record, so the
# mapping is written down here and overridable with --repo-path.
DEFAULT_REPO_PATHS = {
    "cgm-remote-monitor": "externals/cgm-remote-monitor-official",
    "nightscout-connect": "externals/nightscout-connect",
}

# The register tables. Parsed, not summarised: the record quotes the status
# cell verbatim so a reader can disagree with the classifier.
DEFAULT_REGISTER = "docs/30-design/remedial/nightscout-backfix-register.md"

ISO8601 = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")

TAIL_LINES = 40


# ─── small helpers ──────────────────────────────────────────────────────────

def _one_line(text):
    return " ".join(str(text or "").split())


def _sha256_file(path):
    try:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except OSError:
        return None


def _sha256_text(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def git(repo, *args):
    """Run git in `repo`. Returns (ok, stdout-stripped). Never raises."""
    try:
        completed = subprocess.run(
            ("git", "-C", repo) + args,
            capture_output=True, text=True, timeout=60)
    except Exception as error:  # noqa: BLE001
        return (False, "could not run git: %s" % error)
    if completed.returncode != 0:
        return (False, _one_line(completed.stderr) or
                "git exited %d" % completed.returncode)
    return (True, (completed.stdout or "").strip())


# ─── register parsing ───────────────────────────────────────────────────────

ROW_ID = re.compile(r"^\*\*(BF-\d+|CAP-\d+)\*\*$")
SECTION = re.compile(r"^##\s+(\d[a-z]?)\.\s+(.*)$")


def _cells(line):
    body = line.strip()
    if not body.startswith("|"):
        return None
    body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [c.strip() for c in body.split("|")]


def _plain(cell):
    """Strip the markdown a status cell wears, keep the words."""
    text = re.sub(r"~~(.*?)~~", r"\1", cell or "")
    text = text.replace("**", "").replace("`", "")
    return _one_line(text)


# THE BASIS CLASSIFIER, and why it is written as an ordered list of phrases
# rather than a judgement.
#
# Rule 3 asks every finding to be labelled read-derived or reproduced. The
# register does not carry that as a field; it carries it as prose in the status
# cell, and inconsistently -- the register's own header says so. So the
# classifier matches PHRASES, records WHICH phrase it matched, and quotes the
# whole cell beside it. A reader who disagrees can see exactly what was matched
# and why. Where no phrase matches, the answer is `unstated`, never a guess:
# inferring "well, it says 0.837 -> 0.025 ms so somebody must have run it" is
# precisely the laundering of an assertion into a measurement that this
# programme keeps rediscovering.
#
# Order matters: negations are tested before the positive, because
# "not reproduced against a live deployment" contains "reproduc".
BASIS_RULES = (
    ("read-derived", re.compile(r"\b(?:not|never)\b[^.;]{0,40}\breproduc", re.I)),
    ("read-derived", re.compile(r"\b(?:not|never)\b[^.;]{0,30}\b(?:run|executed)\b", re.I)),
    ("read-derived", re.compile(r"derived from source", re.I)),
    ("read-derived", re.compile(r"source census", re.I)),
    ("read-derived", re.compile(r"measured by grep|by grepping|by parsing the", re.I)),
    ("read-derived", re.compile(r"\bread (?:on|in full|, not)\b", re.I)),
    ("reproduced", re.compile(r"reproduc", re.I)),
)


def classify_basis(status_cell):
    """Return (basis, matched_phrase). basis in {reproduced, read-derived, unstated}."""
    text = _plain(status_cell)
    for basis, pattern in BASIS_RULES:
        found = pattern.search(text)
        if found:
            return (basis, found.group(0))
    return ("unstated", None)


def parse_register(path):
    """Parse §1 / §1b / §1c into {id: {...}} plus the file's digest."""
    entries = {}
    section = None
    header = None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError as error:
        return ({}, None, "could not read register: %s" % error)

    for line in lines:
        found = SECTION.match(line)
        if found:
            section = "%s. %s" % (found.group(1), _plain(found.group(2)))
            header = None
            continue
        cells = _cells(line)
        if not cells:
            continue
        if cells and cells[0].strip().lower() == "id":
            header = [c.strip().lower() for c in cells]
            continue
        if header is None:
            continue
        found = ROW_ID.match(cells[0])
        if not found:
            continue
        row = dict(zip(header, cells))
        entry_id = found.group(1)
        status_cell = row.get("status", "")
        basis, phrase = classify_basis(status_cell)
        entries[entry_id] = {
            "id": entry_id,
            "section": section,
            "defect": _plain(row.get("defect") or row.get("capability") or ""),
            "where": _plain(row.get("where") or ""),
            "severity": _plain(row.get("severity") or row.get("scope") or ""),
            "status_verbatim": _plain(status_cell),
            "basis": basis,
            "basis_matched_phrase": phrase,
        }
    return (entries, _sha256_file(path), None)


# ─── item resolution ────────────────────────────────────────────────────────

def resolve_item(item, repo_paths, use_network):
    """Everything git can say about where this item's work actually is."""
    repo = item.get("repo")
    branch = item.get("branch") or ""
    relative = repo_paths.get(repo)
    out = {
        "repo": repo,
        "repo_path": relative,
        "branch": branch or None,
        "base_declared": item.get("base"),
        "worktree": item.get("worktree"),
        "branch_sha": None,
        "base_sha": None,
        "branch_contains_base": None,
        "commits_ahead_of_base": None,
        "package_version_at_branch": None,
        "published": None,
        "problems": [],
    }
    if relative is None:
        out["problems"].append(
            "repo %r has no checkout mapping; pass --repo-path %s=<path>"
            % (repo, repo))
        return out
    absolute = os.path.join(manifest.REPO_ROOT, relative)
    if not os.path.isdir(os.path.join(absolute, ".git")) and not os.path.isdir(absolute):
        out["problems"].append("checkout %s does not exist" % relative)
        return out
    if not branch:
        out["problems"].append(
            "item declares no branch; there is no commit to record. This is a "
            "real state (not-started work), not a tool failure.")
        return out

    ok, value = git(absolute, "rev-parse", "--verify", "%s^{commit}" % branch)
    if not ok:
        out["problems"].append("branch %s does not resolve in %s: %s"
                               % (branch, relative, value))
        return out
    out["branch_sha"] = value

    base = (item.get("base") or "").split("@")[0].strip()
    if base:
        ok, base_sha = git(absolute, "rev-parse", "--verify", "%s^{commit}" % base)
        if ok:
            out["base_sha"] = base_sha
            contains = subprocess.run(
                ("git", "-C", absolute, "merge-base", "--is-ancestor", base_sha, value),
                capture_output=True, text=True)
            out["branch_contains_base"] = (contains.returncode == 0)
            ok, count = git(absolute, "rev-list", "--count", "%s..%s" % (base_sha, value))
            if ok and count.isdigit():
                out["commits_ahead_of_base"] = int(count)
            declared = item.get("base") or ""
            if "@" in declared:
                pinned = declared.split("@", 1)[1].strip()
                if pinned and not base_sha.startswith(pinned.replace("^{commit}", "")):
                    out["problems"].append(
                        "base declared as %s but %s resolves to %s today"
                        % (declared, base, base_sha[:12]))
        else:
            out["problems"].append("base %s does not resolve: %s" % (base, base_sha))

    ok, blob = git(absolute, "show", "%s:package.json" % branch)
    if ok:
        try:
            out["package_version_at_branch"] = json.loads(blob).get("version")
        except ValueError:
            out["problems"].append("package.json at %s is not valid JSON" % branch)

    out["published"] = _publication(absolute, branch, use_network)
    return out


def _publication(absolute, branch, use_network):
    """Has this branch left the machine? Say HOW the answer was obtained.

    By default: local remote-tracking refs only, which is a statement about
    what this checkout last fetched, NOT about the remote. Rule 0 forbids
    anything leaving this machine; `git ls-remote` is a read, not a push, so it
    is available behind --network and off by default. The distinction is in the
    record because "we checked the remote" and "we checked our stale copy of
    the remote" are different facts and only one of them is a measurement of
    the remote.
    """
    tracking = "refs/remotes/origin/%s" % branch
    ok, _ = git(absolute, "rev-parse", "--verify", tracking)
    result = {
        "method": "local remote-tracking refs (no network)",
        "remote_tracking_ref": tracking,
        "remote_tracking_present": bool(ok),
        "remote_checked": False,
        "present_on_remote": None,
    }
    if use_network:
        ok, value = git(absolute, "ls-remote", "--heads", "origin", branch)
        result["method"] = "git ls-remote --heads origin (read-only network)"
        result["remote_checked"] = True
        result["present_on_remote"] = bool(ok and value.strip())
        if not ok:
            result["ls_remote_error"] = value
    return result


# ─── test-evidence extraction ───────────────────────────────────────────────

MOCHA = re.compile(r"^\s*(\d+)\s+(passing|failing|pending)\b", re.M)


def summarise_output(text):
    """Name what the command actually said, without paraphrasing it."""
    summary = {"passing": None, "failing": None, "pending": None,
               "last_line": None, "shape": "unrecognised"}
    if not text:
        summary["shape"] = "no output"
        return summary
    counts = {word: int(number) for number, word in MOCHA.findall(text)}
    if counts:
        summary["shape"] = "mocha"
        summary["passing"] = counts.get("passing", 0)
        summary["failing"] = counts.get("failing", 0)
        summary["pending"] = counts.get("pending", 0)
    lines = [line for line in text.splitlines() if line.strip()]
    if lines:
        summary["last_line"] = _one_line(lines[-1])[:300]
    return summary


def tail(text, count=TAIL_LINES):
    lines = [line.rstrip() for line in (text or "").splitlines()]
    return lines[-count:]


# ─── capture ────────────────────────────────────────────────────────────────

def capture(args):
    doc = manifest.load(args.manifest)
    problems = manifest.validate(doc)
    if problems:
        raise SystemExit(
            "verification-record: the manifest does not validate; a record built "
            "from an invalid manifest would be a record of nothing.\n" +
            "\n".join("  FAIL  %s" % p for p in problems))

    repo_paths = dict(DEFAULT_REPO_PATHS)
    for pair in args.repo_path:
        name, _, path = pair.partition("=")
        repo_paths[name.strip()] = path.strip()

    enabled = set(status.DEFAULT_KINDS)
    if args.integration:
        enabled.add("integration")
    if args.network:
        enabled.add("network")

    chosen = status.select(doc["items"], set(args.ids), set(args.parcels),
                           set(args.states))
    if not chosen:
        raise SystemExit("verification-record: no items matched the selection")
    chosen_ids = {i["id"] for i in chosen}

    register_path = os.path.join(manifest.REPO_ROOT, args.register)
    register, register_digest, register_error = parse_register(register_path)

    record = {
        "record_version": RECORD_VERSION,
        "kind": "verification-record",
        "release": {
            "name": args.release,
            "captured_at": args.captured_at,
            "captured_at_source": "--captured-at argument (this tool never reads a clock)",
            "generator": GENERATOR,
            "generator_sha256": _sha256_file(os.path.abspath(__file__)),
            "selection": {
                "ids": sorted(args.ids),
                "parcels": sorted(args.parcels),
                "states": sorted(args.states),
            },
            "gate_kinds_enabled": sorted(enabled),
            "gate_kinds_disabled": sorted(
                set(manifest.VALID_GATE_KINDS) - enabled),
            "inputs": {
                "manifest": os.path.relpath(args.manifest, manifest.REPO_ROOT),
                "manifest_sha256": _sha256_file(args.manifest),
                "manifest_measured_at": (doc.get("meta") or {}).get("measured_at"),
                "register": args.register,
                "register_sha256": register_digest,
                "register_entries_parsed": len(register),
            },
        },
        "control_surface": {},
        "repos": {},
        "items": [],
        "register_closure": [],
        "test_evidence": [],
        "not_verified": [],
        "totals": {},
    }
    if register_error:
        record["release"]["inputs"]["register_error"] = register_error

    # --- the control surface itself -----------------------------------------
    ok, head = git(manifest.REPO_ROOT, "rev-parse", "HEAD")
    ok_dirty, dirty = git(manifest.REPO_ROOT, "status", "--porcelain")
    record["control_surface"] = {
        "path": manifest.REPO_ROOT,
        "head": head if ok else None,
        "working_tree_clean": (ok_dirty and not dirty.strip()),
        "uncommitted_paths": len([l for l in dirty.splitlines() if l.strip()])
        if ok_dirty else None,
    }

    # --- the product checkouts ----------------------------------------------
    for name in sorted({i.get("repo") for i in chosen if i.get("repo")}):
        relative = repo_paths.get(name)
        block = {"path": relative}
        if relative:
            absolute = os.path.join(manifest.REPO_ROOT, relative)
            ok, value = git(absolute, "rev-parse", "HEAD")
            block["head"] = value if ok else None
            ok, value = git(absolute, "rev-parse", "--abbrev-ref", "HEAD")
            block["head_ref"] = value if ok else None
            ok, value = git(absolute, "config", "--get", "remote.origin.url")
            block["origin"] = value if ok else None
            ok, value = git(absolute, "status", "--porcelain")
            block["working_tree_clean"] = (ok and not value.strip())
        record["repos"][name] = block

    # --- items, gates, evidence ---------------------------------------------
    for item in chosen:
        results = status.evaluate(item, enabled, args.timeout)
        verdict, ran_pass, ran_total, tallies = status.summarise(results)
        resolved = resolve_item(item, repo_paths, args.network)

        gates = []
        for index, (gate, result) in enumerate(zip(item.get("gates") or [], results)):
            kind, payload = manifest.classify_gate(gate)
            entry = {
                "index": index,
                "outcome": result["outcome"],
                "detail": result["detail"],
                "kind": result["kind"],
                "command": result["command"],
                "cwd": result["cwd"],
                "describe": _one_line(payload.get("describe"))
                if kind == "run" else None,
                "no_gate_reason": _one_line(payload) if kind == "no-gate" else None,
            }
            output = result.get("output") or ""
            if result["outcome"] in (status.PASS, status.FAIL):
                entry["output_bytes"] = len(output)
                entry["output_sha256"] = _sha256_text(output)
                entry["output_tail"] = tail(output)
                entry["output_summary"] = summarise_output(output)
            gates.append(entry)

            if kind == "run" and payload.get("kind") in ("unit", "integration"):
                record["test_evidence"].append({
                    "item": item["id"],
                    "gate_index": index,
                    "kind": payload.get("kind"),
                    "command": result["command"],
                    "cwd": result["cwd"] or ".",
                    "outcome": result["outcome"],
                    "detail": result["detail"],
                    "summary": entry.get("output_summary"),
                    "output_sha256": entry.get("output_sha256"),
                    "output_tail": entry.get("output_tail", []),
                })

        claim = None
        claimed = item.get("state")
        if claimed == "ready-to-push" and verdict != "PASS":
            claim = ("state says ready-to-push; the gates measured %s" % verdict)
        elif claimed == "gate-not-met" and verdict == "PASS" and tallies[status.NO_GATE]:
            claim = ("state says gate-not-met, but every RUNNABLE gate passed and "
                     "the failing property sits behind %d no-gate marker(s): the "
                     "claim rests on a recorded measurement this run could not "
                     "reproduce" % tallies[status.NO_GATE])
        elif claimed == "gate-not-met" and verdict == "PASS":
            claim = "state says gate-not-met; every gate that ran passed"

        record["items"].append({
            "id": item["id"],
            "title": _one_line(item.get("title")),
            "parcel": item.get("parcel"),
            "state_claimed": claimed,
            "verdict_measured": verdict,
            "gates_ran_pass": ran_pass,
            "gates_ran_total": ran_total,
            "tallies": {k: tallies.get(k, 0) for k in
                        (status.PASS, status.FAIL, status.MISSING,
                         status.SKIP, status.NO_GATE)},
            "claim_divergence": claim,
            "semver": item.get("semver"),
            "ships_to_operators_today": item.get("ships_to_operators_today"),
            "operator_visible": _one_line(item.get("operator_visible")) or None,
            "register": list(item.get("register") or []),
            "blocks_on": list(item.get("blocks_on") or []),
            "resolved": resolved,
            "gates": gates,
        })

    # --- register closure ----------------------------------------------------
    by_entry = {}
    for item in record["items"]:
        for entry_id in item["register"]:
            by_entry.setdefault(entry_id, []).append(item)

    for entry_id in sorted(by_entry, key=_register_sort):
        carriers = by_entry[entry_id]
        known = register.get(entry_id)
        verdicts = sorted({c["verdict_measured"] for c in carriers})
        closure = _closure_state(known, verdicts)
        block = {
            "id": entry_id,
            "carried_by": [c["id"] for c in carriers],
            "carrier_verdicts": {c["id"]: c["verdict_measured"] for c in carriers},
            "closure_state": closure,
            "closed_for_operators": False,
        }
        if known:
            block.update({
                "section": known["section"],
                "defect": known["defect"],
                "where": known["where"],
                "severity": known["severity"],
                "register_status_verbatim": known["status_verbatim"],
                "basis": known["basis"],
                "basis_matched_phrase": known["basis_matched_phrase"],
            })
        else:
            block.update({
                "section": None, "defect": None, "where": None, "severity": None,
                "register_status_verbatim": None,
                "basis": "unstated",
                "basis_matched_phrase": None,
                "parse_note": "id not found in the parsed register tables",
            })
        record["register_closure"].append(block)

    record["not_verified"] = build_gaps(record, register, chosen_ids, doc, enabled)
    record["totals"] = totals(record)
    return record


def _register_sort(entry_id):
    prefix, _, number = entry_id.partition("-")
    return (prefix, int(number) if number.isdigit() else 0)


def _closure_state(known, verdicts):
    """What this release does to a register entry -- deliberately not 'closed'.

    Nothing in this record can close anything. The branches are local; a
    register entry closes for an operator when a human pushes and a maintainer
    merges, which is D12 and outside this tool. So the vocabulary is about the
    CLAIM and the MEASUREMENT, not about the operator's exposure, and
    `closed_for_operators` is hard-coded False for every entry in the record.
    """
    if known is None:
        return "not-in-register"
    fixed = known["status_verbatim"].lower().startswith(("fixed", "partly fixed"))
    if "FAIL" in verdicts:
        return "claimed-fixed-but-a-gate-failed" if fixed else "open-and-a-gate-failed"
    if "UNMEASURED" in verdicts or "NO-INSTRUMENT" in verdicts:
        return "claimed-fixed-but-unmeasured" if fixed else "open-and-unmeasured"
    if fixed:
        return "claimed-fixed-gates-pass"
    return "open-in-register-gates-pass"


# ─── the gaps section ───────────────────────────────────────────────────────

def build_gaps(record, register, chosen_ids, doc, enabled):
    """Everything this record did NOT establish, and why.

    Assembled MECHANICALLY from the same data the rest of the record is built
    from, never hand-listed, because a hand-listed gaps section records what
    somebody remembered to be missing. Every category below is derived:
    no-gate markers are in the manifest, skips and missing instruments come out
    of the runner, the basis categories come out of the register parse, and the
    scope gap is arithmetic on the selection.
    """
    gaps = []

    def add(category, scope, statement, why):
        gaps.append({"category": category, "scope": scope,
                     "statement": _one_line(statement), "why": _one_line(why)})

    for item in record["items"]:
        for gate in item["gates"]:
            if gate["outcome"] == status.NO_GATE:
                add("no-instrument-declared", "%s gates[%d]" % (item["id"], gate["index"]),
                    "No gate exists for this property; the manifest records why.",
                    gate["no_gate_reason"])
            elif gate["outcome"] == status.SKIP:
                add("gate-not-run", "%s gates[%d]" % (item["id"], gate["index"]),
                    "%s -- NOT RUN in this capture." % (gate["command"] or "?"),
                    "%s This capture enabled kinds %s. A skipped gate is not a pass."
                    % (gate["detail"], ",".join(sorted(enabled))))
            elif gate["outcome"] == status.MISSING:
                add("gate-script-absent", "%s gates[%d]" % (item["id"], gate["index"]),
                    "%s -- the instrument does not exist." % (gate["command"] or "?"),
                    "%s Nothing was measured for this property, which is not the "
                    "same as measuring it and finding a defect." % gate["detail"])
        if item["verdict_measured"] == "UNMEASURED":
            add("item-unmeasured", item["id"],
                "Nothing ran for this item at all; it appears in the record with "
                "no measurement behind it.",
                "Every gate it carries is a no-gate marker or was skipped. Never "
                "read UNMEASURED as green.")
        if item["claim_divergence"]:
            add("claim-diverges-from-measurement", item["id"],
                item["claim_divergence"],
                "The manifest state is a claim; the gate result is the "
                "measurement. Where they disagree the record carries both.")
        for problem in item["resolved"].get("problems") or []:
            add("branch-unresolved", item["id"],
                "Could not resolve the work to a commit: %s" % problem,
                "An item whose branch does not resolve has no SHA in this record, "
                "so nothing about its content was verified here.")
        published = item["resolved"].get("published") or {}
        if published and not published.get("remote_checked"):
            add("publication-unverified", item["id"],
                "Whether %s exists on the remote was NOT checked against the "
                "remote." % (item["resolved"].get("branch") or "this branch"),
                "Determined from %s. That is a statement about this checkout's "
                "last fetch, not about the remote. Re-run with --network for a "
                "read-only ls-remote." % published.get("method"))

    for block in record["register_closure"]:
        if block["basis"] == "read-derived":
            add("register-basis-read-derived", block["id"],
                "Register entry %s is READ-DERIVED, not reproduced." % block["id"],
                "Matched %r in its status cell. Rule 3: measured across this "
                "programme, every register claim that had to be retracted was "
                "derived from reading source. A read-derived entry in a release "
                "is a request to go and run it."
                % (block["basis_matched_phrase"] or ""))
        elif block["basis"] == "unstated":
            add("register-basis-unstated", block["id"],
                "Register entry %s does not state whether it was read or run."
                % block["id"],
                "No phrase in its status cell says. The classifier will not "
                "infer one from measurement-shaped prose, because inferring a "
                "reproduction is exactly the laundering rule 3 exists to stop. "
                "Status cell verbatim: %s"
                % (block["register_status_verbatim"] or "(entry not found in the "
                   "register tables at all)"))
        if block["closure_state"] != "claimed-fixed-gates-pass":
            add("register-entry-not-demonstrated", block["id"],
                "Closure state is %s." % block["closure_state"],
                "This release does not demonstrate that %s is repaired."
                % block["id"])

    # Scope: what the selection left out, stated as a number rather than implied.
    everything = {i["id"] for i in doc["items"]}
    excluded = sorted(everything - chosen_ids)
    if excluded:
        add("out-of-scope", "queue/work-queue.yaml",
            "%d of the %d items in the manifest are NOT in this record."
            % (len(excluded), len(everything)),
            "Selection was ids=%s parcels=%s states=%s. Excluded: %s"
            % (record["release"]["selection"]["ids"] or "-",
               record["release"]["selection"]["parcels"] or "-",
               record["release"]["selection"]["states"] or "-",
               ", ".join(excluded)))

    # Register entries that exist, are not fixed, and are untouched here.
    touched = {b["id"] for b in record["register_closure"]}
    untouched_open = sorted(
        (e for e in register.values()
         if e["id"] not in touched
         and not e["status_verbatim"].lower().startswith(("fixed", "partly fixed",
                                                          "landed", "closed",
                                                          "wontfix"))),
        key=lambda e: _register_sort(e["id"]))
    if untouched_open:
        add("register-untouched", DEFAULT_REGISTER,
            "%d register entries are not fixed and are not carried by anything in "
            "this release." % len(untouched_open),
            "Not a defect in the release; a statement of what shipping it does "
            "not address. Ids: %s"
            % ", ".join(e["id"] for e in untouched_open))

    # A limitation of THIS record, not of the release. It belongs here for the
    # same reason everything else does: the reader must be able to see what the
    # instrument could not see.
    add("record-method", "basis classification",
        "The basis of each register entry was read ONLY from its row in the "
        "register's summary tables (sections 1, 1b, 1c), not from its detail "
        "section in section 2 / 2b.",
        "The register's own header records that provenance marking is not yet "
        "consistent between the two - three entries carry a `reproduced` block "
        "prepended above a body that still reads `not reproduced against a live "
        "instance`. Where the table and the detail disagree, this record follows "
        "the table and does not reconcile them.")
    add("record-method", "gate output",
        "Only the last %d lines of each gate's output are stored, beside a "
        "sha256 of the whole of it." % TAIL_LINES,
        "The digest lets a reader prove a full log they hold is the one this "
        "record was taken from; it does not let them reconstruct it. Full logs "
        "were not retained by this capture.")
    add("record-method", "reproducibility",
        "This record is NOT byte-reproducible end to end, and the claim that it "
        "is has been narrowed to what was measured.",
        "Two captures of this release were diffed field by field. STABLE: "
        "resolved SHAs, commits-ahead counts, every gate outcome, every item "
        "verdict, every register closure state and basis, the COUNTED test "
        "summaries (passing/failing/pending) and every entry in this section. "
        "MOVES: the gate transcripts output_tail, output_bytes and "
        "output_sha256 - 25 of 164 transcript fields moved - because the "
        "commands are not deterministic (mocha prints its own millisecond "
        "timings, node prints its pid). ONE NON-TRANSCRIPT FIELD MOVES WITH "
        "THEM and an earlier draft of this record wrongly implied it did not: "
        "output_summary.last_line, where a benchmark ends its output with a "
        "duration - P0-D's coercion benchmark gave duration_ms 282.795205 on "
        "one capture and 278.901709 on the next, and that string reaches both "
        "the gate summary and the test evidence. So two captures may be diffed "
        "on outcomes, verdicts, bases and gaps, and must NOT be diffed on "
        "digests or on a last_line that quotes a duration.")

    if not record["control_surface"].get("working_tree_clean"):
        add("capture-environment", "control surface",
            "The control-surface working tree was NOT clean at capture "
            "(%s uncommitted path(s))."
            % record["control_surface"].get("uncommitted_paths"),
            "The inputs are digested by content (manifest_sha256, "
            "register_sha256) so the record is still re-derivable, but the "
            "inputs were not committed when it was taken.")

    return gaps


def totals(record):
    gate_outcomes = {}
    for item in record["items"]:
        for gate in item["gates"]:
            gate_outcomes[gate["outcome"]] = gate_outcomes.get(gate["outcome"], 0) + 1
    verdicts = {}
    for item in record["items"]:
        verdicts[item["verdict_measured"]] = verdicts.get(item["verdict_measured"], 0) + 1
    bases = {}
    for block in record["register_closure"]:
        bases[block["basis"]] = bases.get(block["basis"], 0) + 1
    categories = {}
    for gap in record["not_verified"]:
        categories[gap["category"]] = categories.get(gap["category"], 0) + 1
    return {
        "items": len(record["items"]),
        "item_verdicts": dict(sorted(verdicts.items())),
        "gate_outcomes": dict(sorted(gate_outcomes.items())),
        "register_entries": len(record["register_closure"]),
        "register_basis": dict(sorted(bases.items())),
        "test_commands": len(record["test_evidence"]),
        "not_verified": len(record["not_verified"]),
        "not_verified_by_category": dict(sorted(categories.items())),
    }


# ─── rendering ──────────────────────────────────────────────────────────────

BANNER = """<!--
  ============================================================================
  GENERATED FILE - MUST NOT BE HAND-EDITED, AND MUST NOT BE EDITED AT ALL.

  Source of truth:  verification-record.json (beside this file)
  Generator:        tools/queue/verification-record.py

  A verification record is captured ONCE, at release time, and is never
  revised. If something changes -- a gate starts passing, a branch moves, a
  register entry is reproduced -- that is a NEW record with a new
  captured_at, not an edit to this one. A record that is edited after the fact
  is not a record; it is a claim about the past that nothing can check.
  ============================================================================
-->
"""


def _wrap(text, width=94):
    body = _one_line(text)
    return "\n".join(textwrap.wrap(body, width=width)) if body else ""


def render(record):
    release = record["release"]
    lines = [BANNER, "# Verification record &mdash; %s" % release["name"], ""]
    lines.append("**Captured at %s.** Generated from `verification-record.json` by "
                 "`%s`. Do not edit this file or its JSON; capture a new record "
                 "instead." % (release["captured_at"], release["generator"]))
    lines.append("")
    lines.append("This is the quality-system record of what was actually checked "
                 "when this release was cut. It is not a plan and not a changelog. "
                 "It contains failures and gaps on purpose: a record that shows "
                 "only passes has been edited, selected or fabricated.")
    lines.append("")

    totals_block = record["totals"]
    lines.append("## Headline")
    lines.append("")
    lines.append("| | |")
    lines.append("|---|---|")
    lines.append("| items in this release | %d |" % totals_block["items"])
    lines.append("| item verdicts | %s |" % _kv(totals_block["item_verdicts"]))
    lines.append("| gate outcomes | %s |" % _kv(totals_block["gate_outcomes"]))
    lines.append("| register entries carried | %d |" % totals_block["register_entries"])
    lines.append("| register basis (rule 3) | %s |" % _kv(totals_block["register_basis"]))
    lines.append("| test commands captured | %d |" % totals_block["test_commands"])
    lines.append("| **things NOT verified** | **%d** |" % totals_block["not_verified"])
    lines.append("")
    lines.append("Nothing in this record is closed for an operator. Every branch "
                 "below is local and unpushed unless the publication line says "
                 "otherwise; a defect stops reaching operators when a human "
                 "pushes and a maintainer merges, which is outside this record.")
    lines.append("")

    # --- provenance ---------------------------------------------------------
    lines.append("## How this record was taken")
    lines.append("")
    lines.append("| | |")
    lines.append("|---|---|")
    lines.append("| captured_at | `%s` |" % release["captured_at"])
    lines.append("| timestamp source | %s |" % release["captured_at_source"])
    lines.append("| generator | `%s` |" % release["generator"])
    lines.append("| generator sha256 | `%s` |" % (release["generator_sha256"] or "-"))
    selection = release["selection"]
    lines.append("| selection | ids=`%s` parcels=`%s` states=`%s` |" % (
        ",".join(selection["ids"]) or "-",
        ",".join(selection["parcels"]) or "-",
        ",".join(selection["states"]) or "-"))
    lines.append("| gate kinds RUN | `%s` |" % ",".join(release["gate_kinds_enabled"]))
    lines.append("| gate kinds NOT run | `%s` |" % (
        ",".join(release["gate_kinds_disabled"]) or "-"))
    inputs = release["inputs"]
    lines.append("| manifest | `%s` sha256 `%s` |" % (
        inputs["manifest"], (inputs["manifest_sha256"] or "-")[:16]))
    lines.append("| register | `%s` sha256 `%s` (%d entries parsed) |" % (
        inputs["register"], (inputs["register_sha256"] or "-")[:16],
        inputs["register_entries_parsed"]))
    surface = record["control_surface"]
    lines.append("| control surface HEAD | `%s`%s |" % (
        (surface.get("head") or "-")[:12],
        "" if surface.get("working_tree_clean") else
        " (working tree NOT clean: %s uncommitted path(s))"
        % surface.get("uncommitted_paths")))
    lines.append("")
    for name, block in sorted(record["repos"].items()):
        lines.append("- **%s** &mdash; `%s` at `%s` (`%s`), origin `%s`%s" % (
            name, block.get("path"), (block.get("head") or "-")[:12],
            block.get("head_ref"), block.get("origin"),
            "" if block.get("working_tree_clean") else " **working tree not clean**"))
    lines.append("")

    # --- items --------------------------------------------------------------
    lines.append("---")
    lines.append("")
    lines.append("## What is in the release, and what each item resolved to")
    lines.append("")
    lines.append("`state (claimed)` is what the manifest asserts. `verdict "
                 "(measured)` is what the gates said when this record was taken. "
                 "Where they disagree, both are printed and the disagreement is "
                 "in the gaps section.")
    lines.append("")
    lines.append("| id | repo | branch | commit | ahead of base | state (claimed) | "
                 "verdict (measured) | gates |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for item in record["items"]:
        resolved = item["resolved"]
        tallies = item["tallies"]
        extras = []
        for label, key in (("skip", status.SKIP), ("no-gate", status.NO_GATE),
                           ("missing", status.MISSING)):
            if tallies.get(key):
                extras.append("%d %s" % (tallies[key], label))
        lines.append("| `%s` | %s | `%s` | `%s` | %s | `%s` | **%s** | %d/%d%s |" % (
            item["id"], resolved.get("repo"), resolved.get("branch") or "-",
            (resolved.get("branch_sha") or "unresolved")[:12],
            "-" if resolved.get("commits_ahead_of_base") is None
            else resolved["commits_ahead_of_base"],
            item["state_claimed"], item["verdict_measured"],
            item["gates_ran_pass"], item["gates_ran_total"],
            (" (%s)" % ", ".join(extras)) if extras else ""))
    lines.append("")

    for item in record["items"]:
        lines.extend(_render_item(item))

    # --- register -----------------------------------------------------------
    lines.append("---")
    lines.append("")
    lines.append("## Register entries this release touches, and each entry's basis")
    lines.append("")
    lines.append(_wrap(
        "Rule 3 of this programme: read-derived versus reproduced. Measured "
        "across the programme, every register claim that had to be retracted "
        "was derived from READING source; not one that began with a "
        "REPRODUCTION has been. So this table labels each entry from the words "
        "in its own register row, quotes the row, and names the phrase that "
        "decided it. `unstated` means the register does not say -- it is not a "
        "guess, and it is a finding about the register, not about the defect."))
    lines.append("")
    lines.append("| entry | basis | closure state | carried by | severity | where |")
    lines.append("|---|---|---|---|---|---|")
    for block in record["register_closure"]:
        lines.append("| `%s` | **%s** | `%s` | %s | %s | %s |" % (
            block["id"], block["basis"], block["closure_state"],
            ", ".join("`%s`" % c for c in block["carried_by"]),
            (block.get("severity") or "-").replace("|", "\\|"),
            (block.get("where") or "-").replace("|", "\\|")))
    lines.append("")
    for block in record["register_closure"]:
        lines.append("**`%s`** &mdash; %s" % (
            block["id"], block.get("defect") or "_not found in the register tables_"))
        lines.append("")
        lines.append("- basis: **%s**%s" % (
            block["basis"],
            " (matched %r)" % block["basis_matched_phrase"]
            if block["basis_matched_phrase"] else ""))
        lines.append("- register status, verbatim: %s"
                     % (block.get("register_status_verbatim") or "_absent_"))
        lines.append("- carried by: %s" % ", ".join(
            "`%s` (%s)" % (k, v) for k, v in sorted(
                block["carrier_verdicts"].items())))
        lines.append("- closure state: `%s`; closed for operators: **%s**" % (
            block["closure_state"],
            "yes" if block["closed_for_operators"] else "no"))
        lines.append("")

    # --- tests --------------------------------------------------------------
    lines.append("---")
    lines.append("")
    lines.append("## Test evidence")
    lines.append("")
    if not record["test_evidence"]:
        lines.append("_No `unit` or `integration` gate is declared by any item in "
                     "this release. That is itself a gap and is recorded below._")
        lines.append("")
    else:
        lines.append("The exact command, where it ran, and what it said. A command "
                     "that was not run in this capture is listed with outcome "
                     "`SKIP` and no summary &mdash; it is not a pass.")
        lines.append("")
        lines.append("| item | kind | command | cwd | outcome | summary |")
        lines.append("|---|---|---|---|---|---|")
        for evidence in record["test_evidence"]:
            summary = evidence.get("summary") or {}
            if evidence["outcome"] in (status.PASS, status.FAIL):
                if summary.get("shape") == "mocha":
                    cell = "%s passing, %s failing, %s pending" % (
                        summary.get("passing"), summary.get("failing"),
                        summary.get("pending"))
                else:
                    cell = "%s &mdash; last line: `%s`" % (
                        evidence["detail"],
                        _one_line(summary.get("last_line") or "")[:90])
            else:
                cell = "_not run: %s_" % evidence["detail"]
            lines.append("| `%s` | %s | `%s` | `%s` | **%s** | %s |" % (
                evidence["item"], evidence["kind"],
                (evidence["command"] or "-").replace("|", "\\|"),
                evidence["cwd"], evidence["outcome"],
                cell.replace("|", "\\|")))
        lines.append("")
        for evidence in record["test_evidence"]:
            if evidence["outcome"] != status.FAIL:
                continue
            lines.append("**Failing: `%s` gates[%d]** &mdash; `%s`"
                         % (evidence["item"], evidence["gate_index"],
                            evidence["command"]))
            lines.append("")
            lines.append("```")
            lines.extend(evidence.get("output_tail") or ["(no output)"])
            lines.append("```")
            lines.append("")

    # --- gaps ---------------------------------------------------------------
    lines.append("---")
    lines.append("")
    lines.append("## What was NOT verified")
    lines.append("")
    lines.append(_wrap(
        "This section is mandatory and the generator refuses to write a record "
        "whose gaps section is empty. It is assembled mechanically from the "
        "same data as everything above -- no-gate markers from the manifest, "
        "skips and absent instruments from the runner, bases from the register "
        "parse, scope from arithmetic on the selection -- because a "
        "hand-written gaps section records only what somebody remembered was "
        "missing."))
    lines.append("")
    lines.append("**%d entries.**" % len(record["not_verified"]))
    lines.append("")
    by_category = {}
    for gap in record["not_verified"]:
        by_category.setdefault(gap["category"], []).append(gap)
    lines.append("| category | n |")
    lines.append("|---|---|")
    for category in sorted(by_category):
        lines.append("| `%s` | %d |" % (category, len(by_category[category])))
    lines.append("")
    for category in sorted(by_category):
        lines.append("### `%s`" % category)
        lines.append("")
        for gap in by_category[category]:
            lines.append("- **%s** &mdash; %s" % (gap["scope"], gap["statement"]))
            if gap["why"]:
                lines.append("  - %s" % gap["why"])
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*End of verification record. Machine-readable source: "
                 "`verification-record.json`. Captured `%s`. Never edited.*"
                 % release["captured_at"])
    lines.append("")
    return "\n".join(lines)


def _kv(mapping):
    return ", ".join("%s=%s" % (k, v) for k, v in mapping.items()) or "-"


def _render_item(item):
    resolved = item["resolved"]
    lines = ["### `%s` &mdash; %s" % (item["id"], item["title"]), ""]
    lines.append("| | |")
    lines.append("|---|---|")
    lines.append("| repo | `%s` (`%s`) |" % (resolved.get("repo"),
                                             resolved.get("repo_path")))
    lines.append("| branch | `%s` |" % (resolved.get("branch") or "-"))
    lines.append("| commit | `%s` |" % (resolved.get("branch_sha") or "UNRESOLVED"))
    lines.append("| base declared | `%s` |" % (resolved.get("base_declared") or "-"))
    lines.append("| base resolved | `%s` |" % (resolved.get("base_sha") or "-"))
    lines.append("| branch contains base | %s |" % _tri(resolved.get("branch_contains_base")))
    lines.append("| commits ahead of base | %s |" % (
        "-" if resolved.get("commits_ahead_of_base") is None
        else resolved["commits_ahead_of_base"]))
    lines.append("| package version at branch | `%s` |" % (
        resolved.get("package_version_at_branch") or "-"))
    published = resolved.get("published") or {}
    lines.append("| published | %s |" % _published(published))
    lines.append("| state (claimed) | `%s` |" % item["state_claimed"])
    lines.append("| verdict (measured) | **%s** |" % item["verdict_measured"])
    lines.append("| semver | `%s` |" % item["semver"])
    if item["register"]:
        lines.append("| register | %s |" % ", ".join("`%s`" % r for r in item["register"]))
    lines.append("")
    if item["claim_divergence"]:
        lines.append("> **CLAIM DIVERGES FROM MEASUREMENT.** %s" % item["claim_divergence"])
        lines.append("")
    if item["operator_visible"]:
        lines.append("**What an operator sees.** %s" % item["operator_visible"])
        lines.append("")
    lines.append("**Gates, and what each one actually said.**")
    lines.append("")
    for gate in item["gates"]:
        if gate["outcome"] == status.NO_GATE:
            lines.append("- **NO-GATE** &mdash; %s" % gate["no_gate_reason"])
            continue
        where = " _(cwd: `%s`)_" % gate["cwd"] if gate["cwd"] else ""
        lines.append("- **%s** `[%s]`%s `%s`" % (
            gate["outcome"], gate["kind"], where,
            (gate["command"] or "-").replace("|", "\\|")))
        lines.append("  - %s" % gate["detail"])
        if gate.get("describe"):
            lines.append("  - intent: %s" % gate["describe"])
        summary = gate.get("output_summary") or {}
        if summary.get("shape") == "mocha":
            lines.append("  - measured: %s passing, %s failing, %s pending" % (
                summary.get("passing"), summary.get("failing"), summary.get("pending")))
        if gate["outcome"] == status.FAIL and gate.get("output_tail"):
            lines.append("")
            lines.append("  ```")
            for line in gate["output_tail"]:
                lines.append("  %s" % line)
            lines.append("  ```")
    lines.append("")
    for problem in resolved.get("problems") or []:
        lines.append("> **UNRESOLVED.** %s" % problem)
        lines.append("")
    return lines


def _tri(value):
    return "-" if value is None else ("yes" if value else "**no**")


def _published(published):
    if not published:
        return "-"
    if published.get("remote_checked"):
        return "%s &mdash; on remote: **%s**" % (
            published["method"],
            "yes" if published.get("present_on_remote") else "NO")
    return ("%s &mdash; remote-tracking ref `%s` %s. **The remote itself was not "
            "contacted.**" % (published["method"], published["remote_tracking_ref"],
                              "exists" if published.get("remote_tracking_present")
                              else "does not exist"))


# ─── writing ────────────────────────────────────────────────────────────────

def serialise(record):
    return json.dumps(record, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def write(record, out_dir, check=False):
    """Write both halves. Refuses on an empty gaps section -- invariant 1."""
    if not record.get("not_verified"):
        sys.stderr.write(
            "verification-record: REFUSING TO WRITE. The `not_verified` section "
            "is empty.\n"
            "A record that omits its own gaps is worse than no record: it reads "
            "like completeness.\n"
            "There is no flag to override this. Either the selection is empty, "
            "or the gap builder\nis broken -- both are bugs, and neither is a "
            "clean release.\n")
        return 2

    json_text = serialise(record)
    md_text = render(record)
    json_path = os.path.join(out_dir, "verification-record.json")
    md_path = os.path.join(out_dir, "verification-record.md")

    if check:
        drift = 0
        for path, text in ((json_path, json_text), (md_path, md_text)):
            if not os.path.exists(path):
                print("MISSING  %s" % path)
                drift = 1
                continue
            with open(path, "r", encoding="utf-8") as handle:
                if handle.read() != text:
                    print("DRIFT    %s differs from the record it claims to be" % path)
                    drift = 1
                else:
                    print("OK       %s" % os.path.relpath(path, manifest.REPO_ROOT))
        return drift

    os.makedirs(out_dir, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as handle:
        handle.write(json_text)
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write(md_text)
    print("verification-record  %s" % record["release"]["name"])
    print("  captured_at %s" % record["release"]["captured_at"])
    print("  %s  (%d bytes)" % (os.path.relpath(json_path, manifest.REPO_ROOT),
                                len(json_text)))
    print("  %s  (%d bytes)" % (os.path.relpath(md_path, manifest.REPO_ROOT),
                                len(md_text)))
    totals_block = record["totals"]
    print("  items=%d  verdicts=%s" % (totals_block["items"],
                                       _kv(totals_block["item_verdicts"])))
    print("  gates=%s" % _kv(totals_block["gate_outcomes"]))
    print("  register basis=%s" % _kv(totals_block["register_basis"]))
    print("  NOT VERIFIED=%d entries across %d categories"
          % (totals_block["not_verified"],
             len(totals_block["not_verified_by_category"])))
    return 0


# ─── self-test: prove the record is not vacuous ─────────────────────────────

def self_test(args):
    """Rule 2: a check that has never failed is not yet evidence.

    Take the real manifest, find an item in the selection whose gates all PASS,
    write a COPY of the manifest with one of that item's gates replaced by a
    command that cannot succeed, capture a record from the copy, and assert
    three things about the second record that a record which quietly swallowed
    the failure would not satisfy:

      * the item's verdict moved from PASS to FAIL;
      * the gate appears with outcome FAIL and the failing command's output;
      * the register entries that item carries moved off
        `claimed-fixed-gates-pass`.

    Nothing is written to the real manifest and nothing is written to the real
    release directory. The copy lives wherever --self-test-dir says.
    """
    import shutil

    workdir = args.self_test_dir or os.path.join(
        manifest.REPO_ROOT, "tools", "queue", ".self-test")
    os.makedirs(workdir, exist_ok=True)

    baseline = capture(args)
    passing = [i for i in baseline["items"]
               if i["verdict_measured"] == "PASS" and i["gates_ran_total"] > 0]
    if not passing:
        print("self-test: no PASSing item in the selection to break; inconclusive.")
        return 2
    target = passing[0]
    gate_index = next(g["index"] for g in target["gates"]
                      if g["outcome"] == status.PASS)

    print("BEFORE  %s  verdict=%s  gates %d/%d" % (
        target["id"], target["verdict_measured"],
        target["gates_ran_pass"], target["gates_ran_total"]))
    before_gate = next(g for g in target["gates"] if g["index"] == gate_index)
    print("        gates[%d] %s  %s" % (gate_index, before_gate["outcome"],
                                        before_gate["command"]))
    print("        register: %s" % ", ".join(
        "%s=%s" % (b["id"], b["closure_state"])
        for b in baseline["register_closure"] if target["id"] in b["carried_by"]))

    import yaml
    with open(args.manifest, "r", encoding="utf-8") as handle:
        doc = yaml.safe_load(handle)
    for item in doc["items"]:
        if item.get("id") == target["id"]:
            item["gates"][gate_index] = {
                "run": "echo 'ABLATION: this gate is broken on purpose' >&2; exit 7",
                "kind": item["gates"][gate_index].get("kind", "static"),
                "describe": "SELF-TEST ABLATION - not a real gate",
            }
    broken_manifest = os.path.join(workdir, "work-queue.ablated.yaml")
    with open(broken_manifest, "w", encoding="utf-8") as handle:
        yaml.safe_dump(doc, handle, sort_keys=False, width=200)

    ablated_args = argparse.Namespace(**vars(args))
    ablated_args.manifest = broken_manifest
    after = capture(ablated_args)
    after_item = next(i for i in after["items"] if i["id"] == target["id"])
    after_gate = next(g for g in after_item["gates"] if g["index"] == gate_index)

    print("AFTER   %s  verdict=%s  gates %d/%d" % (
        after_item["id"], after_item["verdict_measured"],
        after_item["gates_ran_pass"], after_item["gates_ran_total"]))
    print("        gates[%d] %s  %s" % (gate_index, after_gate["outcome"],
                                        after_gate["detail"]))
    print("        output tail: %s" % " / ".join(after_gate.get("output_tail") or []))
    print("        register: %s" % ", ".join(
        "%s=%s" % (b["id"], b["closure_state"])
        for b in after["register_closure"] if after_item["id"] in b["carried_by"]))

    rendered = render(after)
    checks = [
        ("item verdict moved PASS -> FAIL",
         target["verdict_measured"] == "PASS" and after_item["verdict_measured"] == "FAIL"),
        ("the broken gate is recorded as FAIL",
         after_gate["outcome"] == status.FAIL),
        ("the failing command's own output is in the record",
         any("ABLATION" in line for line in after_gate.get("output_tail") or [])),
        ("the Markdown shows the failure, not a pass",
         ("**FAIL**" in rendered or "| **FAIL**" in rendered)
         and "ABLATION" in rendered),
        ("register entries moved off claimed-fixed-gates-pass",
         all(b["closure_state"] != "claimed-fixed-gates-pass"
             for b in after["register_closure"]
             if after_item["id"] in b["carried_by"]) or
         not [b for b in after["register_closure"]
              if after_item["id"] in b["carried_by"]]),
        ("the gaps section grew",
         len(after["not_verified"]) > len(baseline["not_verified"])),
    ]
    print("")
    failed = 0
    for label, ok in checks:
        print("  %-4s %s" % ("OK" if ok else "FAIL", label))
        if not ok:
            failed += 1
    shutil.rmtree(workdir, ignore_errors=True)
    print("")
    if failed:
        print("self-test: %d assertion(s) failed. The record is NOT proven "
              "non-vacuous." % failed)
        return 1
    print("self-test: the generator reports an injected gate failure as a "
          "failure, in both halves of the record.")
    return 0


# ─── cli ────────────────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="capture the verification record for a named release")
    parser.add_argument("--release", help="release name, e.g. cgm-remote-monitor-15.0.9")
    parser.add_argument("--captured-at",
                        help="ISO-8601 capture timestamp. REQUIRED for a capture. "
                             "This tool never reads a clock, so a record is "
                             "reproducible.")
    parser.add_argument("--out-dir", help="directory to write both halves into")
    parser.add_argument("--manifest", default=manifest.MANIFEST_PATH)
    parser.add_argument("--register", default=DEFAULT_REGISTER)
    parser.add_argument("--id", action="append", default=[], dest="ids")
    parser.add_argument("--parcel", action="append", default=[], dest="parcels")
    parser.add_argument("--state", action="append", default=[], dest="states")
    parser.add_argument("--repo-path", action="append", default=[],
                        metavar="NAME=PATH",
                        help="override the checkout that owns a repo's branches")
    parser.add_argument("--integration", action="store_true",
                        help="ALSO run gates that need MongoDB")
    parser.add_argument("--network", action="store_true",
                        help="ALSO run network gates, and check branch publication "
                             "with a read-only ls-remote. Rule 0 still holds: read, "
                             "never push.")
    parser.add_argument("--timeout", type=int, default=status.DEFAULT_TIMEOUT)
    parser.add_argument("--from-json", help="re-render an existing record instead "
                                            "of capturing a new one")
    parser.add_argument("--check", action="store_true",
                        help="with --from-json: exit 1 if the files on disk differ "
                             "from what the record renders to")
    parser.add_argument("--stdout", action="store_true",
                        help="print the Markdown and write nothing")
    parser.add_argument("--self-test", action="store_true",
                        help="rule 2: break a passing gate and prove the record "
                             "reports the failure")
    parser.add_argument("--self-test-dir")
    args = parser.parse_args(argv)

    if args.from_json:
        with open(args.from_json, "r", encoding="utf-8") as handle:
            record = json.load(handle)
        if args.stdout:
            sys.stdout.write(render(record))
            return 0
        out_dir = args.out_dir or os.path.dirname(os.path.abspath(args.from_json))
        return write(record, out_dir, check=args.check)

    if not args.captured_at:
        parser.error("--captured-at is required. This tool never reads a clock: "
                     "the capture timestamp is an input so that a record can be "
                     "re-derived and diffed.")
    if not ISO8601.match(args.captured_at.strip()):
        parser.error("--captured-at %r is not ISO-8601 (e.g. 2026-09-15T23:10:00Z)"
                     % args.captured_at)
    args.captured_at = args.captured_at.strip()

    if args.self_test:
        args.release = args.release or "self-test"
        return self_test(args)

    if not args.release:
        parser.error("--release is required")

    record = capture(args)
    if args.stdout:
        sys.stdout.write(render(record))
        return 0
    if not args.out_dir:
        parser.error("--out-dir is required (or use --stdout)")
    return write(record, os.path.join(manifest.REPO_ROOT, args.out_dir)
                 if not os.path.isabs(args.out_dir) else args.out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
