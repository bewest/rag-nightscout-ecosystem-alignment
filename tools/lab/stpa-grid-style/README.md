# stpa-grid-style — drawing control structures in Leveson's style

*Contributor-facing.* A styling lab, dated 2026-10-17. The published control-structure drawings
(`tools/structure-diagrams/render.py`, Graphviz `dot` with splines) were judged "lots of elbows
crossing each other, and hard to follow". This lab asks which way of drawing the same YAML inputs
gets closest to the classic STPA control-structure figures, and measures the answer. It changes
the visual form only: every candidate draws the same nodes, edges and labels from the same inputs.
Nothing here replaces `render.py` or the published SVGs; the integrating session decides that.

## The conventions being aimed at

These are the visual conventions of the control-structure figures in Nancy Leveson's
*Engineering a Safer World* (2011) and the *STPA Handbook* (Leveson and Thomas, 2018), described
from memory in our own words. No figure is reproduced.

Confident (they define the notation and recur across the published figures):

1. **Vertical axis means authority.** Controllers sit above what they control. Control actions
   are drawn going down, feedback going up. Position on the page carries meaning.
2. **One loop, two lines.** A controller and its controlled process are joined by a pair of
   arrows: control action down on the left, feedback up on the right, as two separate parallel
   lines rather than one double-headed line.
3. **Straight, orthogonal lines.** Lines are vertical or horizontal, with right-angle corners
   where a corner is needed. Curves are not used.
4. **Labels beside the line, not on it.** The text naming a control action or feedback sits next
   to its arrow (control text on the outer left side, feedback text on the outer right side of a
   pair) and does not cut through any line.
