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

## Refresh steps

Run from the repository root. `R=tools/qc/results/write-contract-matrix/compat-16.0.0` and
`P=releases/cgm-remote-monitor-16.0.0/compat` below.

1. **Prepare the trees.** One cgm-remote-monitor worktree per tree and per bisect commit, named
   `<prefix><commit>`, each with `npm ci` done. One MongoDB container per lane, named
   `compat-m7-<port>`, for example
   `docker run -d --name compat-m7-27970 -p 127.0.0.1:27970:27017 mongo:7.0.43`.
   Copy the harness and, if any tree predates `lib/server/storage-reads`, apply the guard:
   `cp tools/qc/write-contract-matrix.js "$H" && patch "$H" tools/qc/compat/v15.0.9-harness-guard.diff`.
   The guard applies to the current harness with an offset. Since `7b24de535` the batch
   cells are opt-in: pass `MATRIX_ARGS=--batch` to include them, as the 2026-10-31 run did.

2. **Run the matrix.** For each tree, twice, and once for each bisect commit of `analysis.json`'s
   `chain`:
   `MATRIX_ARGS=--batch tools/qc/compat/lane.sh <port> <outdir> <prefix> "$H" <commit>...`
   (several lanes in parallel, one container each). Copy each tree's first run to
   `tools/qc/results/write-contract-matrix/<tree>-<commit>.json` and point `trees.<key>.run1` in
   `analysis.json` at it. Update `chain` with the merge steps between the trees, and `predictions`
   with any per-slice prediction files (each written before its slice's code).
   A quick check of one pair: `python3 tools/qc/compat/wcdiff.py A.json B.json --list`.

3. **Diff and classify.**
   ```
   python3 tools/qc/compat/build.py --config $R/analysis.json --groups $P/groups.yaml \
       --bisect <outdir> --run2 v1509=<run2.json> --run2 dev=<run2.json> --run2 8879=<run2.json> --all
   ```
   This writes `diff-cells.json`, `clients.json` and `summary.json` into `$R`. Check that
   `summary.json`'s `totals.unexplained` is 0 and every tree's `flaky_outside_cache_wire` is 0; an
   unexplained cell needs a cause before the page is refreshed. A cell in a group with no `name` in
   `groups.yaml` stops step 4: add the group's text and verdict there.

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
