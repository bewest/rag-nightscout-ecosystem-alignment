"""emit_views.py — fill the GENERATED BLOCKS inside the hand-written views.

    python3 tools/queue/emit_views.py            # rewrite the blocks in place
    python3 tools/queue/emit_views.py --check    # exit 1 if any block is stale
    python3 tools/queue/emit_views.py --stdout   # print every block, write nothing

HOW THIS DIFFERS FROM emit.py, AND WHY BOTH EXIST

``emit.py`` owns a whole file: ``queue/QUEUE.md`` is generated end to end and
carries a banner saying so, because it is a *view of the manifest* and nothing
else. The documents this file serves are not that. They are arguments — what
the programme is for, which of three horizons a reader should care about, what
a new reviewer should read first — and an argument cannot be generated from a
YAML manifest.

So these are HYBRID: prose a human writes, wrapped around blocks a program
owns. The maintainer chose this shape on 2026-09-16 over a fully generated
view (which cannot carry an argument) and over a fully hand-written one (which
becomes another document that reads true after it stops being true — the exact
failure the docs-truth parcel exists to repair).

THE CONTRACT

A generated block is delimited in the Markdown by:

    <!-- BEGIN GENERATED: <block-name> -->
    ...anything here is owned by this program and will be destroyed...
    <!-- END GENERATED: <block-name> -->

Everything outside those markers is a human's, and this program never touches
it. Everything inside is this program's, and a human's edit there is destroyed
by the next run — which is what ``--check`` in CI makes discoverable rather
than surprising.

WHAT THE BLOCKS MAY AND MAY NOT SAY

Every number here is read from ``queue/work-queue.yaml``, where ``state`` is a
CLAIM about what the gates will say, not a measurement. That distinction is the
manifest's founding rule and these views inherit it: a block prints the claim
and names ``make queue-status`` as the measurement. A block must never print a
state as though a gate had just confirmed it.
"""

from __future__ import annotations

import argparse
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import manifest  # noqa: E402

VIEWS_DIR = os.path.join(manifest.REPO_ROOT, "docs", "00-overview")

BLOCK_RE = re.compile(
    r"(<!-- BEGIN GENERATED: (?P<name>[a-z0-9-]+) -->\n)"
    r"(?P<body>.*?)"
    r"(<!-- END GENERATED: (?P=name) -->)",
    re.S,
)

# The three horizons the maintainer works in, and the parcels that serve each.
# `docs-truth` sits under remedial because a document that contradicts itself
# is a defect in the same sense the register means: something that will mislead
# whoever reads it next.
HORIZONS = [
    ("Remedial", "find and fix defects that already ship",
     ["phase0", "register-open", "docs-truth"]),
    ("Modernization", "bring dependencies and code up to date",
     ["release-train"]),
    ("Multitenant", "operate at bulk scale, affordably",
     ["tenancy"]),
]

# How `review:` prose maps to the kind of person an item is waiting for. The
# order matters: the first pattern that matches wins, so the specific
# escalations are checked before the catch-all.
REVIEWER_KINDS = [
    ("SECURITY reviewer", r"^\s*security\b"),
    ("SAFETY reviewer", r"^\s*safety\b"),
    ("Upstream reviewers", r"upstream reviewer"),
    ("Maintainer + a second human", r"plus (a|one) (human )?reviewer|and at least one human|AND the security"),
    ("Whoever edits it next", r"whoever edits it next"),
    ("Maintainer", r"maintainer"),
]

# A state is a claim. These are the claims that mean "no further engineering is
# what this is waiting for" — a person has to act.
HUMAN_BLOCKED_STATES = {
    "ready-to-push": "every runnable gate passes; the next step is a human push",
    "needs-decision": "waiting on a decision, not on work",
    "in-flight-upstream": "handed to upstream; not ours to land",
    "unsettled": "not yet established that this is a defect at all",
}


def reviewer_kind(item):
    text = " ".join(str(item.get("review") or "").split())
    for label, pattern in REVIEWER_KINDS:
        if re.search(pattern, text, re.I):
            return label
    return "Unassigned"


