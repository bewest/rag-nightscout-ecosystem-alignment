# Metrics, all 12 inputs

Columns:

```
  bends      mean total turning per edge, in right angles (a straight line 0, an L 1, a Z 2; a spline
             counts its curvature)
  axis       share of all edge length running horizontal or vertical (within 3 degrees); sampling at
             2 px puts the corners of an orthogonal route just under 1.0 (control-grid: 0.993-0.997)
  cross      edge crossings away from nodes          overlap  edge pairs drawn on top of each other
  through    edge passes through a node it does not touch
  lbl/line   label text runs lying over any edge line / all text runs outside nodes
  lbl/lbl    text runs overlapping other text runs
  loops      control-feedback pairs: control left of feedback / both straight vertical / parallel at a
             constant separation (same number of bends, separation varying by <= max(8 px, half its median))
  grid       levels and columns whose node centres spread by more than 2 px / levels and columns with 2+ nodes
  area       drawing area per node, viewBox units squared (Graphviz: points; others: px; 1:1 at these sizes)
```

Totals over every input (bends, axis and area: mean of the per-diagram values).

| variant | bends | axis | cross | overlap | through | lbl/line | lbl/lbl | loops left | loops straight | loops parallel | grid misaligned | area/node |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `dot-spline` | 1.07 | 0.127 | 43 | 1 | 0 | 17/254 | 4 | 46/46 | 0/46 | 18/46 | 26/53 | 48003 |
| `grid` | 0.71 | 0.995 | 10 | 0 | 0 | 11/254 | 0 | 46/46 | 17/46 | 46/46 | 0/53 | 54557 |
| `grid-z` | 1.34 | 0.994 | 11 | 0 | 0 | 1/254 | 0 | 37/46 | 17/46 | 42/46 | 0/53 | 57569 |
| `neato-ortho` | 0.67 | 0.995 | 10 | 3 | 0 | 86/247 | 2 | 36/46 | 17/46 | 26/46 | 0/53 | 53144 |
| `elk` | 5.04 | 0.993 | 362 | 0 | 0 | 2/254 | 0 | 26/46 | 0/46 | 9/46 | 26/53 | 88230 |
| `avoid` | 1.77 | 0.991 | 14 | 0 | 0 | 10/254 | 0 | 46/46 | 9/46 | 15/46 | 0/53 | 53786 |
| `control-grid` | 1.16 | 0.994 | 120 | 23 | 15 | 2/254 | 0 | 32/46 | 20/46 | 20/46 | 0/53 | 65785 |
| `control-random` | 2.68 | 0.023 | 1105 | 10 | 275 | 217/231 | 39 | 23/46 | 0/46 | 0/46 | 53/53 | 53794 |

## Controls

A metric is shown to discriminate when `control-random` scores worse than `control-grid` on every input. `bends check` is the largest gap between the measured turning of a `control-grid` edge and the bend count it was constructed with.

| metric | random worse on | random equal on | random better on |
|---|---|---|---|
| bends | 12/12 | — | — |
| axis | 12/12 | — | — |
| crossings | 12/12 | — | — |
| overlaps | 2/12 | aid-loop, z1-proposed | governance, p-apple, p-sqlite, z0-sector, z1-today, z2-agreement, z2b-loop-as-a-service, z3-device |
| through | 12/12 | — | — |
| lbl/line | 12/12 | — | — |
| lbl/lbl | 12/12 | — | — |
| loops left | 7/12 | aid-loop, hub-spoke, p-apple, z1-today, z3-device | — |
| loops straight | 12/12 | — | — |
| loops parallel | 12/12 | — | — |
| grid dev | 12/12 | — | — |

bends check, max error over all inputs: 0

## Per diagram

### aid-loop

