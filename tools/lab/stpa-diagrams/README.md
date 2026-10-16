# stpa-diagrams — which tools can draw STPA control structures

*Contributor-facing.* A feasibility lab: the same three generic structures drawn by every candidate
tool and measured, so the choice of diagram tool for the STPA, hub-and-spoke and governance views
rests on measured layouts rather than on reading each tool's documentation.

## What it does

- `inputs/*.yaml`: three tool-neutral structures, all generic:
  - `aid-loop`: an AID control loop (person, controller app, pump, CGM, the body, disturbances).
  - `hub-spoke`: a Nightscout hub with uploaders, followers and remote commands down a push path.
  - `governance`: a two-column (development / operations) sociotechnical control structure, from
    open-source projects through a shared commons and companies to regulators and governments.

  Each input gives every node a `level` (0 = top) and a `column` (left-to-right lane), and every
  edge a kind (`control`, `feedback`, `data`, `disturbance`). Its `mutation` is one extra feedback
  edge, used to measure how far the layout moves when the diagram changes.
- `gen.py` emits, per input, one source per variant, using the layout hints each tool offers:

  | variant | tool | hints used |
  |---|---|---|
  | `dot-spline`, `dot-ortho` | Graphviz `dot` | `rank=same` per level, invisible edges for column order, `dir=back` for upward edges, compass ports to put control left and feedback right |
  | `d2-dagre`, `d2-elk` | D2 | declaration order, containers for groups (no rank or port hints exist) |
  | `d2-grid` | D2 grid layout | one cell per (level, column); containers dropped |
  | `mermaid-dagre`, `mermaid-elk` | Mermaid flowchart | declaration order, subgraphs for groups |
  | `plantuml` | PlantUML (on Graphviz) | `-down->`/`-up->` arrows, hidden `right` links for column order, packages for groups |
  | `control-grid` | none (positive control) | every node at its exact (column, level); loop pairs offset left/right |
  | `control-random` | none (negative control) | seeded random positions, straight edges, one forced node overlap |
- `lab.sh` renders every variant for the base and mutated inputs. Mermaid is rendered by
  `mermaid-render.js` inside Chrome, as the docs site renders it, with the ELK layout registered.
- `measure.js` loads each SVG in Chrome, reads node boxes and sampled edge paths in screen
  coordinates, and scores them against the model (`report.py` builds `results/metrics.md`; the
  column meanings are at its top). A variant whose nodes or edges cannot all be identified is
  reported as not scored rather than scored on partial geometry.
- `sheet.js` writes the contact sheets in `results/sheets/`.

```sh
PYTHON=/path/to/python-with-pyyaml ./lab.sh     # render + measure, prints results/metrics.md
NODE_PATH=.tools/node/node_modules node sheet.js results/build "$(command -v google-chrome)" results/sheets
```

### Installing the tools

Everything except Graphviz and Chrome installs into `.tools/` (gitignored); nothing is global.

```sh
cd tools/lab/stpa-diagrams
sudo apt install graphviz default-jre                       # dot (2.43 used here); Java for PlantUML
GOBIN=$PWD/.tools/bin go install oss.terrastruct.com/d2@v0.7.1
mkdir -p .tools/node && (cd .tools/node && npm init -y >/dev/null && \
  npm i @mermaid-js/layout-elk@0.2.3 mermaid@11.17.2 playwright-core@1.56.1)
mkdir -p .tools/plantuml && curl -fsSL -o .tools/plantuml/plantuml.jar \
  https://github.com/plantuml/plantuml/releases/download/v1.2025.2/plantuml-1.2025.2.jar
# sha256 of that jar as downloaded 2026-10-16: 862c7d6d0d3bde3c819eac4dfc03cf549046bf1d49c04d18a779eb2d834b77c9
```

`lab.sh` uses `google-chrome` from `PATH`; set `CHROME=` to use another build (see the Chrome 131
finding below before choosing an older one). draw.io was not run: its export needs the desktop app
or a container (`docker run --rm -v $PWD:/data rlespinasse/drawio-export`), and it has no layout
from text, so it would only measure whoever placed the boxes by hand.

## Results, 2026-10-16

Tools: Graphviz 2.43.0, D2 0.7.1, Mermaid 11.17.2 with `@mermaid-js/layout-elk` 0.2.3, PlantUML
1.2025.2 (OpenJDK 21), measured in Google Chrome 154. Full tables in `results/metrics.md`; contact
sheets of the base renders in `results/sheets/*-base.png`.

