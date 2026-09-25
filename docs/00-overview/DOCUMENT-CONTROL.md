# Document control — proposal

*Contributor- and maintainer-facing. **DRAFT PROPOSAL, requiring review by the maintainer and by
a quality-management professional before it is adopted or relied on.** Written 2026-09-25 against
this repository at `eb564053`. It is not legal or regulatory advice. It does not claim that the
Nightscout Foundation, or any software it stewards, conforms to any standard.*

This proposes how the alignment repository controls its documents and records. It is the first
procedure of a quality management system (QMS) for the Nightscout ecosystem alignment work. It
writes down the practice piloted on 2026-09-25, when 19 superseded files were retired into 5 living
ones, and names what is still missing before the practice can be called controlled.

**Context that bounds it.** The Nightscout Foundation is a 501(c)(3) that stewards open-source
automated insulin delivery software. It does not manufacture medical devices or prescribe therapy,
and people build and run these tools themselves. The procedure borrows the document-control
practices that medical-device quality systems use, because readers of this repository make
decisions that can affect people managing diabetes. Borrowing a practice is not a claim of
conformity.

## 1. Scope

**In scope:** the programme material from August and September 2026 and everything written after
it:

- `docs/00-overview`;
- `docs/30-design/{remedial,modernization,tenancy,platform}` and the loose design documents of that
  period;
- `docs/60-research/{remedial,modernization,tenancy,programme}`;
- `docs/40-migration`;
- `queue/`, `releases/` and `reports/`.

**Out of scope until the maintainer extends it:** the January–April 2026 AID research campaign,
including the 53 `VERIFICATION-*` files at the repository root and the loose files in
`docs/60-research`, and the July 2026 telemetry design documents. They stay where they are
(maintainer decision, 2026-09-16).

## 2. Two kinds of controlled information

The procedure turns on one distinction, the same one ISO 13485:2016 draws between documents
(§4.2.4) and records (§4.2.5), and ISO 9001:2015 between maintained and retained documented
information (§7.5).

| | a **document** | a **record** |
|---|---|---|
| says | what is true, decided or intended **now** | what was measured or done **at a point in time** |
| changes | corrected in place whenever the world moves | never, once captured |
| file name | stable, **no date** (`ROADMAP.md`, `rc-15.0.9-integration-record.md`) | dated (`manual-lab-15.0.9-rc-2026-09-23.md`) |
| examples | overview pages, the backfix register, the queue, the execution plan, the versioning policy, a release's contents and decisions, a defect record such as BF-103 | a lab run, a soak, a measurement report, a posted PR body, a triage record |

