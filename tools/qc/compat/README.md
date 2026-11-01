# Write compatibility between two cgm-remote-monitor trees

*Contributor-facing.*

These tools compare what the write-contract matrix (`tools/qc/write-contract-matrix.js`) measures
on a release tree and on a later tree, explain every cell that differs, and turn the result into the
datasets of the living site page
[16.0.0 write compatibility](../../../site/pages/cgm-remote-monitor-16.0.0-write-compatibility.html).
Every record the matrix writes is synthetic test data in a throwaway database.

## Where things are

| What | Where |
| --- | --- |
| Matrix pins of the three trees (run 1) | `tools/qc/results/write-contract-matrix/v15.0.9-c6a0d8ed.json`, `dev-37b2280f.json`, `pr8879-6960bfb7.json` |
| Comparison inputs and outputs | `tools/qc/results/write-contract-matrix/compat-16.0.0/`: `analysis.json` (trees, bisect chain, prediction files, set-aside cells), `client-shapes.json` (client catalogue, read from code with file and line), `slice-batch-attribution.json`, `predictions/`; outputs `diff-cells.json`, `summary.json`, `clients.json` |
| Page sources | `releases/cgm-remote-monitor-16.0.0/compat/`: the seven page datasets (`headline`, `groups`, `heat`, `families`, `triage`, `clients`, `cells`), `groups.yaml` (group names, meanings, verdicts, decision basis, undo), `page.yaml` (the page's words and measurement description), `reconsider.json` (the decision cards) |
| Renderer | `tools/site/render_compat.py`, drawing code `tools/site/compat-dash.js` |

The bisect pins (one matrix run per commit of the chain in `analysis.json`, about 1.4 MB each) and the
second run of each tree are not committed; step 2 regenerates them.

## Measurement of 2026-10-31

`v15.0.9` `c6a0d8ed`, `dev` `37b2280f` and #8879 `6960bfb7`; default settings; Node 22.23.4;
MongoDB 7.0.43 (15.0.9's MongoDB driver 5.9.2 predates 8.0); two runs per tree, 0 cells differing
between a tree's runs. 4,916 cells per tree, 2,947 differ from 15.0.9, 0 unexplained, one defect
(BF-225, 3 cells). The harness was `tools/qc/write-contract-matrix.js` at `df2a96c12`, which ran the
batch cells by default, with `v15.0.9-harness-guard.diff` applied (v15.0.9 has no
`lib/server/storage-reads`; the guard lets the run continue and the six `ws idread-fail` cells are set
aside as not comparable, listed in `analysis.json`).

## Fresh comparison of v15.0.9 and merged 16.0.0 dev

The 2026-11-01 refresh is separate from the historical comparison above:
`tools/qc/results/write-contract-matrix/compat-16.0.0-refresh-2026-11-01/analysis.json`.
It repeats both endpoint trees (`v15.0.9` `c6a0d8ed` and merged `dev` `497d08c9`) on Node 22.23.4
and MongoDB 7.0.43, including batch forms. The existing `dev` `37b2280f` matrix pin is a historical
attribution anchor, not a third fresh or repeated endpoint. The comparison labels that boundary
explicitly and does not attribute changes within the post-`37b2280f` interval to individual PRs.
Six `ws idread-fail` cells remain set aside because the injected read failure did not exist on the
15.0.9 tree. The merged-dev endpoint sets `WRITE_IDENTIFIER_INDEX=off` because some identity-field
fixtures intentionally seed duplicate identifiers, which the unique index correctly rejects;
index behavior is separate. The completed `--batch --no-idf` matrix has 3,443 cells per off/try
lane on MongoDB 5.0.32 and 8.0.34: each version shows the same 33 expected batch differences, with
other observed differences cache-only.

The two fresh runs of each endpoint contain 4,916 cells each; repeat comparisons differ only in
cache/wire (81 baseline and 19 merged-dev cells). The fresh baseline runs match outside cache/wire.
The classified comparison has 2,803 changed cells, zero unexplained and zero `Defect`-verdict
cells. The final change split is 347 only by the pre-identity dev anchor, 2,107 only after it, and
349 across both intervals; 1,886 cells concern identifier format. The 2026-10-31 retained baseline
pin differs from the fresh baseline by 23 batch cells outside cache/wire, so it is not used as a
repeat. The release colophon visualizes the endpoint runs, origin split, behavior groups, client
shape matches and current release gates.

The retained 2026-10-31 pin also has 114 cache/wire-only differences from the fresh baseline; it is
not used as a repeat or as an endpoint in this comparison.

The refreshed page labels are in `releases/cgm-remote-monitor-16.0.0/compat/page.yaml`; the builder
uses `origin_labels` from the analysis file so an attribution interval is not mislabeled as PR
`#8879`. Endpoint pins and intermediate output are retained under the refresh directory; generated
page datasets remain under `releases/cgm-remote-monitor-16.0.0/compat/`.

## Refresh steps

Run from the repository root. `R=tools/qc/results/write-contract-matrix/compat-16.0.0-refresh-2026-11-01` and
`P=releases/cgm-remote-monitor-16.0.0/compat` below.

1. **Prepare the endpoints.** Check out cgm-remote-monitor worktrees at `c6a0d8ed` and
   `497d08c9`, each with `npm ci` complete. Reuse the retained MongoDB 7.0.43 container for one
   run at a time. For v15.0.9, copy the current harness to the worktree and apply the compatibility
   guard because that tree predates `lib/server/storage-reads`:
   `cp tools/qc/write-contract-matrix.js "$H" && patch "$H" tools/qc/compat/v15.0.9-harness-guard.diff`.
   The guard applies to the current harness with an offset. The historical 37b2280f attribution
   pin is an input to the comparison; it is not rerun.

2. **Run each endpoint twice.** Use the guarded harness for v15.0.9 and the current harness for
   merged dev; both runs include `--batch`, use Node 22.23.4 and MongoDB 7.0.43, and run sequentially
   against the shared database. Leave other settings unset on v15.0.9; set
   `WRITE_IDENTIFIER_INDEX=off` only on merged dev to permit the deliberate duplicate-state fixtures.
   For each run, execute
   `env WC_WORKTREE="$W" WC_MONGO=mongodb://127.0.0.1:27970 n exec 22.23.4 node "$H" --batch --out "$OUT"`
   (with `WRITE_IDENTIFIER_INDEX=off` added to the merged-dev environment). Save first pins under
   `R/run1/` and repeats under `R/run2/`; the config's `trees.<key>.run1` paths point to the first
   pins. A quick check of one pair:
   `python3 tools/qc/compat/wcdiff.py A.json B.json --list`.

3. **Diff and classify.**
   ```
   python3 tools/qc/compat/build.py --config $R/analysis.json --groups $P/groups.yaml \
       --bisect tools/qc/results/write-contract-matrix \
       --run2 v1509=$R/run2/v1509-c6a0d8ed.json \
       --run2 8879=$R/run2/dev-497d08c9.json --all
   ```
   This writes `diff-cells.json`, `clients.json` and `summary.json` into `$R`. Check that
   `summary.json`'s top-level `unexplained` list is empty and `totals.flaky_outside_cache_wire` is 0
   for both fresh endpoints; the historical attribution anchor is not repeated. An unexplained cell
   needs a cause before the page is refreshed. A cell in a group with no `name` in `groups.yaml`
   stops step 4: add the group's text and verdict there.

4. **Build the page datasets.**
   `python3 tools/qc/compat/build_page.py --data $R --groups $P/groups.yaml --out $P`

   A re-classification (a verdict, a decision basis, a group's wording or undo) needs only
   `groups.yaml` edited and steps 3 (for `guard`) and 4 re-run; no matrix run. The page's words and
   measurement description are in `page.yaml`, the decision cards in `reconsider.json`.

5. **Commit, then render.** Commit the changed files of `$R`, `$P` and the pins. Then
   `tools/site/.venv/bin/python tools/site/render_compat.py`, set the page's `source_commit` in
   `site/pages/pages.yaml` to the commit the script prints (the last commit that touched a source),
   run `make site`, and commit the page and `pages.yaml` together. The site build fails, naming this
   page, while any source has changed after `source_commit`.