| variant | bends (max) | axis | cross | overlap | through | lbl/line | lbl/lbl | loops left / straight / parallel | grid | size |
|---|---|---|---|---|---|---|---|---|---|---|
| `dot-spline` | 0.82 (2.0) | 0.197 | 4 | 0 | 0 | 1/17 | 0 | 2 / 0 / 0 of 2 | 1/3 | 536×384 |
| `grid` | 0.80 (2.0) | 0.995 | 2 | 0 | 0 | 0/17 | 0 | 2 / 1 / 2 of 2 | 0/3 | 754×406 |
| `grid-z` | 1.60 (4.0) | 0.994 | 1 | 0 | 0 | 0/17 | 0 | 2 / 1 / 2 of 2 | 0/3 | 754×527 |
| `neato-ortho` | 0.80 (2.0) | 0.995 | 1 | 0 | 0 | 6/17 | 0 | 2 / 1 / 1 of 2 | 0/3 | 786×396 |
| `elk` | 5.60 (12.0) | 0.992 | 26 | 0 | 0 | 0/17 | 0 | 2 / 0 / 0 of 2 | 1/3 | 710×685 |
| `avoid` | 1.60 (4.0) | 0.994 | 2 | 0 | 0 | 2/17 | 0 | 2 / 1 / 1 of 2 | 0/3 | 754×406 |
| `control-grid` | 1.20 (2.0) | 0.994 | 9 | 0 | 1 | 0/17 | 0 | 1 / 1 / 1 of 2 | 0/3 | 898×406 |
| `control-random` | 2.66 (3.9) | 0.024 | 48 | 0 | 14 | 14/15 | 1 | 1 / 0 / 0 of 2 | 3/3 | 754×406 |

### governance

| variant | bends (max) | axis | cross | overlap | through | lbl/line | lbl/lbl | loops left / straight / parallel | grid | size |
|---|---|---|---|---|---|---|---|---|---|---|
| `dot-spline` | 1.59 (4.7) | 0.158 | 6 | 0 | 0 | 3/30 | 2 | 8 / 0 / 3 of 8 | 2/5 | 762×697 |
| `grid` | 0.95 (2.0) | 0.994 | 4 | 0 | 0 | 2/30 | 0 | 8 / 2 / 8 of 8 | 0/5 | 722×824 |
| `grid-z` | 1.79 (4.0) | 0.992 | 4 | 0 | 0 | 0/30 | 0 | 6 / 2 / 7 of 8 | 0/5 | 617×986 |
| `neato-ortho` | 0.95 (2.0) | 0.994 | 4 | 0 | 0 | 10/28 | 0 | 6 / 2 / 5 of 8 | 0/5 | 617×812 |
| `elk` | 5.08 (14.5) | 0.994 | 55 | 0 | 0 | 0/30 | 0 | 6 / 0 / 1 of 8 | 1/5 | 713×1302 |
| `avoid` | 2.11 (4.0) | 0.990 | 3 | 0 | 0 | 1/30 | 0 | 8 / 1 / 2 of 8 | 0/5 | 673×824 |
| `control-grid` | 1.37 (2.0) | 0.995 | 21 | 4 | 3 | 0/30 | 0 | 5 / 3 / 3 of 8 | 0/5 | 786×824 |
| `control-random` | 2.69 (4.0) | 0.052 | 174 | 0 | 27 | 26/28 | 3 | 4 / 0 / 0 of 8 | 5/5 | 673×825 |

### hub-spoke

| variant | bends (max) | axis | cross | overlap | through | lbl/line | lbl/lbl | loops left / straight / parallel | grid | size |
|---|---|---|---|---|---|---|---|---|---|---|
| `dot-spline` | 0.44 (1.4) | 0.085 | 0 | 0 | 0 | 1/13 | 0 | 1 / 0 / 1 of 1 | 2/5 | 582×454 |
| `grid` | 0.45 (2.0) | 0.996 | 0 | 0 | 0 | 1/13 | 0 | 1 / 1 / 1 of 1 | 0/5 | 719×541 |
| `grid-z` | 0.73 (2.0) | 0.996 | 0 | 0 | 0 | 0/13 | 0 | 1 / 1 / 1 of 1 | 0/5 | 691×554 |
| `neato-ortho` | 0.45 (2.0) | 0.995 | 0 | 0 | 0 | 4/13 | 0 | 1 / 1 / 1 of 1 | 0/5 | 719×529 |
| `elk` | 5.07 (7.9) | 0.988 | 20 | 0 | 0 | 0/13 | 0 | 0 / 0 / 1 of 1 | 3/5 | 707×798 |
| `avoid` | 1.45 (2.0) | 0.991 | 0 | 0 | 0 | 0/13 | 0 | 1 / 1 / 1 of 1 | 0/5 | 719×541 |
| `control-grid` | 0.73 (2.0) | 0.997 | 3 | 0 | 0 | 0/13 | 0 | 1 / 1 / 1 of 1 | 0/5 | 854×541 |
| `control-random` | 2.56 (3.4) | 0.000 | 54 | 1 | 14 | 12/13 | 1 | 1 / 0 / 0 of 1 | 5/5 | 719×541 |