**A series is one document.** When the same deliverable is produced again and again (successive
test runs of one release candidate, revisions of one plan), it lives in one undated file. The
current version is given in full, and each earlier version is one row in a history table that
links to the file at the commit that holds it. This rule is already in the
[definition of done](DEFINITION-OF-DONE.md#living-documents-and-snapshots).

## 3. Controls

### 3.1 Identification

Every controlled file opens with a status block under its title. The block states:

- **the audience**: contributor-facing, or user-facing;
- **the status**: living, or a snapshot with its date; *draft requiring professional review*
  where that applies;
- **what it was measured against**, as dates and commits (for example `origin/dev` `4f705217`);
- **where the current fact lives**, if it lives somewhere else (the queue, the register, a
  decision record).

Queue items (`RT-0`, `BFQ-47`) and register entries (`BF-103`) are the stable identifiers that
documents cite. **Proposed, not yet done:** a document register (§5) that gives every controlled
document an identifier, an owner and a class.

### 3.2 Revision control

- **Git is the revision history.** A revision is a commit. Documents carry no change logs, no "was
  X, now Y" passages and no retraction notes; they are corrected in place.
- **Pushing is a human act.** Agents prepare commits locally and stop. The maintainer pushes, so
  nothing becomes public without a person choosing it.
- **The approved version is the version on `main` in the public repository.** Until pushed, a
  commit is a proposal.

### 3.3 Review and approval

| class | approved by | review standard |
|---|---|---|
| decision records (execution plan, versioning policy, a release's `decisions.md`) | the maintainer, who owns every decision in them | each decision is the maintainer's words or is confirmed by them |
| living status documents (overview pages, queue, register, release contents) | the maintainer, by pushing | the [definition of done](DEFINITION-OF-DONE.md), ten criteria |
| records | nobody after capture; they are reviewed for accuracy when captured | reproducible, with the command or harness named, and a control where the claim is about access or severity |
| user-facing text (release notes, operator guidance) | the maintainer, plus a reader who is not a developer | plain language, every safety caveat kept, no individual dosing advice, not medical advice, points to the care team |
| security- or safety-relevant content | the maintainer and a named SECURITY or SAFETY reviewer | disclosure rule (§3.8) |

**Gap:** the SECURITY and SAFETY reviewer rows name a kind of reviewer, and for most items no
individual is assigned ([PROGRAMME-STATUS](PROGRAMME-STATUS.md#the-two-constraints-neither-of-them-engineering)).
Until they are, approval of that content rests on one person.

### 3.4 The current version is the one a reader finds

- **Entry points.** The READMEs link to [PROGRAMME-STATUS](PROGRAMME-STATUS.md),
  [ROADMAP](ROADMAP.md), [NEEDS-A-HUMAN](NEEDS-A-HUMAN.md) and
  [REVIEWER-ONBOARDING](REVIEWER-ONBOARDING.md). Each of them points to the one home of each kind
  of fact.
- **One home per fact.** Defect facts live in the register, item state in the queue, decisions in
  the decision records. Other documents link to them and do not restate them.
- **Generated blocks for anything that moves.** Counts, states and orders are generated from
  `queue/work-queue.yaml` inside hand-written pages, and `make views-check` fails when they drift.
  An example is ROADMAP §1's table of what the next release still waits on.

### 3.5 Changing a document

A change is a commit that leaves every gate in §3.9 green. A change that **supersedes** files
follows the procedure piloted on 2026-09-25:

1. **Classify** each file in the cluster as document or record, and read all of them in full.
2. **Check scope before merging.** Files with similar names are not necessarily one series. The
   adoption roadmap and the 2026-09-09 next-steps discussion were distinct proposals and stayed.
3. **Write the one current document.** Give the current version in full. Carry forward, with the
   tree each ran on, any evidence the current version did not repeat. **Re-check each
   carried-forward claim against the current code before carrying it**; one claim in the pilot was
   already out of date and was dropped.
4. **Move design content that has no other home** to the document that owns that topic (for
   example, tenancy designs to the execution plan) instead of deleting it.
5. **Add a history row** for each superseded version, linking to it at a pushed commit.
6. **Rewrite every inbound link**, including queue evidence paths, generated views, reviewer
   packets and copies of posted PR bodies.
7. **Remove the superseded files** from the working tree.
8. **Run the gates** and show that the link gate goes red on a restored dead link.
9. **Coordinate** with every session editing the same files (§3.10).

### 3.6 Obsolete documents

- A superseded document is **removed from the working tree**, not kept beside the current one with a
  "superseded" banner.
- It stays **retrievable**: through the history row of its successor, by `git show <commit>:<path>`,
  or at a GitHub URL pinned to a pushed commit.
- **Snapshots that quote a removed file** (a dated research note citing a line of an old readiness
  document) keep the citation, repointed to the pinned URL, so the quotation stays checkable.
- **Proposed:** a pushed annotated tag at each consolidation (`archive/<date>`), so retrieval does
  not depend on remembering a hash. No such tag exists yet.

### 3.7 Records

- **A record is not edited after capture**, except to correct a known-wrong claim in place with a
  one-line note (the definition of done's snapshot rule).
- **A superseded record** (an earlier test run of the same candidate) leaves the reader's path. The
  living document that supersedes it carries its history row, and anything it alone measured.
- **Retention:** git retains every record. **Proposed:** records that are evidence for a release
  (the integration record, verification records, lab results) are kept retrievable for at least as
  long as that release is supported. A pushed tag per release would pin them.
- **Health data.** Records contain synthetic data only, unless a data holder has agreed otherwise
  in writing. They contain no names, emails or identifiers from real data, and no credentials.

### 3.8 External and restricted documents

- **Copies of external text** (PR bodies as posted, advisory drafts) are records of what was sent,
  or drafts marked unsent. They follow the live text; they do not replace it.
- **Disclosure rule.** The repository is public. A defect that is live on the shipping release is
  described by mechanism only: no request, payload or pattern that would work against a deployed
  instance. Security advisory detail is withheld until a release with the fix ships and the
  advisory is published. The withheld text stays in history at a named commit, and the index of
  what is withheld is the [advisory response pack](../30-design/remedial/advisory-response-2026-09/README.md).
- **Private material**, such as BF-72's disposition, is held outside version control.

### 3.9 Automated controls

| gate | what it enforces |
|---|---|
| `make docs-links` | every path cited in the groomed material and the queue tooling resolves; the exemptions are named and each carries a reason |
| `make views-check` | every generated block on the overview pages is current |
| `make packets-check` | every reviewer packet is current, and none is orphaned |
| `make queue-validate`, `queue-coverage` | the queue's schema, and that every open register entry has a queue item |
| `make queue-vacuity` | every runnable gate has a negative control that fails, or a recorded reason why it cannot |
| `make queue-check` | all of the above, for CI |

**A check is evidence only after it has been seen to fail.** Every new gate or generated block
introduced during the consolidation was broken on purpose once, to show it goes red.

### 3.10 Concurrent authors

Several sessions (people and agents) edit the same tree and share one git index.

- **Commit by path** (`git commit -- <paths>`), never the whole index.
- **Announce** a multi-file edit to the other sessions before starting, and name the files.
  **Re-read** a shared file before editing it.
- **A change containing another author's hunks** is committed only when that author agrees, and
  the commit message names them.
- **A file another session is rewriting** is left out of a commit, and the one-line change it needs
  is handed to that session.

## 4. The 2026-09-25 pilot

| commit | retired | now |
|---|---:|---|
| `a35e7e25` | 8 run records `rc-15.0.9-*-2026-09-2x.md` | [15.0.9 integration record](../30-design/remedial/rc-15.0.9-integration-record.md) |
| `8135442f` | the post-Phase-0 roadmap | [ROADMAP](ROADMAP.md), generated from the queue; its designs moved into the execution plan |
| `bb26a50c` | 2 BF-103 records, 2 connector profile-sync records, 2 advisory stubs | [BF-103 record](../60-research/remedial/bf103-split-drag-time.md); [connector profile sync](../60-research/remedial/connector-profile-sync.md); the advisory pack README |
| `c8945592` | the backfix-2 plan and its first integration run | [15.0.9 decisions](../../releases/cgm-remote-monitor-15.0.9/decisions.md); versioning policy §5.7 (compatibility flags) |
| `238c3da2` | 2 release-readiness snapshots | ROADMAP §1 (what 15.0.9 still waits on, generated) and the release's `contents.md`; versioning policy §8.3 (why the release order) |

**19 files retired, 5 living files created**, plus new sections in the versioning policy and the
execution plan. `make queue-check` was green after each commit. The pilot also found and fixed three
queue items whose recorded blockers or state had fallen behind (`RT-0`, `RT-5`, `BFQ-47`), because
the new generated tables made the mismatch visible.

## 5. Gaps before this can be called controlled

| gap | proposal | owner |
|---|---|---|
| no document register | one generated table listing each controlled document: identifier, class, owner, status, path | maintainer to approve the shape |
| no named owner per document | owner = the person who approves changes to it; the maintainer by default | maintainer |
| approval is implicit in pushing | record approval of decision records and user-facing text in the commit or PR that carries it | maintainer |
| no independent SECURITY or SAFETY reviewer | recruit one of each ([REVIEWER-ONBOARDING](REVIEWER-ONBOARDING.md)) | maintainer |
| 75 dated files remain in the programme directories, many of them snapshots whose facts now live elsewhere | classify each as record (keep) or superseded document (consolidate), cluster by cluster | agents, maintainer review |
| no pushed archive or release tags | tag each consolidation and each release in this repository | maintainer |
| the April campaign and July telemetry material | out of scope by decision; revisit if outside readers are pointed at it | maintainer |
| no periodic review | a review of the living documents at each release, checking every fact against the tree it names | maintainer |
| training | this document and the definition of done are the material; no training record is kept | — |

## 6. For the reviewer to verify

- **Applicability.** Whether the Foundation's role (steward of user-built open-source software, not
  a manufacturer) makes any QMS obligation apply, or whether this is voluntary good practice only.
  This draft assumes the latter.
- **Standards mapping.** Whether §2 and §3 map correctly onto ISO 13485:2016 §4.2.4 and §4.2.5 and
  ISO 9001:2015 §7.5. Also, if manufacturers building on this software will cite these documents,
  whether the FDA's Quality Management System Regulation (21 CFR Part 820, which incorporates
  ISO 13485 by reference and applies from 2026-02-02) or IEC 62304's configuration-management
  expectations change anything. These references were written from general knowledge and have not
  been checked against the standards' text.
- **Git as the revision system.** Whether commit history on a public host is adequate retention for
  records, or whether releases need exported, signed snapshots.
- **Approval evidence.** Whether a maintainer's push is sufficient evidence of approval, or whether
  explicit sign-off (a PR review, a signed tag) is needed.
- **Agent authorship.** Whether content drafted by AI agents under the maintainer's direction needs
  its own identification or review step beyond §3.3.
- **Retention period** for release evidence (§3.7).
