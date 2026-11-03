---
name: release-record
description: Record a merge, a maintainer decision, a test run or a cohort check in the release directory (releases/<product>-<version>/) and keep the backfix register's status words and the queue's states consistent with it. Use whenever a PR merges to dev, a decision is taken, a V&V run completes, or a session hands off programme state. The release records are the state of record for a cycle; overview pages and progress.md are not.
---

# Release record: what merged, what was decided, what was checked

`releases/README.md` gives the convention and `releases/VERIFICATION-RECORDS.md` the verification
record format. This skill is the procedure for keeping a cycle's records current while work lands.

## Which file takes what

| event | file | form |
|---|---|---|
| a PR merged to `dev`, a branch opened or re-based, a session handoff | `contents.md` | a dated **Update** table appended under "What is merged so far" or the relevant section: PR, head SHA, what it carries, register ids, what was measured, what is left |
| a decision by the maintainer | `decisions.md` | one row: decision as it stands, date, who decided, link to the evidence |
| a test run, soak, replay or cohort check | the integration record `docs/30-design/remedial/rc-<version>-integration-record.md` | the next `R<n>` entry: tree, command, totals, what it does not cover |
| a defect's status moved | the backfix register, the entry's status cell | `open` → `fixed <date>` (branch, commit) → `merged <date>` (PR) → `released <tag>` |
| an item's state moved | `queue/work-queue.yaml` | see the `queue-item` skill; switch the gate to `official/dev` ancestry when it merges |
| a new queue id named in the records | `verification-selection.txt` | one id per line, same commit |

## Procedure

1. **Anchor first.** Read the current tree from the remote, not from a brief:
   ```bash
   git -C externals/cgm-remote-monitor-official fetch official
   git -C externals/cgm-remote-monitor-official log -1 --format='%h %s' official/dev
   gh pr view <n> --repo nightscout/cgm-remote-monitor --json state,mergeCommit,headRefOid
   ```
2. **Write the contents.md row** with the figures you ran (`reproduced`) or read (`read-derived`),
   labelled. Totals name the suite and the tree (`npm test` 6035/0/3 on `dev` `f54941b5`, MongoDB
   5.0). A count that moves is given with the command that reproduces it.
3. **Move the status words** in the register and the queue in the same commit, and nowhere else.
   Merged to `dev` is `merged`, never `released`; `released` appears only when a tag exists that
   operators install.
4. **Add a release-notes line** in `release-notes.md` for every operator-visible change: what they
   will notice, when, and what to do. Plain language; every safety caveat kept; no individual dosing
   advice. A change with no operator-visible effect is said to have none.
5. **Keep the three files agreeing**: the count of operator-visible changes in `tag-message.txt`
   and `release-notes.md`, the version number everywhere including the directory name, and no
   caveat softened between `contents.md` and the notes.
6. **Run the checks** after `git add`:
   ```bash
   make queue-check          # coverage, generated views, links
   make docs-links
   ```
   If the next-gen plan changed: `tools/site/render_nextgen.py`, then move `source_commit` in
   `site/pages/pages.yaml` to the plan commit, and commit both.
7. **Commit by path**, no trailers; quote the hash from the `git commit` output in any message that
   names it.

## What the record never does

- It never describes a defect that is live on the shipping release by recipe; mechanism only.
- It never narrates how a belief changed ("was X, now Y"). Correct the fact in place; git holds the
  history.
- It never carries a name, email, glucose value or identifier from user data.
- It never calls a step verified that nobody ran. A skipped gate is written as skipped.

## Capturing the verification record

Once, at the tag, over the ids in `verification-selection.txt`:

```bash
python3 tools/queue/verification-record.py --release cgm-remote-monitor-<version> \
  --captured-at "$(date +%Y-%m-%dT%H:%M:%S%:z)" \
  $(grep -v '^#' releases/cgm-remote-monitor-<version>/verification-selection.txt | sed 's/^/--id /') \
  --out-dir releases/cgm-remote-monitor-<version>
```

The `.md` is generated from the `.json`; never hand-edit it. `--check --from-json` reports DRIFT if
anyone did.