### p-apple

| variant | bends (max) | axis | cross | overlap | through | lbl/line | lbl/lbl | loops left / straight / parallel | grid | size |
|---|---|---|---|---|---|---|---|---|---|---|
| `dot-spline` | 1.27 (2.2) | 0.098 | 4 | 0 | 0 | 3/17 | 0 | 3 / 0 / 1 of 3 | 2/3 | 733×419 |
| `grid` | 0.78 (1.0) | 0.995 | 0 | 0 | 0 | 3/17 | 0 | 3 / 1 / 3 of 3 | 0/3 | 650×548 |
| `grid-z` | 1.56 (2.0) | 0.991 | 0 | 0 | 0 | 1/17 | 0 | 1 / 1 / 3 of 3 | 0/3 | 568×552 |
| `neato-ortho` | 0.78 (1.0) | 0.996 | 0 | 1 | 0 | 3/15 | 0 | 2 / 1 / 2 of 3 | 0/3 | 665×537 |
| `elk` | 4.67 (6.0) | 0.994 | 22 | 0 | 0 | 2/17 | 0 | 0 / 0 / 2 of 3 | 2/3 | 606×704 |
| `avoid` | 2.00 (2.0) | 0.989 | 0 | 0 | 0 | 1/17 | 0 | 3 / 0 / 0 of 3 | 0/3 | 650×548 |
| `control-grid` | 1.56 (2.0) | 0.994 | 8 | 1 | 2 | 2/17 | 0 | 2 / 1 / 1 of 3 | 0/3 | 792×548 |
| `control-random` | 2.88 (3.7) | 0.051 | 34 | 0 | 10 | 14/15 | 4 | 2 / 0 / 0 of 3 | 3/3 | 650×548 |

### p-cncf

| variant | bends (max) | axis | cross | overlap | through | lbl/line | lbl/lbl | loops left / straight / parallel | grid | size |
|---|---|---|---|---|---|---|---|---|---|---|
| `dot-spline` | 0.52 (1.8) | 0.197 | 1 | 0 | 0 | 0/18 | 0 | 2 / 0 / 1 of 2 | 3/5 | 638×588 |
| `grid` | 0.45 (1.0) | 0.996 | 0 | 0 | 0 | 2/18 | 0 | 2 / 1 / 2 of 2 | 0/5 | 611×714 |
| `grid-z` | 0.91 (2.0) | 0.992 | 0 | 0 | 0 | 0/18 | 0 | 2 / 1 / 2 of 2 | 0/5 | 583×758 |
| `neato-ortho` | 0.45 (1.0) | 0.997 | 0 | 1 | 0 | 2/18 | 0 | 1 / 1 / 1 of 2 | 0/5 | 627×703 |
| `elk` | 4.73 (8.0) | 0.993 | 13 | 0 | 0 | 0/18 | 0 | 2 / 0 / 0 of 2 | 3/5 | 707×1231 |
| `avoid` | 1.09 (2.0) | 0.991 | 0 | 0 | 0 | 0/18 | 0 | 2 / 1 / 1 of 2 | 0/5 | 611×714 |
| `control-grid` | 0.91 (2.0) | 0.992 | 2 | 0 | 0 | 0/18 | 0 | 2 / 1 / 1 of 2 | 0/5 | 757×714 |
| `control-random` | 2.54 (3.7) | 0.050 | 60 | 2 | 20 | 14/15 | 4 | 1 / 0 / 0 of 2 | 5/5 | 606×714 |