**Controls.** `control-grid` scores 0 hierarchy violations, 0 lane violations and every loop pair
control-left and distinct on all three diagrams. `control-random` scores 5/13, 10/34 and 9/25
hierarchy violations, 0 loop pairs control-left, and at least one label collision on each diagram.
The crossing count is not a discriminating measure on its own: the random layout has few
crossings on `hub-spoke` because its straight edges lie on top of each other (counted under
"overlap" instead).

**Hierarchy kept** (node pairs out of level order, base render):

| variant | aid-loop | hub-spoke | governance |
|---|---|---|---|
| `dot-spline` | 0/13 | 0/25 | 0/34 |
| `dot-ortho` | 0/13 | 0/25 | 0/34 |
| `plantuml` | 0/13 | 0/25 | 7/34 |
| `d2-grid` | 0/13 | 0/25 | 0/34 |
| `d2-dagre` | 3/13 | 8/25 | 7/34 |
| `mermaid-dagre` | 3/13 | 8/25 | 7/34 |
| `d2-elk` | 10/13 | 14/25 | 11/34 |
| `mermaid-elk` | 10/13 | 18/25 | 12/34 |

**STPA loop convention** (loop pairs with control left of feedback):

| variant | aid-loop | hub-spoke | governance |
|---|---|---|---|
| `dot-spline`, `dot-ortho` | 2/2 | 1/1 | 8/8 |
| `mermaid-dagre` | 2/2 | 1/1 | 6/8 |
| `d2-elk`, `mermaid-elk` | 2/2 | 1/1 or 0/1 | 5/8 |
| `plantuml` | 1/2 | 1/1 | 2/8 |
| `d2-dagre` | 2/2 | 1/1 | 2/8 |
| `d2-grid` | 0/2 | 0/1 | 1/8 |

**Findings**

1. Graphviz is the only tool that held the hierarchy, the lanes and the loop convention on all
   three structures. Its levers are `rank=same`, compass ports and `dir=back`; none of the other
   tools exposes all three. On governance `dot-spline` also kept the development and operations
   columns side by side with the commons between them, which no other auto-layout did.
2. ELK, in both D2 and Mermaid, inverts STPA structures: it treats feedback edges as layering
   constraints, so on `aid-loop` the disturbance node is drawn at the top and the pump at the bottom.
   It also moves furthest when one edge is added (mean displacement 0.67 of the drawing for
   `d2-elk` on `aid-loop`, against 0.05–0.09 for Graphviz and PlantUML). Graphviz is not immune:
   `dot-spline` moved 0.31 on `hub-spoke`, where the added edge joins two levels.
3. D2 and Mermaid with dagre are adequate for hub-and-spoke pictures, not for control structures:
   with only declaration order to steer them they put the CGM sensor below the body on `aid-loop`,
   and D2 dagre stacks the governance containers vertically instead of as columns.
4. D2's grid holds positions exactly but routes edges centre to centre, so every control/feedback
   pair is drawn on one line (0/2, 0/1 and 0/8 loop pairs distinct; 4, 3 and 12 overlapping edge
   pairs) and labels collide (3, 3 and 8 text overlaps). It cannot hold containers in a grid.
5. PlantUML keeps the hierarchy on the two small diagrams, but on governance it swaps the two
   columns, floats the commons up beside the regulators, and is the least stable (mean
   displacement 0.41, one node moving the full width of the drawing).
6. `dot-ortho` is the most compact and has 0 crossings on all three, but its edge labels sit on
   other edges' lines (visible on `aid-loop` and `governance`); the label measure here only counts
   text overlapping text, so this shows on the contact sheet, not in the table.
7. Mermaid 11.17.2 places no edge labels in Chrome 131: every label gets
   `transform="translate(undefined, NaN)"` and a zero-width box, including for a two-node
   `A -->|hello| B` chart. Chrome 154 places them. `mmdc` 11.4.2, with its own bundled Mermaid, fails the same
   way on its default Chrome 131. Readers on an old browser would see Mermaid diagrams on the site without
   edge labels. Not diagnosed further.
8. Site integration: Material for MkDocs loads `mermaid@11` (floating) from unpkg and does not
   register the ELK layout, so `layout: elk` would not render on the site without extra JavaScript.
   Mermaid is the only option that follows the site's light/dark theme. The Graphviz, D2 and
   PlantUML SVGs carry fixed black text and strokes (D2 and PlantUML also a white background), and
   none of them contains a `prefers-color-scheme` rule; included as images they would need a
   dark-mode treatment (a styled wrapper, or rendering a dark variant).

**What this does not measure:** label text over edge lines (finding 6), how readable a reader
finds a drawing, and hand-placed tools (draw.io). The inputs are one size each; larger structures
may change the ranking.