5. **Plain rectangles, plain text.** Boxes are simple rectangles with short names. Colour carries
   no meaning in the originals (the colours in this repo's drawings are a local addition).
6. **The two-column sociotechnical form.** The generic safety control structure has system
   development on the left and system operations on the right, each a column of levels from
   legislatures down through regulators, company management and project or operations
   management, to the operating process at the bottom, with a few links between the columns.

Inferred (consistent with the figures as remembered, but not a stated rule we can cite):

7. **Grid alignment.** Boxes on one level share a baseline, and boxes in one column share a
   centre line, so most connections are single straight verticals.
8. **Horizontal bands between levels.** The sociotechnical figures read as layers (government,
   regulators, companies, operations, physical process), which suggests horizontal boundaries
   for legal, organisational and technical regions. The originals separate levels by placement;
   whether they draw explicit bands or rules is not something we can confirm from memory. Here
   bands are an optional extra (`bands:` below), off unless an input asks for them.
9. **Few bends, and crossings avoided or made deliberate.** Long links between distant boxes run
   round the outside rather than through the middle; where a crossing is unavoidable it is a
   plain right-angle crossing, not an oblique tangle.

The measurements below are chosen to test exactly these: bends, the axis-aligned share of line
length, crossings, label text over lines, loop pairs drawn straight and parallel, and grid
alignment of node centres.

## What it does

- Inputs: every `tools/structure-diagrams/inputs/*.yaml` (nine drawings) and the three generic
  `tools/lab/stpa-diagrams/inputs/*.yaml` (`aid-loop`, `hub-spoke`, `governance`), unchanged.
- `gridstpa.py`: the new deterministic grid renderer (candidate `grid`). Python, PyYAML only,
  writes SVG directly. How it works, in order:
  1. Each node sits in the cell (column, level); columns are as wide and rows as tall as their
     largest box, so centres align exactly.
  2. Each pair of connected nodes picks the route with the lowest cost that passes through no
     other box: straight down; an L (out of a box side, into the top of the other); a Z (down,
     across in the gap between two rows, down); or a "corridor" round a column gap. Cost is
     10 per bend, 6 per side entry, 15 per crossing with routes already placed, plus length.
     Every edge between the same two nodes shares the route shape, so a control/feedback pair
     is drawn as two parallel lines.
  3. Ports on each box side and tracks in each gap are ordered, then adjacent swaps are tried
     while they remove crossings or overlaps. Downward (control) ports sit left of upward
     (feedback) ports between the same two boxes. Ports, side ports and gap tracks share one
     16 px spacing, so an L or Z pair keeps a constant separation round its corners.
  4. Labels are placed beside a segment from a candidate set (positions along each segment, two
     distances, either side), scored for overlap with boxes, other labels and any line; control
     labels prefer the left of the line and feedback labels the right. If a label cannot be
     placed cleanly, the gaps near it grow and the layout is redone (at most 12 times, keeping
     the attempt with the fewest bad labels).
  It reads the same YAML schema as `render.py` (nodes with `level`, `column`, `kind`, `status`,
  `group`, `zoom`; edges with `kind`, `status`; `groups`; `views`) and writes `<name>.svg`, one
  `<name>--<view>.svg` per view, and `legend.svg`, each on a white card like the published ones.
  Optional additions, all ignored by `render.py` and absent from the current inputs:

  | key | where | meaning |
  |---|---|---|
  | `bands: [{label, levels: [..]}]` | top level | shaded horizontal bands behind those levels, labelled in a left strip |
  | `route: straight \| z \| l \| corridor` | edge | restrict the route shape |
  | `via: N` | edge, with `route` | `z`: jog in the gap below level N; `corridor`: run in the gap left of column N |
  | `label_side: left \| right \| above \| below` | edge | preferred side for the label |

- `lab.py` renders every candidate for every input into `results/build/<input>/`:

  | variant | what it is |
  |---|---|
  | `dot-spline` | the published renderer's own dot source (`render.py`'s `emit`, ids added), the baseline |
  | `grid` | `gridstpa.py`, default costs |
  | `grid-z` | `gridstpa.py` with a side entry costing 40, so edges enter tops and bottoms and take Z routes |
  | `neato-ortho` | Graphviz `neato -n2`, nodes pinned at the `grid` positions, `splines=ortho`, `xlabel`s (ortho has no edge labels or ports) |
  | `elk` | elkjs `layered`, `INTERACTIVE` cycle breaking, layering, crossing minimisation and node placement seeded with the `grid` positions, orthogonal routing, fixed port positions, ELK's own label placement |
  | `avoid` | libavoid (libavoid-js, the Adaptagrams router behind Inkscape's and Dunnart's connectors): nodes at the `grid` positions, orthogonal routing with nudging and `hateCrossings`, labels by `gridstpa.py`'s placer (libavoid places none) |
  | `control-grid` | positive control: grid positions; same-column and same-level edges straight, every other edge a Z with exactly two bends; pairs offset left/right; labels in a column to the right, clear of all lines |
  | `control-random` | negative control: seeded random positions, random two-waypoint polylines, labels centred on their own lines, one forced node overlap |

  `elk` and `avoid` get neutral ports (bottom of the upper box to top of the lower one, ordered
  by the far end, downward edges first), not `gridstpa.py`'s, so they route on their own. Both
  are drawn with `gridstpa.py`'s styles so only the geometry differs. `route.mjs` runs them.
- `measure.js` loads each SVG in Chrome at its viewBox size, samples every edge path every 2
  units, and scores it against the model (`report.py` writes `results/metrics.md`; the column
  meanings are at its top). It keeps the old lab's metrics and adds:
  - **bends**: total turning per edge in right angles (straight 0, L 1, Z 2; a spline counts its
    curvature), mean and max;
  - **axis share**: the share of all line length within 3° of horizontal or vertical;
  - **label over line**: text runs outside the boxes whose box (shrunk 1 unit) contains a point
    of any edge line, the measure the old lab lacked (its finding 6);
  - **loops straight**: both lines of a control/feedback pair one straight vertical;
  - **loops parallel**: both lines with the same number of bends, at a separation that varies by
    no more than max(8, half its median) along the middle 80 %;
  - **grid alignment**: levels and columns whose node centres spread by more than 2 units;
  - **area per node**.