### p-sqlite

| variant | bends (max) | axis | cross | overlap | through | lbl/line | lbl/lbl | loops left / straight / parallel | grid | size |
|---|---|---|---|---|---|---|---|---|---|---|
| `dot-spline` | 0.81 (1.4) | 0.064 | 2 | 0 | 0 | 2/12 | 0 | 1 / 0 / 1 of 1 | 2/3 | 582×406 |
| `grid` | 0.71 (3.0) | 0.997 | 0 | 0 | 0 | 0/12 | 0 | 1 / 1 / 1 of 1 | 0/3 | 623×526 |
| `grid-z` | 1.14 (4.0) | 0.996 | 0 | 0 | 0 | 0/12 | 0 | 1 / 1 / 1 of 1 | 0/3 | 609×560 |
| `neato-ortho` | 0.43 (1.0) | 0.997 | 1 | 0 | 0 | 4/12 | 0 | 1 / 1 / 1 of 1 | 0/3 | 637×514 |
| `elk` | 5.71 (10.0) | 0.994 | 13 | 0 | 0 | 0/12 | 0 | 1 / 0 / 0 of 1 | 1/3 | 783×680 |
| `avoid` | 1.71 (4.0) | 0.992 | 1 | 0 | 0 | 1/12 | 0 | 1 / 1 / 1 of 1 | 0/3 | 623×526 |
| `control-grid` | 0.86 (2.0) | 0.995 | 2 | 2 | 2 | 0/12 | 0 | 1 / 1 / 1 of 1 | 0/3 | 792×526 |
| `control-random` | 2.74 (3.5) | 0.027 | 18 | 1 | 11 | 11/12 | 4 | 0 / 0 / 0 of 1 | 3/3 | 623×526 |

### z0-sector

| variant | bends (max) | axis | cross | overlap | through | lbl/line | lbl/lbl | loops left / straight / parallel | grid | size |
|---|---|---|---|---|---|---|---|---|---|---|
| `dot-spline` | 1.54 (4.7) | 0.162 | 6 | 0 | 0 | 3/30 | 2 | 8 / 0 / 3 of 8 | 2/5 | 762×709 |
| `grid` | 0.95 (2.0) | 0.995 | 4 | 0 | 0 | 2/30 | 0 | 8 / 2 / 8 of 8 | 0/5 | 729×824 |
| `grid-z` | 1.79 (4.0) | 0.992 | 4 | 0 | 0 | 0/30 | 0 | 6 / 2 / 7 of 8 | 0/5 | 625×1000 |
| `neato-ortho` | 0.95 (2.0) | 0.994 | 4 | 0 | 0 | 11/28 | 0 | 6 / 2 / 5 of 8 | 0/5 | 622×812 |
| `elk` | 5.00 (14.4) | 0.994 | 53 | 0 | 0 | 0/30 | 0 | 6 / 0 / 1 of 8 | 1/5 | 756×1302 |
| `avoid` | 2.11 (4.0) | 0.991 | 3 | 0 | 0 | 1/30 | 0 | 8 / 1 / 2 of 8 | 0/5 | 681×824 |
| `control-grid` | 1.37 (2.0) | 0.996 | 21 | 4 | 3 | 0/30 | 0 | 5 / 3 / 3 of 8 | 0/5 | 798×824 |
| `control-random` | 2.69 (4.0) | 0.052 | 174 | 0 | 27 | 26/28 | 3 | 4 / 0 / 0 of 8 | 5/5 | 681×825 |

### z1-proposed

