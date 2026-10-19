# animations — figures that change over time, drawn from data

*Contributor-facing.* One manim scene, drawn from the same files as the static rule figures,
rendered into [`docs/30-design/platform/animations/`](../../docs/30-design/platform/animations/) as
a VP9 `.webm` (1280×720, 30 fps), a poster `.png` (the last frame) and a `.sources.json` sidecar.

```sh
make animations          # render (needs manim 0.20 and PyAV; MANIM_PY, MANIM, ANIM_MEDIA)
make animations-check    # fail naming each animation whose scene or inputs changed since its render
```

`make animations` runs `render.py --media-dir $(ANIM_MEDIA)`. manim writes its cache and a lossless
QuickTime RLE render there, outside the repository; `render.py` encodes VP9 once (crf 32), renders
the poster with `manim -s`, writes the sidecar, and refuses a video over 2 MB or a set over 10 MB.

| Animation · scene | Shows | Source | Grade | Static figure |
|---|---|---|---|---|
| `active-state-spans` · `active_state_spans.py` `ActiveStateSpans` | rules A5–A8 of state and intent §6.1, one case each: records land in the order the hub received them, the derived instances start, end, are superseded or vanish as each lands, then a cursor visits each "active at" query; the last frame lists each case's instances and active sets | `specs/sync/conformance/active-state/` (loaded with `tools/diagrams/active_state_rules.py`); instances after each record from `tools/nsschema/active_state.py`; rule names from `spec/state-intent.md` | synthetic cases; after the last record the instances equal each case's `expected` block, or the scene refuses to render | `diagrams/active-state-a5.svg` … `a8.svg` |

**Text size.** The site shows the 1280 px video 688 px wide on a 1440 px desktop window and 358 px
wide on a 390 px phone (measured in headless Chrome, 2026-10-18), a scale of 0.54 and 0.28. Text is
manim font size 18 or more (`common.MIN_SIZE`; a 22.5 px CSS font on the canvas), which shows at
12.1 px on the desktop and 6.3 px on the phone; the per-case frames use 20 (13.4 px on the
desktop). On a phone the poster and the static figures `diagrams/active-state-a5.svg` … `a8.svg`
carry the content. Two earlier scenes were replaced by static figures on 2026-10-18 because their
text showed at 9.4 px on the desktop: the two hubs' readings (`hub-active-state`; the static
`diagrams/hub-active-state-*.svg` show every case) and the command lifecycle, whose call lines
with payload, hash and expiry do not fit four lanes at font size 18
(`tools/diagrams/command_lifecycle.py` draws it).

`sources.py` lists each animation's scene, class and inputs; the scenes import their case lists from
it. An input is a file, hashed whole, or a specification with the rule ids whose bold names the
animation shows: only those names are hashed, so other edits to the specification do not make the
animation stale.

`test_animations.py`: video bytes are not deterministic, so the drift test compares the sidecar's
hashes with the files as they stand; it also checks the poster, sidecar and sizes. Its controls
each change one input in a temporary copy (an active-state case, a rule name in `state-intent.md`,
the scene file, `common.py`) and require that the animation is reported stale; an edit to
`state-intent.md` outside the rule names, or to a lab result no animation draws, must report none.

Rules the scenes keep, as `tools/diagrams` does: data only (every instance and active set comes
from a case or a reference function the cases are tested against); text at manim font size 18 or
more; the tools/diagrams palette; roles and products only, no people or companies; calm motion,
about 1.5 s on each state change; a final frame that summarises and serves as the poster.