- `sheet.js` writes contact sheets: `results/sheets/<input>.png` (all eight variants) and
  `results/sheets/<input>-dot-spline-vs-grid.png` (baseline and `grid` side by side, larger).
- `inputs-demo/z0-sector-bands.yaml`: `z0-sector` with `bands:` added, to show the rendering.
  Its band names and level ranges are illustrative, not a content proposal. Output in
  `results/demo/`.
- `results/grid-render/`: `gridstpa.py`'s output for all nine published inputs, with views and
  legend, ready for the integrating session to compare with `docs/00-overview/perspective/diagrams/`.

```sh
cd tools/lab/stpa-grid-style
./lab.sh                      # render, measure, report, contact sheets
python3 gridstpa.py           # the nine published inputs -> results/grid-render/
python3 gridstpa.py -o OUT tools/structure-diagrams/inputs/z0-sector.yaml
```

### Installing

Graphviz, Chrome, Python 3 with PyYAML and Node come from the system; the Node packages go into
`.tools/` (gitignored).

```sh
cd tools/lab/stpa-grid-style
sudo apt install graphviz                     # dot/neato 2.43.0 used here
mkdir -p .tools/node && (cd .tools/node && npm init -y >/dev/null && \
  npm i playwright-core@1.56.1 elkjs@0.10.0 libavoid-js@0.4.5)
```

`gridstpa.py` itself needs only Python and PyYAML. libavoid-js is LGPL-2.1-or-later and is used
here only as a lab comparison, not shipped.

## Results, 2026-10-17

Tools: Python 3.12.3, PyYAML 6.0.3, Graphviz 2.43.0, elkjs 0.10.0, libavoid-js 0.4.5, Node 24.15.0,
playwright-core 1.56.1, measured in Google Chrome 154.0.8037.57. Full tables in
`results/metrics.md`, raw numbers in `results/metrics.json`.

**Controls.** On every one of the 12 inputs `control-random` scores worse than `control-grid` on
bends, axis share, crossings, edges through nodes, label over line, label collisions, loops
straight, loops parallel and grid alignment. The bend metric was also checked against ground
truth: on `control-grid` the measured turning of every edge equals the bend count it was built
with (largest error 0). Two metrics do not discriminate:

- **edge overlaps fails its negative control**: random lines rarely lie on top of each other, so
  `control-random` scores worse on only 2 of 12 inputs, and better on 8 (`control-grid` reuses
  lanes and scores 23 overlaps). It does detect constructed overlaps, but a low count is not
  evidence of a good drawing.
- **loops control-left** is at chance on random geometry, as in the old lab: `control-random`
  ties `control-grid` on 5 of 12 inputs.

**Totals over all 12 inputs** (bends and axis share: mean of the per-input means):

| variant | bends per edge | axis share | crossings | label runs over a line | loops straight | loops parallel | loops control-left | grid misaligned | area per node |
|---|---|---|---|---|---|---|---|---|---|
| `dot-spline` (baseline) | 1.07 | 0.127 | 43 | 17/254 | 0/46 | 18/46 | 46/46 | 26/53 | 48003 |
| **`grid`** | **0.71** | **0.995** | **10** | 11/254 | 17/46 | **46/46** | 46/46 | **0/53** | 54557 |
| `grid-z` | 1.34 | 0.994 | 11 | **1/254** | 17/46 | 42/46 | 37/46 | 0/53 | 57569 |
| `neato-ortho` | 0.67 | 0.995 | 10 | 86/247 | 17/46 | 26/46 | 36/46 | 0/53 | 53144 |
| `elk` | 5.04 | 0.993 | 362 | 2/254 | 0/46 | 9/46 | 26/46 | 26/53 | 88230 |
| `avoid` | 1.77 | 0.991 | 14 | 10/254 | 9/46 | 15/46 | 46/46 | 0/53 | 53786 |
| `control-grid` | 1.16 | 0.994 | 120 | 2/254 | 20/46 | 20/46 | 32/46 | 0/53 | 65785 |
| `control-random` | 2.68 | 0.023 | 1105 | 217/231 | 0/46 | 0/46 | 23/46 | 53/53 | 53794 |

