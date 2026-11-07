---
name: evidence-harness
description: >-
  Measure a cgm-remote-monitor change or a defined cross-ecosystem compatibility claim using shipping-module labs, comparative matrices and meaningful failure controls. Use before claiming a fix reproduced or a client compatible; scale verification to capability and batch boundaries.
---

# Evidence harness: measure, control, record

The programme's evidence has one shape. A harness `require()`s the shipping module **by path from
a worktree** so the thing measured is the thing that ships; it runs against a throwaway database
with synthetic data; it asserts liveness before and after each measured step; and each claimed
property has a meaningful known-bad control before its green is believed. One independent control may
exercise several assertions when it exposes the same failure mechanism.

## Choose the verification boundary

Finish a complete capability or adopted milestone criterion within its lane.
Use focused/affected checks during implementation. For cgm-remote-monitor, the
integration coordinator owns full/browser/enabled-corpus acceptance on the coherent frozen candidate;
resumption, a helper commit or another control does not trigger that campaign.
Retain exact-head attribution and required semantic/clinical safeguards.

An early native proof is useful when its result could change the architecture or
establish a critical boundary. State its question and exit condition, then join
its result into the capability. After an unexpected failure, preserve the symptom
and diagnose narrowly. Setup-only failures need preflight repair before another
campaign, with the invalid capture retained. Record one capability/batch evidence
bundle and link it from the evolving handoff; individual control logs stay in
that bundle rather than each becoming a new programme acceptance record.

## Pick the instrument

| question | instrument | where |
|---|---|---|
| does a write path store, stamp, delete and announce a record the same way after a change | write-contract matrix | `tools/qc/write-contract-matrix.js` (header comment is the manual) |
| which cells changed between two trees and why | compat classification | `tools/qc/compat/` (README gives the lane) |
| does a specific defect reproduce, and does the fix remove it | a lab | `tools/lab/<topic>/` (each has a README with its command and its controls) |
| does a client still read and write correctly against a tree | consumer survey, replay lab | `reports/consumer-impact-<version>/`, `tools/lab/rc-soak` |
| does a gate measure what it claims | vacuity controls | `make queue-vacuity`, `queue/gate-controls.yaml` |
| what does the matrix of MongoDB versions say | `tools/lab/mongo-server-matrix` | floor and ceiling only (Node and MongoDB edges) |

## Run the matrix

```bash
# a fresh MongoDB on its own port; never a real site
docker run -d --name wc-mongo-$$ -p 27151:27017 mongo:7.0
WC_WORKTREE=externals/work/<crm worktree> WC_MONGO=mongodb://127.0.0.1:27151 \
  node tools/qc/write-contract-matrix.js --out /tmp/<scratch>/after.json
node tools/qc/write-contract-matrix.js --compare tools/qc/results/write-contract-matrix/<pin>.json /tmp/<scratch>/after.json
```

For a new differential matrix capture, run each compared tree **twice**; a cell
that differs between a tree's own runs is noise, not a finding. This repeatability
check belongs to the comparative experiment, not every helper validation or
full-suite campaign; justified reuse of an accepted capture retains its source scope.
Predict the differing cells before the run and write the prediction down; a result that matches a
prediction is evidence, a result that surprises is a finding to stop and report. Pins live in
`tools/qc/results/write-contract-matrix/`; the settings and database version of every run are part
of the record.

## Build or extend a lab

1. Copy the shape of a neighbouring `tools/lab/<topic>/`: a README that states the question, the
   command, the expected output and the control; a runner that boots from `WC_WORKTREE` or an
   explicit worktree path; results under `results/` with the tree SHA in the file name.
2. Seed synthetic data only. Database names contain `test`. Drop the database at the end.
3. **Controls are authored, never derived.** For each claimed property, define and run a meaningful
   failing state. A control family may cover several assertions sharing a failure mechanism.
   Restore each break; run the unmodified focused capability suite after the control family.
   Record positive, semantic failure and restoration results. A revert that does not reproduce
   the original symptom proves nothing about the check.
4. Stop and report when the code does not match the brief. Do not substitute the nearest thing that
   works; most real defects in this programme surfaced exactly at that point.

## Record the run

- A dated file under `docs/60-research/<horizon>/<topic>-<YYYY-MM-DD>.md` or the next `R<n>` entry
  of the integration record: tree SHAs, Node and MongoDB versions, settings, command, totals, the
  controls and what they showed, and **what the run does not cover**.
- Label every figure `reproduced` (you ran it) or `read-derived` (you inferred it from source).
- Link the record from the queue item's `evidence:` list and from the release record row.
- A defect found this way gets a register entry by mechanism; if it is live on the shipping release,
  no request or payload that would work against a deployed site goes in the public tree.

## Traps that cost a run

- Headless client tests load `node_modules/.cache`'s bundle: rebuild per worktree with
  `npm run postinstall`; never borrow another checkout's `node_modules`.
- The matrix's identifier-format cells seed shared identifiers straight to MongoDB and crash with
  the unique index on; compare index-on and index-off runs with the **same** flags.
- A test tier can miss shared-database interference. Run the full `npm test` before "ready".
- The local `mongod` on 27017 is an old version; use a container and read `db.version()` before
  labelling a run.
- `ENOSPC` from a watcher is usually the inotify limit, not disk.
