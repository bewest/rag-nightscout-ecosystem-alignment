"""emit_packets.py — one bounded review packet per open pull request.

    python3 tools/queue/emit_packets.py            # write reports/reviewer-packets/
    python3 tools/queue/emit_packets.py --check    # exit 1 if any packet is stale

WHY A PACKET AND NOT "PLEASE REVIEW"

This project's last 100 child pull requests were merged with zero human reviews.
Asking somebody to "review Phase 0" asks them to first reconstruct which of ten
branches are coupled, what the register says about each defect, which evidence
document backs which claim, and which gates ran. That is hours of work before
the first line of diff, and it is why the ask has not been taken up.

A packet turns it into a bounded task: one PR, what changed, what was measured,
and — the part that matters most — **what the measurement does not cover**.

THE SECTION THAT EARNS THIS FILE

Every queue item's gates are either a runnable command or an explicit `no-gate:`
marker carrying a reason. Those reasons are, collectively, the most honest
document in the repository: they are the author writing down what they could not
measure, at the time they could not measure it. Scattered through a 200 KB YAML
manifest nobody reads them. Gathered per pull request, under the heading "what
these gates do NOT prove", they are a reviewer's actual worklist.

So this file is a fully generated view — it carries no argument of its own, only
a re-projection of the manifest onto one axis. That is the same test `emit.py`
passes and `emit_views.py` deliberately fails: a document with an argument in it
must not be machine-owned.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import manifest  # noqa: E402

OUT_DIR = os.path.join(manifest.REPO_ROOT, "reports", "reviewer-packets")
PR_BODIES = os.path.join(manifest.REPO_ROOT, "reports", "phase0-pr-bodies")

# States where a human reviewer is the next move. `ready-to-push` is included
# because those items are waiting on review too — they simply have no PR open
# yet, and P0-C is the clearest case in the queue: gate-passing, and waiting on
# a security reviewer who does not exist.
PACKET_STATES = {"in-flight-upstream", "ready-to-push", "needs-decision"}

BANNER = """<!--
  ============================================================================
  GENERATED FILE - MUST NOT BE HAND-EDITED.

  Source of truth:  queue/work-queue.yaml
  Generator:        tools/queue/emit_packets.py   (make packets)
  Staleness check:  python3 tools/queue/emit_packets.py --check

  Review NOTES belong on the pull request, not here. This file is a projection
  of the manifest; anything written into it is destroyed by the next run.
  ============================================================================