def pr_numbers(item):
    """The PR number this item IS, not every PR number it mentions.

    Two wrong answers were measured before this one. A bare four-digit pattern
    dropped nightscout-connect's `PR #68` entirely, because that repository's
    numbering is two digits while cgm-remote-monitor's is four — P0-F rendered
    an em-dash while its own title said `PR #68`. Widening to two digits then
    made it WORSE: P0-F's `notes` legitimately discuss #26, #64, #65, #66 and
    #67 as related pull requests, and sorting strings put `#26` first, so the
    view confidently named the wrong PR.

    So the qualifier is what is matched, not the number, and only `title` and
    `review` are searched. `notes` is where an item discusses OTHER people's
    pull requests, and reading those as its own is how a table ends up
    pointing a reviewer at somebody else's work.

    A THIRD WRONG ANSWER, measured 2026-09-18. `review` is not safe either.
    P0-K has no PR at all, and its `review` field says a reviewer must also
    rule on "the $type collision with PR #8737" -- another item's pull request,
    named in the one place this function trusted. The view rendered P0-K as
    `#8737`, pointing a reviewer at somebody else's work, which is the exact
    failure the paragraph above says it had fixed.

    So the inference is now a FALLBACK. An item may declare `pr:` -- a list, or
    a scalar, or an empty list meaning "this item is not a PR" -- and that wins.
    Guessing from prose is what is left when nothing was declared.
    """
    if "pr" in item:
        declared = item["pr"]
        if declared is None:
            declared = []
        if not isinstance(declared, (list, tuple)):
            declared = [declared]
        return sorted({str(p).lstrip("#") for p in declared}, key=int)
    blob = " ".join(str(item.get(k, "")) for k in ("title", "review"))
    return sorted(set(re.findall(r"\bPR #(\d{2,5})\b", blob)), key=int)


def _flow(text, width=100):
    return " ".join(str(text or "").split())[:width]


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------

def block_horizons(doc):
    items = doc["items"]
    by_parcel = collections.defaultdict(list)
    for item in items:
        by_parcel[item["parcel"]].append(item)

    out = ["| horizon | parcels | items | claimed `not-started` | claimed waiting on a person |",
           "|---|---|---:|---:|---:|"]
    for name, _purpose, parcels in HORIZONS:
        got = [i for p in parcels for i in by_parcel.get(p, [])]
        waiting = [i for i in got if i["state"] in HUMAN_BLOCKED_STATES]
        fresh = [i for i in got if i["state"] == "not-started"]
        out.append("| **%s** | %s | %d | %d | %d |"
                   % (name, ", ".join("`%s`" % p for p in parcels),
                      len(got), len(fresh), len(waiting)))
    total_waiting = len([i for i in items if i["state"] in HUMAN_BLOCKED_STATES])
    out.append("| | **total** | **%d** | **%d** | **%d** |"
               % (len(items),
                  len([i for i in items if i["state"] == "not-started"]),
                  total_waiting))
    return "\n".join(out)


def block_state_matrix(doc):
    items = doc["items"]
    states = [s for s in doc["meta"]["states"]]
    present = [s for s in states
               if any(i["state"] == s for i in items)]
    out = ["| parcel | " + " | ".join("`%s`" % s for s in present) + " | total |",
           "|---" * (len(present) + 2) + "|"]
    for parcel in doc["parcels"]:
        row = [i for i in items if i["parcel"] == parcel]
        cells = [str(len([i for i in row if i["state"] == s]) or "") for s in present]
        out.append("| `%s` | %s | **%d** |" % (parcel, " | ".join(cells), len(row)))
    return "\n".join(out)


def block_needs_a_human(doc):
    items = doc["items"]
    waiting = [i for i in items if i["state"] in HUMAN_BLOCKED_STATES]
    by_kind = collections.defaultdict(list)
    for item in waiting:
        by_kind[reviewer_kind(item)].append(item)

    out = []
    for kind in sorted(by_kind, key=lambda k: -len(by_kind[k])):
        group = sorted(by_kind[kind], key=lambda i: (i["state"], i["id"]))
        out.append("### %s &mdash; %d item%s\n"
                   % (kind, len(group), "" if len(group) == 1 else "s"))
        out.append("| id | claimed state | what it is | PR |")
        out.append("|---|---|---|---|")
        for item in group:
            prs = pr_numbers(item)
            out.append("| `%s` | `%s` | %s | %s |"
                       % (item["id"], item["state"], _flow(item["title"], 80),
                          ", ".join("#" + p for p in prs) or "&mdash;"))
        out.append("")
    return "\n".join(out).rstrip()


def block_reviewer_load(doc):
    items = doc["items"]
    counts = collections.Counter(reviewer_kind(i) for i in items)
    total = sum(counts.values())
    out = ["| the item is waiting for | items | share |", "|---|---:|---:|"]
    for kind, n in counts.most_common():
        out.append("| %s | %d | %d%% |" % (kind, n, round(100.0 * n / total)))
    out.append("| **total** | **%d** | |" % total)
    return "\n".join(out)


