# brush-extent — BF-168 in a real browser

*Contributor-facing.* Measures whether the context chart's window (the brush under the main
chart) can be dragged back to now (register BF-168, queue `BFQ-168`). Synthetic data only.

- `probe.js` boots one cgm-remote-monitor tree on a fresh database, seeds a profile and 48 h of
  CGM readings, opens the main page in Chromium (Playwright) and records the brush's drag limit
  (d3-brush's stored extent) beside the context chart's width. Then it taps the middle of the
  context chart, drags the window to the right edge, drags again from near the edge and taps
  inside the right edge, recording retro mode and the brush selection after each step. The header
  comment describes the modes; `-force` makes every `<svg>` report the browser default 300x150
  for 6 s after load, which is the race made certain.

It needs `NODE_PATH` pointing at a `node_modules` with `playwright`, `n` with Node 22.23.2, and a
MongoDB (the runs below used a dedicated `mongo:7.0.43` container).

## Results, 2026-10-07

Trees: `dev` `43289dde`, `v15.0.8` `92d08342`, and the fix branch `bf/brush-extent` `b919af9f`
(one commit on `dev` `43289dde`). Chromium 1243 under Playwright 1.56.1, Node 22.23.2.

**Forced** (`results/*-force*.json`):

| tree | mode | drag limit at load | after dragging right |
|---|---|---|---|
| `dev` | touch | 300 (chart 884) | stuck at `[245, 300]`, retro, about 1900 min behind now |
| `v15.0.8` | touch | 300 (chart 884) | stuck at `[245, 300]`, retro, about 1900 min behind now |
| fix | touch, mouse, touch after rotating | the chart's width | `[829, 884]` / `[1196, 1276]`, at now |

The tap inside the right edge did not bring `dev` or `v15.0.8` back to now in the forced run.

**Unforced** (`results/unforced-runs.json`; these drags ended 40 px past the chart edge): the drag
limit at load was 300 while the chart was 406 or 872 px wide in 3 of 28 loads, once on `dev` and
twice on `v15.0.8`. Both `v15.0.8` cases were phone loads with no resize afterwards, and the drag
stopped at x = 300 (2 of 12 such loads on `v15.0.8`; 0 of 11 on `dev`). The `dev` case was
followed by a resize, which re-reads the limit (`window.onresize` reaches `updateBrushToNow()`,
which calls the brush again), and the drag then reached now.

**Fix, unforced** (`results/fix[1-5]-touch.json`, `fix-mouse-widen.json`): 5 of 5 phone loads and
the widened desktop load reached now.

Mechanism, read from the code and confirmed by the runs: `chart.charts` is the `<g>` inside the
`<svg>`, so `chart.charts.attr('width', …)` never sizes the `<svg>`; d3-brush's default extent
reads the `<svg>`'s own size when `.call(chart.brush)` runs, and `chart.update()` never calls the
brush again when the width changes.
