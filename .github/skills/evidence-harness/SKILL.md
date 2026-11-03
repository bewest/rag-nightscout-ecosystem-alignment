---
name: evidence-harness
description: Verify a cgm-remote-monitor change or a cross-ecosystem compatibility claim by measurement rather than by reading: boot the shipping module by path in a lab under tools/lab or tools/qc, run the write-contract matrix and classify the differing cells, prove every check with a break-it control, and record the run as a dated, labelled record. Use before calling any fix verified, any claim reproduced, or any client compatible.
---

# Evidence harness: measure, control, record

The programme's evidence has one shape. A harness `require()`s the shipping module **by path from
a worktree** so the thing measured is the thing that ships; it runs against a throwaway database
with synthetic data; it asserts liveness before and after each measured step; and every check is
shown to fail on a known-bad state before its green is believed.

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

Run each tree **twice**; a cell that differs between a tree's own runs is noise, not a finding.
Predict the differing cells before the run and write the prediction down; a result that matches a
prediction is evidence, a result that surprises is a finding to stop and report. Pins live in
`tools/qc/results/write-contract-matrix/`; the settings and database version of every run are part
of the record.

## Build or extend a lab

1. Copy the shape of a neighbouring `tools/lab/<topic>/`: a README that states the question, the
   command, the expected output and the control; a runner that boots from `WC_WORKTREE` or an
   explicit worktree path; results under `results/` with the tree SHA in the file name.
2. Seed synthetic data only. Database names contain `test`. Drop the database at the end.
3. **Controls are authored, never derived.** For each assertion, write the state in which it must
   fail and run it there. Record both results. A revert that does not reproduce the original
   symptom proves nothing about the check.
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