def block_operator_exposure(doc):
    rows = [i for i in doc["items"] if i.get("ships_to_operators_today") is True]
    out = ["| id | claimed state | defect |", "|---|---|---|"]
    for item in sorted(rows, key=lambda i: i["id"]):
        out.append("| `%s` | `%s` | %s |"
                   % (item["id"], item["state"], _flow(item["title"], 90)))
    return "\n".join(out)


def block_open_prs(doc):
    rows = []
    for item in doc["items"]:
        prs = pr_numbers(item)
        if prs and item["state"] == "in-flight-upstream":
            rows.append((prs[0], item))
    out = ["| PR | id | branch | what it fixes | who should review |",
           "|---|---|---|---|---|"]
    for pr, item in sorted(rows, key=lambda r: (r[0], r[1]["id"])):
        out.append("| **#%s** | `%s` | `%s` | %s | %s |"
                   % (pr, item["id"], item.get("branch", "&mdash;"),
                      _flow(item["title"], 60), reviewer_kind(item)))
    return "\n".join(out)


def block_provenance(doc):
    meta = doc["meta"]
    against = meta.get("measured_against", {})
    return (
        "*Generated from `queue/work-queue.yaml` by `tools/queue/emit_views.py`. "
        "Manifest `measured_at` **%s**, against cgm-remote-monitor-official "
        "`%s` and this repository at `%s`. Every state above is a **claim** "
        "about what the gates will say &mdash; `make queue-status` is the "
        "measurement.*"
        % (meta.get("measured_at", "?"),
           against.get("cgm-remote-monitor-official", "?"),
           against.get("main_repo_head", "?")))


BLOCKS = {
    "horizons": block_horizons,
    "state-matrix": block_state_matrix,
    "needs-a-human": block_needs_a_human,
    "reviewer-load": block_reviewer_load,
    "operator-exposure": block_operator_exposure,
    "open-prs": block_open_prs,
    "provenance": block_provenance,
}


# ---------------------------------------------------------------------------

def views():
    if not os.path.isdir(VIEWS_DIR):
        return []
    return sorted(os.path.join(VIEWS_DIR, f) for f in os.listdir(VIEWS_DIR)
                  if f.endswith(".md"))


def render(doc, path):
    with open(path, "r", encoding="utf-8") as handle:
        src = handle.read()
    unknown = []

    def fill(match):
        name = match.group("name")
        if name not in BLOCKS:
            unknown.append(name)
            return match.group(0)
        return "%s\n%s\n\n%s" % (match.group(1), BLOCKS[name](doc),
                                 match.group(4))

    out = BLOCK_RE.sub(fill, src)
    return out, src, unknown


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if any block on disk is stale")
    parser.add_argument("--stdout", action="store_true",
                        help="print every block and write nothing")
    args = parser.parse_args()

    doc = manifest.load()

    if args.stdout:
        for name in sorted(BLOCKS):
            print("<!-- BEGIN GENERATED: %s -->" % name)
            print(BLOCKS[name](doc))
            print("<!-- END GENERATED: %s -->\n" % name)
        return 0

    targets = views()
    if not targets:
        sys.stderr.write("emit_views: no views found under %s\n" % VIEWS_DIR)
        return 1

    stale, written, blocks_seen, problems = [], [], 0, []
    for path in targets:
        out, src, unknown = render(doc, path)
        blocks_seen += len(BLOCK_RE.findall(src))
        for name in unknown:
            problems.append("%s: unknown block %r"
                            % (os.path.relpath(path, manifest.REPO_ROOT), name))
        if out == src:
            continue
        if args.check:
            stale.append(os.path.relpath(path, manifest.REPO_ROOT))
        else:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(out)
            written.append(os.path.relpath(path, manifest.REPO_ROOT))

    if problems:
        for line in problems:
            sys.stderr.write("emit_views: %s\n" % line)
        return 1

    # A run that filled nothing has measured nothing. Say so rather than
    # printing OK — the same trap `report()` guards against in the gates.
    if blocks_seen == 0:
        sys.stderr.write("emit_views: VACUOUS — %d view(s) carry no generated "
                         "blocks at all\n" % len(targets))
        return 1

    if args.check:
        if stale:
            sys.stderr.write("emit_views: STALE, run `make views`:\n")
            for path in stale:
                sys.stderr.write("  %s\n" % path)
            return 1
        print("OK     %d generated block(s) across %d view(s) are current"
              % (blocks_seen, len(targets)))
        return 0

    print("emit_views  %d block(s) across %d view(s); rewrote %d"
          % (blocks_seen, len(targets), len(written)))
    for path in written:
        print("  %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