| variant | bends (max) | axis | cross | overlap | through | lbl/line | lbl/lbl | loops left / straight / parallel | grid | size |
|---|---|---|---|---|---|---|---|---|---|---|
| `dot-spline` | 1.00 (2.5) | 0.115 | 6 | 0 | 0 | 1/30 | 0 | 5 / 0 / 2 of 5 | 2/4 | 854×750 |
| `grid` | 0.81 (2.0) | 0.996 | 0 | 0 | 0 | 0/30 | 0 | 5 / 1 / 5 of 5 | 0/4 | 567×890 |
| `grid-z` | 1.33 (4.0) | 0.995 | 1 | 0 | 0 | 0/30 | 0 | 3 / 1 / 4 of 5 | 0/4 | 567×1060 |
| `neato-ortho` | 0.67 (2.0) | 0.996 | 0 | 1 | 0 | 15/30 | 0 | 3 / 1 / 2 of 5 | 0/4 | 617×878 |
| `elk` | 5.14 (8.0) | 0.992 | 36 | 0 | 0 | 0/30 | 0 | 3 / 0 / 1 of 5 | 3/4 | 674×1382 |
| `avoid` | 1.90 (4.0) | 0.991 | 2 | 0 | 0 | 1/30 | 0 | 5 / 1 / 2 of 5 | 0/4 | 567×890 |
| `control-grid` | 1.14 (2.0) | 0.994 | 20 | 3 | 2 | 0/30 | 0 | 3 / 1 / 1 of 5 | 0/4 | 717×890 |
| `control-random` | 2.54 (3.9) | 0.002 | 190 | 3 | 52 | 27/28 | 6 | 1 / 0 / 0 of 5 | 4/4 | 567×890 |

### z1-today

| variant | bends (max) | axis | cross | overlap | through | lbl/line | lbl/lbl | loops left / straight / parallel | grid | size |
|---|---|---|---|---|---|---|---|---|---|---|
| `dot-spline` | 0.93 (2.0) | 0.162 | 3 | 0 | 0 | 1/18 | 0 | 3 / 0 / 2 of 3 | 3/6 | 599×496 |
| `grid` | 0.58 (1.0) | 0.996 | 0 | 0 | 0 | 0/18 | 0 | 3 / 1 / 3 of 3 | 0/6 | 543×538 |
| `grid-z` | 1.17 (2.0) | 0.995 | 0 | 0 | 0 | 0/18 | 0 | 3 / 1 / 3 of 3 | 0/6 | 543×643 |
| `neato-ortho` | 0.58 (1.0) | 0.996 | 0 | 0 | 0 | 7/18 | 0 | 3 / 1 / 1 of 3 | 0/6 | 588×534 |
| `elk` | 6.00 (14.0) | 0.993 | 36 | 0 | 0 | 0/18 | 0 | 2 / 0 / 1 of 3 | 5/6 | 707×1012 |
| `avoid` | 1.83 (2.0) | 0.990 | 1 | 0 | 0 | 0/18 | 0 | 3 / 0 / 0 of 3 | 0/6 | 546×538 |
| `control-grid` | 1.17 (2.0) | 0.994 | 6 | 2 | 0 | 0/18 | 0 | 1 / 1 / 1 of 3 | 0/6 | 687×538 |
| `control-random` | 2.52 (3.4) | 0.000 | 51 | 1 | 24 | 15/16 | 3 | 1 / 0 / 0 of 3 | 6/6 | 543×538 |

### z2-agreement

| variant | bends (max) | axis | cross | overlap | through | lbl/line | lbl/lbl | loops left / straight / parallel | grid | size |
|---|---|---|---|---|---|---|---|---|---|---|
| `dot-spline` | 1.32 (2.9) | 0.160 | 5 | 0 | 0 | 2/23 | 0 | 5 / 0 / 2 of 5 | 2/4 | 673×630 |
| `grid` | 0.43 (1.0) | 0.997 | 0 | 0 | 0 | 0/23 | 0 | 5 / 3 / 5 of 5 | 0/4 | 578×705 |
| `grid-z` | 0.86 (2.0) | 0.995 | 0 | 0 | 0 | 0/23 | 0 | 5 / 3 / 5 of 5 | 0/4 | 536×759 |
| `neato-ortho` | 0.43 (1.0) | 0.996 | 0 | 0 | 0 | 10/23 | 0 | 5 / 3 / 4 of 5 | 0/4 | 578×694 |
| `elk` | 4.51 (8.0) | 0.990 | 30 | 0 | 0 | 0/23 | 0 | 0 / 0 / 2 of 5 | 1/4 | 566×934 |
| `avoid` | 1.43 (2.0) | 0.989 | 0 | 0 | 0 | 1/23 | 0 | 5 / 1 / 3 of 5 | 0/4 | 578×705 |
| `control-grid` | 0.86 (2.0) | 0.994 | 8 | 1 | 0 | 0/23 | 0 | 4 / 3 / 3 of 5 | 0/4 | 731×705 |
| `control-random` | 2.81 (3.9) | 0.000 | 103 | 0 | 23 | 21/22 | 1 | 2 / 0 / 0 of 5 | 4/4 | 584×705 |