-->
"""


def flow(text, width=78):
    body = " ".join(str(text or "").split())
    return "\n".join(textwrap.wrap(body, width=width)) if body else ""


def pr_number(item):
    """See emit_views.pr_numbers for why this is a fallback and not the rule.

    A declared `pr:` wins; an empty list means "this item is not a PR" and is
    NOT the same as saying nothing, which is what lets a packet stop guessing.
    """
    if "pr" in item:
        declared = item["pr"]
        if declared is None:
            declared = []
        if not isinstance(declared, (list, tuple)):
            declared = [declared]
        found = sorted({str(p).lstrip("#") for p in declared}, key=int)
        return found[0] if found else None
    blob = " ".join(str(item.get(k, "")) for k in ("title", "review"))
    found = sorted(set(re.findall(r"\bPR #(\d{2,5})\b", blob)), key=int)
    return found[0] if found else None


def pr_body_path(item):
    """The drafted PR body for this branch, if one was written."""
    branch = str(item.get("branch") or "")
    slug = branch.replace("/", "-")
    for candidate in (slug, slug.replace("bf-", "bf-")):
        path = os.path.join(PR_BODIES, candidate + ".md")
        if os.path.isfile(path):
            return os.path.relpath(path, manifest.REPO_ROOT)
    return None


def slugify(item):
    """Packet filename: the id, plus the branch when there is one.

    Two items in this manifest carry `branch: ''` on purpose - P0-C-REMEDIATE
    is operator-facing text rather than code, and BFQ-47 needs a decision on
    intent before any branch exists. Appending an empty slug produced
    `bfq-47-.md`, a filename whose trailing hyphen reads like a truncation.
    """
    branch = re.sub(r"[^a-z0-9]+", "-",
                    str(item.get("branch") or "").lower()).strip("-")
    return "%s-%s" % (item["id"].lower(), branch) if branch else item["id"].lower()


def render(item, doc):
    pr = pr_number(item)
    gates = item.get("gates") or []
    runnable = [g for g in gates if g.get("run")]
    nogate = [g for g in gates if g.get("no-gate")]
    meta = doc["meta"]

    out = [BANNER]
    heading = "Review packet — %s" % item["id"]
    if pr:
        heading += " (PR #%s)" % pr
    out.append("# %s\n" % heading)
    out.append("**%s**\n" % flow(item["title"]))

    out.append("| | |")
    out.append("|---|---|")
    out.append("| repository | `%s` |" % item.get("repo", "?"))
    out.append("| branch | `%s` |" % item.get("branch", "?"))
    out.append("| base | `%s` |" % item.get("base", "?"))
    out.append("| claimed state | `%s` — a claim; `make queue-status ID=%s` is the measurement |"
               % (item["state"], item["id"]))
    out.append("| semver | `%s` |" % item.get("semver", "?"))
    if item.get("register"):
        out.append("| register entries | %s |"
                   % ", ".join("`%s`" % r for r in item["register"]))
    if item.get("ships_to_operators_today") is True:
        out.append("| operator exposure | **reaches an operator on today's release** |")
    out.append("")

    out.append("## What this changes\n")
    out.append(flow(item.get("blast_radius")) or "_Not stated in the manifest._")
    out.append("")

    if item.get("semver_reason"):
        out.append("## Why that semver\n")
        out.append(flow(item["semver_reason"]))
        out.append("")

    if item.get("operator_visible"):
        out.append("## What an operator would notice\n")
        out.append("> " + flow(item["operator_visible"], 74).replace("\n", "\n> "))
        out.append("")

    out.append("## Who should review this, and why\n")
    out.append(flow(item.get("review")) or "_Not stated._")
    out.append("")

    out.append("## What was measured\n")
    if runnable:
        for gate in runnable:
            out.append("**`%s`** &nbsp;·&nbsp; kind: `%s`%s\n"
                       % (gate["run"].strip().split("\n")[0][:110],
                          gate.get("kind", "static"),
                          "" if not gate.get("cwd") else
                          " &nbsp;·&nbsp; cwd: `%s`" % gate["cwd"]))
            out.append(flow(gate.get("describe")))
            out.append("")
    else:
        out.append("**Nothing runnable.** Every gate on this item is an explicit "
                   "`no-gate:` marker. Read the next section as the whole "
                   "evidence picture, not as a caveat on it.")
        out.append("")

    out.append("## What these gates do NOT prove\n")
    if nogate:
        out.append("*Each of these is the author recording, at the time, a property "
                   "they could not measure. This is the reviewer's worklist.*\n")
        for gate in nogate:
            out.append("- " + flow(gate["no-gate"], 74).replace("\n", "\n  "))
        out.append("")
    else:
        out.append("*No `no-gate:` markers on this item — every declared property "
                   "has a runnable measurement. That is rare in this manifest and "
                   "worth confirming rather than assuming.*")
        out.append("")

    if item.get("blocks_on"):
        out.append("## Blocked on\n")
        out.append(", ".join("`%s`" % b for b in item["blocks_on"]))
        out.append("")

    out.append("## Evidence\n")
    body = pr_body_path(item)
    if body:
        out.append("- Drafted PR body: [`%s`](../../%s)" % (body, body))
    for ev in item.get("evidence") or []:
        out.append("- [`%s`](../../%s)" % (ev, ev))
    if not body and not item.get("evidence"):
        out.append("_None cited in the manifest._")
    out.append("")

    if item.get("notes"):
        out.append("## Notes carried on the item\n")
        out.append(flow(item["notes"]))
        out.append("")

    out.append("---\n")
    out.append("## Before you approve\n")
    out.append("- [ ] Re-read **what these gates do NOT prove**. A gate can pass "
              "for the wrong reason; two in this project did, and both were green.")
    out.append("- [ ] If the diff changes what an existing test expects, confirm "
              "the reason is stated **in the diff**, where a reviewer sees it.")
    out.append("- [ ] `make queue-status ID=%s` — do the gates still agree with "
              "the claimed state?" % item["id"])
    out.append("- [ ] **Do not merge, push or tag.** Publication is a separate, "
              "deliberate human act; pushing `dev` or `master` builds and "
              "publishes a Docker image.")
    out.append("")
    out.append("*Generated from `queue/work-queue.yaml`, `measured_at` %s, against "
               "cgm-remote-monitor-official `%s`.*"
               % (meta.get("measured_at", "?"),
                  meta.get("measured_against", {}).get(
                      "cgm-remote-monitor-official", "?")))

    return "\n".join(out) + "\n"


def index(items, doc):
    out = [BANNER, "# Reviewer packets\n"]
    out.append(flow(
        "One bounded packet per item whose next move is a human review or "
        "decision. Each says what changed, what was measured, and - the "
        "section worth opening first - what the measurement does not cover. "
        "Start at docs/00-overview/REVIEWER-ONBOARDING.md if this is your "
        "first time in this repository."))
    out.append("")
    out.append("| packet | PR | claimed state | what it is |")
    out.append("|---|---|---|---|")
    for item in items:
        pr = pr_number(item)
        out.append("| [`%s`](%s.md) | %s | `%s` | %s |"
                   % (item["id"], slugify(item),
                      "#%s" % pr if pr else "&mdash;",
                      item["state"], flow(item["title"], 400)))
    out.append("")
    out.append("*Generated by `tools/queue/emit_packets.py` (`make packets`) from "
               "`queue/work-queue.yaml`, `measured_at` %s.*"
               % doc["meta"].get("measured_at", "?"))
    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    doc = manifest.load()
    items = sorted((i for i in doc["items"] if i["state"] in PACKET_STATES),
                   key=lambda i: (pr_number(i) or "zzz", i["id"]))

    if not items:
        sys.stderr.write("emit_packets: VACUOUS — no item is in a state that "
                         "wants a reviewer. That is not a pass.\n")
        return 1

    wanted = {slugify(i) + ".md": render(i, doc) for i in items}
    wanted["README.md"] = index(items, doc)

    if not args.check:
        os.makedirs(OUT_DIR, exist_ok=True)

    stale, written = [], []
    for name, text in sorted(wanted.items()):
        path = os.path.join(OUT_DIR, name)
        current = None
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as handle:
                current = handle.read()
        if current == text:
            continue
        if args.check:
            stale.append(name)
        else:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
            written.append(name)

    # A packet left behind for an item that no longer wants a reviewer is a
    # reviewer pointed at finished work.
    orphans = []
    if os.path.isdir(OUT_DIR):
        orphans = sorted(f for f in os.listdir(OUT_DIR)
                         if f.endswith(".md") and f not in wanted)

    if args.check:
        if stale or orphans:
            sys.stderr.write("emit_packets: STALE, run `make packets`:\n")
            for name in stale:
                sys.stderr.write("  changed:  %s\n" % name)
            for name in orphans:
                sys.stderr.write("  orphaned: %s (its item no longer wants a "
                                 "reviewer)\n" % name)
            return 1
        print("OK     %d reviewer packet(s) are current" % len(wanted))
        return 0

    for name in orphans:
        os.remove(os.path.join(OUT_DIR, name))

    print("emit_packets  %d packet(s); wrote %d, removed %d orphan(s)"
          % (len(wanted), len(written), len(orphans)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
