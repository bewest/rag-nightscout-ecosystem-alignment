# structure-diagrams — the overview's control-structure drawings

*Contributor-facing.* Sources and renderer for the drawings on
[Control structures, drawn](../../docs/00-overview/perspective/STRUCTURES.md).

- `inputs/*.yaml`: one drawing each. Nodes have a `level` (0 = top) and a `column`, a `kind`
  (`authority`, `entity`, `org`, `commons`, `human`, `process`), and optionally `status: proposed`,
  a `group` and a `zoom` label naming the drawing that opens the box up. Edges have a `kind`
  (`control`, `feedback`, `funding`, `data`) and optionally `status: proposed`. `views` lists
  stakeholder views: the same drawing with everything not touching `focus` greyed.
- `render.py` writes `docs/00-overview/perspective/diagrams/<name>.svg`, one `<name>--<view>.svg`
  per view, and `legend.svg`. It needs Graphviz (`sudo apt install graphviz`) and PyYAML.

```sh
python3 tools/structure-diagrams/render.py            # every input
python3 tools/structure-diagrams/render.py tools/structure-diagrams/inputs/z2-agreement.yaml
```

The SVGs are committed so the drawings show on GitHub and on the site without a build step. Each
sits on its own light card, so it reads the same in either colour scheme. Avoid edges between
nodes on the same level: Graphviz routes them without the level constraint and their labels
collide.
