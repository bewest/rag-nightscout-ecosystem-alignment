<!-- Body of #8807, branch bf/brush-extent at b919af9f (one commit on dev 43289dde), merged 2026-10-08 as fade2299. This comment is hidden on GitHub. -->
On some page loads, the window in the small chart under the main chart could not be dragged back to the latest reading: the drag stopped part-way across and the page stayed on older readings (BF-168). This was reported on `dev` with a screen recording from a phone, and it is present in 15.0.8 as well. One commit on `dev` `43289dde`, client only.

## What changes for you

*A plain-language summary for people who run their own Nightscout site, for themselves or for a family member.*

**What was wrong.** Under the main chart there is a smaller chart of the last day or two, with a highlighted window showing which part the main chart is displaying. You can drag that window left to look back in time, and drag it right again to come back to the latest reading. On some page loads, most often on a phone, the window stopped moving about a third or more short of the right-hand end, so you could not drag back to the latest reading. The page kept showing older readings until it was reloaded or the browser window changed size (for example by rotating the phone).

**Who is affected.** Anyone viewing the main page, intermittently: it depends on how quickly the page lays itself out when it first draws the chart. In our tests the drag got stuck on about 1 in 6 phone page loads on 15.0.8. Nothing about your data or readings was wrong; only the view was stuck.

**What this change does.** The window can always be dragged all the way to the latest reading, however the page loaded.

**Do you need to do anything?** No.

## Technical detail

`chart.brush` (`lib/client/chart.js:196`) had no extent, so d3-brush used its default: the size of the owner `<svg>`, read once when `.call(chart.brush)` runs (`:384`, inside `chart.update(true)`). The `<svg>` never gets a width: `chart.charts` is the `<g>` appended inside it, so `chart.charts.attr('width', chartWidth)` (`:352`) sizes the `<g>`. When the chart is first drawn before the page has laid out, the browser reports an unsized `<svg>` as its default 300x150, and d3-brush clamps every drag of the selection to x ≤ 300, whatever width the chart has by then.

A tap still worked, because `beforeBrushStarted` clamps to `chart.xScale2.range()`, not to the brush's extent. And `chart.update(false)` updates the scales when the size changes but did not call the brush again. Only `updateBrushToNow()` in `lib/client/index.js` did that, through `window.onresize` (which passes the event as `updateToNow`), the tab becoming visible again, or a forecast toggle. So a page that was never resized kept the wrong limit for as long as it was open.

The change, 8 lines in `lib/client/chart.js`:

- the brush gets an explicit extent, `[[0, 0], [chart.xScale2.range()[1], chart.contextHeight]]`, so the limit comes from the chart's own scale instead of the `<svg>`;
- when `chart.update()` sees a new size, it calls the brush again so the extent is re-read, and then puts back the overlay's `{type: 'selection'}` datum. Calling the brush rebinds the overlay to `overlay`, and without the datum a drag would start a new selection instead of moving the window.

d3-brush 1.1.6 (D3 5, 15.0.8) and 3.0.0 (D3 7, `dev`) read the default extent the same way, so this is not a regression from the D3 7 migration (#8735's `48075a18`).

## Tests

`tests/dependency-d3.test.js`, new case *drags the context window back to now after the chart was drawn before layout*, with mouse and with touch. The chart is drawn at 880 px while its `<svg>` reports 300x150, then updated at 900 px. The test taps the middle, drags to x = 1000, and expects the window at `[675, 900]` and the page out of retro mode.

`tests/fixtures/d3-chart.js` takes an optional layout argument for this. Without it, the fixture keeps pinning the extent to `[[0, 0], [900, 171]]` as before, because jsdom has no SVG sizes. That pin is also why the existing tests could not see this bug.

Controls on `dev` `43289dde`: both new cases fail at `[75, 300]`. With only the extent function removed they fail at `[75, 300]`; with only the re-read in `chart.update()` removed they fail at `[655, 880]`.

### In a browser

Chromium under Playwright, synthetic data, Node 22.23.2, MongoDB 7.0.43, using the alignment repository's `tools/lab/brush-extent/probe.js`. The probe taps the middle of the context chart, then drags the window to the right edge.

- **Race forced** (every `<svg>` reports 300x150 for the first 6 s): `dev` and 15.0.8 both stop at `[245, 300]`, about 1900 minutes behind now. This branch reaches now with touch, with mouse, and after a rotation.
- **Unforced:** the limit at load was 300 in 3 of 28 loads. The drag stuck in 2 of 12 phone loads on 15.0.8 with no resize afterwards. `dev`'s one bad load was followed by a resize, which repaired it. This branch reached now in 5 of 5 phone loads and after widening a desktop window.

### Validation (Node 22.23.2, MongoDB 7.0.43 in a dedicated container)

- Full suite (`ci.test.env` form): 3566 passing, 0 failing, 4 pending, against 3564 on `43289dde`; the 2 added are this commit's.
- ESLint on the three changed files: no findings.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