### z2b-loop-as-a-service

| variant | bends (max) | axis | cross | overlap | through | lbl/line | lbl/lbl | loops left / straight / parallel | grid | size |
|---|---|---|---|---|---|---|---|---|---|---|
| `dot-spline` | 1.57 (3.2) | 0.056 | 5 | 1 | 0 | 0/35 | 0 | 6 / 0 / 1 of 6 | 3/6 | 785×630 |
| `grid` | 0.84 (2.0) | 0.994 | 0 | 0 | 0 | 0/35 | 0 | 6 / 2 / 6 of 6 | 0/6 | 637×735 |
| `grid-z` | 1.68 (4.0) | 0.991 | 1 | 0 | 0 | 0/35 | 0 | 5 / 2 / 5 of 6 | 0/6 | 581×920 |
| `neato-ortho` | 0.84 (2.0) | 0.995 | 0 | 0 | 0 | 11/34 | 2 | 4 / 2 / 2 of 6 | 0/6 | 637×723 |
| `elk` | 5.05 (10.0) | 0.994 | 55 | 0 | 0 | 0/35 | 0 | 3 / 0 / 0 of 6 | 4/6 | 712×1167 |
| `avoid` | 2.00 (4.0) | 0.988 | 2 | 0 | 0 | 2/35 | 0 | 6 / 1 / 1 of 6 | 0/6 | 637×726 |
| `control-grid` | 1.26 (2.0) | 0.995 | 18 | 5 | 2 | 0/35 | 0 | 5 / 3 / 3 of 6 | 0/6 | 784×726 |
| `control-random` | 2.74 (3.8) | 0.018 | 174 | 2 | 39 | 30/31 | 7 | 4 / 0 / 0 of 6 | 6/6 | 637×727 |

### z3-device

| variant | bends (max) | axis | cross | overlap | through | lbl/line | lbl/lbl | loops left / straight / parallel | grid | size |
|---|---|---|---|---|---|---|---|---|---|---|
| `dot-spline` | 1.07 (2.5) | 0.067 | 1 | 0 | 0 | 0/11 | 0 | 2 / 0 / 1 of 2 | 2/4 | 449×408 |
| `grid` | 0.75 (1.0) | 0.994 | 0 | 0 | 0 | 1/11 | 0 | 2 / 1 / 2 of 2 | 0/4 | 565×490 |
| `grid-z` | 1.50 (2.0) | 0.994 | 0 | 0 | 0 | 0/11 | 0 | 2 / 1 / 2 of 2 | 0/4 | 523×522 |
| `neato-ortho` | 0.75 (1.0) | 0.993 | 0 | 0 | 0 | 3/11 | 0 | 2 / 1 / 1 of 2 | 0/4 | 565×479 |
| `elk` | 3.92 (4.0) | 0.992 | 3 | 0 | 0 | 0/11 | 0 | 1 / 0 / 0 of 2 | 1/4 | 553×676 |
| `avoid` | 2.00 (2.0) | 0.991 | 0 | 0 | 0 | 0/11 | 0 | 2 / 0 / 1 of 2 | 0/4 | 565×490 |
| `control-grid` | 1.50 (2.0) | 0.992 | 2 | 1 | 0 | 0/11 | 0 | 2 / 1 / 1 of 2 | 0/4 | 696×490 |
| `control-random` | 2.82 (3.4) | 0.000 | 25 | 0 | 14 | 7/8 | 2 | 2 / 0 / 0 of 2 | 4/4 | 565×490 |

