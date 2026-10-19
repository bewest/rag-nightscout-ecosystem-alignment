# structure-diagrams — the overview's control-structure drawings

*Contributor-facing.* Sources and renderer for the drawings on
[Control structures of the ecosystem and the proposals](../../docs/00-overview/perspective/STRUCTURES.md).

- `inputs/*.yaml`: one drawing each. Nodes have a `level` (0 = top) and a `column`, a `kind`
  (`authority`, `entity`, `org`, `commons`, `human`, `process`), and optionally `status: proposed`,
  a `group` and a `zoom` label naming the drawing that opens the box up. Edges have a `kind`
  (`control`, `feedback`, `funding`, `data`) and optionally `status: proposed`. `views` lists
  stakeholder views: the same drawing with everything not touching `focus` greyed.
- Optional `icon` on a node: a file name in `icons/` without `.svg`, drawn at the box's left to say
  what the box does (factory, landmark, scale, user, users, key-round, smartphone, syringe, …).
  `icons/` holds only the Lucide icons in use, copied from `lucide-static` 0.460.0 with its ISC
  `LICENSE`; to add one, copy its SVG from that package and add a line to `ICON_KEY` in
  `render.py`, which also writes `icon-key.svg`.
- Scenarios: `scenarios: [believed, actual, emerging]`, `base: false` and one view per scenario
  draw the same structure several times on one layout. An edge or node with `in: [...]` appears
  only in those scenarios; `labels: {scenario: text}` changes an edge's label there, and on a node changes who or what sits
  in that box (see `inputs/idea-sponsor-or-operate.yaml`). Edge kinds
  `authority` (where a right to act comes from) and `discretion` (control exercised at the
  controller's own choice) exist for these drawings. See `inputs/1-authority.yaml`.
- Optional layout keys: `bands` (horizontal bands behind rows, e.g. legal / organisational /
  technical), and per edge `route` (`straight`, `z`, `l`, `corridor`), `via` and `label_side`. Use
  them to move a line that crosses the middle of a drawing; see the docstring of `render.py`.
- `render.py` writes `docs/00-overview/perspective/diagrams/<name>.svg`, one `<name>--<view>.svg`
  per view, and `legend.svg`. It needs only Python and PyYAML. It places every box on a
  (column, level) grid and routes lines at right angles; chosen by
  [the grid layout lab](../lab/stpa-grid-style/README.md), which keeps the Graphviz renderer it
  replaced as `baseline_dot.py`.

- `access_charts.py` draws two charts that are not control structures, `1-access-ladder.svg` and
  `1-access-matrix.svg`, from `access/devices.yaml` (one record per device line, mechanism level
  only). It reuses `render.py`'s font and text measure.

- `history_timeline.py` draws `history-timeline.svg` into `docs/00-overview/observations/diagrams/`
  from `history/timeline.yaml`: one row per dated row of the
  [chronology](../../docs/00-overview/observations/HISTORY.md), each naming its section, date cell and
  words. `test_history_timeline.py` fails naming any row that no longer matches HISTORY.md, and
  checks the committed figure; `make history-timeline` draws it and `make diagrams-svg-check` runs
  the test.

```sh
python3 tools/structure-diagrams/render.py            # every input
python3 tools/structure-diagrams/access_charts.py     # the access ladder and matrix
python3 tools/structure-diagrams/render.py tools/structure-diagrams/inputs/z2-agreement.yaml
```

The SVGs are committed so the drawings show on GitHub and on the site without a build step. Each
sits on its own light card, so it reads the same in either colour scheme. Keep each drawing to
one idea and roughly 6–10 boxes; put detail in a drawing one zoom level down.