No candidate drew an edge through a node it does not touch. `neato-ortho` drew 3 edge pairs on
top of each other and had 2 text-over-text collisions; `dot-spline` had 4 text-over-text
collisions and 1 overlap; `grid` had none of either. A loop pair can only be one straight
vertical when both boxes share a column, so 17 of 46 is the most any grid placement of these
inputs reaches: `grid` reaches it, `control-grid` scores 20 only by drawing through boxes.

**Baseline against `grid`, per input** (bends per edge; crossings; label runs over a line; loops
parallel; size in viewBox units):

| input | `dot-spline` | `grid` |
|---|---|---|
| `z0-sector` | 1.54; 6; 3; 3/8; 762×709 | 0.95; 4; 2; 8/8; 729×824 |
| `z1-today` | 0.93; 3; 1; 2/3; 599×496 | 0.58; 0; 0; 3/3; 543×538 |
| `z1-proposed` | 1.00; 6; 1; 2/5; 854×750 | 0.81; 0; 0; 5/5; 567×890 |
| `z2-agreement` | 1.32; 5; 2; 2/5; 673×630 | 0.43; 0; 0; 5/5; 578×705 |
| `z2b-loop-as-a-service` | 1.57; 5; 0; 1/6; 785×630 | 0.84; 0; 0; 6/6; 637×735 |
| `z3-device` | 1.07; 1; 0; 1/2; 449×408 | 0.75; 0; 1; 2/2; 565×490 |
| `p-sqlite` | 0.81; 2; 2; 1/1; 582×406 | 0.71; 0; 0; 1/1; 623×526 |
| `p-cncf` | 0.52; 1; 0; 1/2; 638×588 | 0.45; 0; 2; 2/2; 611×714 |
| `p-apple` | 1.27; 4; 3; 1/3; 733×419 | 0.78; 0; 3; 3/3; 650×548 |
| `aid-loop` | 0.82; 4; 1; 0/2; 536×384 | 0.80; 2; 0; 2/2; 754×406 |
| `hub-spoke` | 0.44; 0; 1; 1/1; 582×454 | 0.45; 0; 1; 1/1; 719×541 |
| `governance` | 1.59; 6; 3; 3/8; 762×697 | 0.95; 4; 2; 8/8; 722×824 |

Contact sheets (base renders): `results/sheets/<input>.png` for all candidates (not committed, about 6 MB; `node sheet.js` regenerates them),
`results/sheets/<input>-dot-spline-vs-grid.png` for the two that matter most, e.g.
[z0-sector](results/sheets/z0-sector-dot-spline-vs-grid.png),
[z1-proposed](results/sheets/z1-proposed-dot-spline-vs-grid.png),
[z2b](results/sheets/z2b-loop-as-a-service-dot-spline-vs-grid.png). Bands demo:
`results/demo/z0-sector-bands.svg`.

**Findings**

1. `grid` is the closest to the target form on the measures that fit the complaint. Against the
   baseline it cuts bends per edge from 1.07 to 0.71, crossings from 43 to 10 (zero on 9 of 12
   inputs), raises the axis-aligned share of line length from 0.127 to 0.995, draws every one of
   the 46 control/feedback pairs as parallel lines (baseline 18), and puts every node centre on
   its grid line (baseline: 26 of 53 levels and columns out of line, because `dot` keeps levels
   but not columns). The cost is size: 14 % more area per node on average, mostly height, since
   the gaps between rows hold the labels.
