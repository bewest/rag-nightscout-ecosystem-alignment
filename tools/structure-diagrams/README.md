# structure-diagrams — the overview's control-structure drawings

*Contributor-facing.* Sources and renderer for the drawings on
[Control structures, drawn](../../docs/00-overview/perspective/STRUCTURES.md).

- `inputs/*.yaml`: one drawing each. Nodes have a `level` (0 = top) and a `column`, a `kind`
  (`authority`, `entity`, `org`, `commons`, `human`, `process`), and optionally `status: proposed`,
  a `group` and a `zoom` label naming the drawing that opens the box up. Edges have a `kind`
  (`control`, `feedback`, `funding`, `data`) and optionally `status: proposed`. `views` lists
  stakeholder views: the same drawing with everything not touching `focus` greyed.
- Optional layout keys: `bands` (horizontal bands behind rows, e.g. legal / organisational /
  technical), and per edge `route` (`straight`, `z`, `l`, `corridor`), `via` and `label_side`. Use
  them to move a line that crosses the middle of a drawing; see the docstring of `render.py`.
- `render.py` writes `docs/00-overview/perspective/diagrams/<name>.svg`, one `<name>--<view>.svg`
  per view, and `legend.svg`. It needs only Python and PyYAML. It places every box on a
  (column, level) grid and routes lines at right angles; chosen by
  [the grid layout lab](../lab/stpa-grid-style/README.md), which keeps the Graphviz renderer it
  replaced as `baseline_dot.py`.

```sh
python3 tools/structure-diagrams/render.py            # every input
python3 tools/structure-diagrams/render.py tools/structure-diagrams/inputs/z2-agreement.yaml
```

The SVGs are committed so the drawings show on GitHub and on the site without a build step. Each
sits on its own light card, so it reads the same in either colour scheme. Keep each drawing to
one idea and roughly 6–10 boxes; put detail in a drawing one zoom level down.