2. Visual judgement (ours, from the contact sheets, not measured): `grid` reads as a Leveson
   figure. Authority runs top to bottom, pairs are two parallel lines with their labels outside
   them, and long links run round the edge. The baseline's curves cross the middle of the
   drawing and some labels sit between unrelated curves (`z0-sector`'s "therapy plans" and "hub
   reports" overprint in the baseline).
3. Where `grid` still falls short: 10 crossings remain, on `z0-sector` and `governance` (4 each)
   and `aid-loop` (2). On `z0-sector` the long "pumps, CGMs" link from companies to the AID system
   cuts across the middle; an explicit `route: corridor, via: 0` on that one edge sends it round
   the left margin clear of the other lines (checked by eye on a scratch copy, not measured; the
   inputs were not changed). 11 label text runs
   still touch a line, on 6 inputs; the placer reports them as the least bad position, and
   growing the gaps did not free them.
4. `grid-z` (side entries made expensive) has the fewest labels over lines (1/254) but nearly
   twice the bends (1.34) and puts control right of feedback on 9 of 46 pairs: forcing tops and
   bottoms makes nested Z pairs that the port order cannot always keep control-left. Whether
   arrows entering a box's side look acceptable is a judgement call; the numbers favour `grid`.
5. `neato-ortho` (Graphviz with the same pinned positions) matches `grid` on bends, axis share
   and crossings, so the router is not the gain on those; the gain is in the parts Graphviz
   ortho cannot do. It ignores ports (control-left 36/46, parallel 26/46), draws 3 edge pairs on
   top of each other, and its `xlabel`s land on lines: 86 of 247 label runs, against 11 for `grid`.
6. `elk` does not keep the grid. Its `INTERACTIVE` strategies are seeded by the positions but
   still re-place nodes (26 of 53 levels and columns out of line) and route edge labels as
   dummy nodes, giving staircase routes: 5.04 bends per edge and 362 crossings. It was the
   worst candidate on every shape measure. Not pursued further.
7. `avoid` (libavoid with the grid positions) is clean on crossings (14) and never draws through
   a box, but its nudging separates parallel runs unevenly and it doubles the bends (1.77): only
   15 of 46 pairs parallel. A general-purpose connector router does not know the
   control-left/feedback-right pair rule; `grid` builds it in.
8. The old lab's `control-grid` positive control was a useful hint: a deterministic placement
   plus a small amount of STPA-specific routing beats the general layout engines here.

**Recommendation.** Adopt `gridstpa.py` (variant `grid`) as the renderer for the
control-structure drawings, replacing the Graphviz spline renderer, after the integrating
session has looked at `results/grid-render/` beside the published SVGs. It reads the same
inputs unchanged and needs no tool beyond Python and PyYAML. Use `route:` hints only for the
few edges that still cross (`z0-sector`'s "pumps, CGMs" first) and leave `bands:` off until the
content work decides what the bands should say.

**What this does not measure:**

- How readable a reader finds a drawing; the visual judgements above are ours.
- Whether a label is unambiguously next to its own line. A label can sit clear of every line
  and still be nearer to a neighbour's line than to its own; nothing here scores that.
- Lines crossing group borders or band boundaries, and group labels under lines (counted as
  label over line, not separately).
- Text width: `gridstpa.py` sizes boxes and labels from Helvetica advance widths. Chrome here
  rendered with Arimo/Nimbus Sans (metric-compatible); a viewer with a wider fallback font
  could see text overrun its box.
- Stability under edits. Node positions are fixed by (column, level), so adding an edge cannot
  move a node, but it can change other edges' routes and label positions; not measured.
- Larger structures. The inputs have 5 to 10 nodes and 7 to 21 edges; the renderer's swap
  search is quadratic in edges and was not tried beyond that.
- Dark mode: every drawing sits on its own white card, as the published ones do; no dark variant.
