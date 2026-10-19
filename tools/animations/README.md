# animations — figures that change over time, drawn from data

*Contributor-facing.* Three manim scenes, each drawn from the same files as a static figure, rendered
into [`docs/30-design/platform/animations/`](../../docs/30-design/platform/animations/) as a VP9
`.webm` (1280×720, 30 fps), a poster `.png` (the last frame) and a `.sources.json` sidecar.

```sh
make animations          # render all three (needs manim 0.20 and PyAV; MANIM_PY, MANIM, ANIM_MEDIA)
make animations-check    # fail naming each animation whose scene or inputs changed since its render
```

`make animations` runs `render.py --media-dir $(ANIM_MEDIA)`. manim writes its cache and a lossless
QuickTime RLE render there, outside the repository; `render.py` encodes VP9 once (crf 32), renders
the poster with `manim -s`, writes the sidecar, and refuses a video over 2 MB or a set over 10 MB.

| Animation · scene | Shows | Source | Grade | Static figure |
|---|---|---|---|---|
| `active-state-spans` · `active_state_spans.py` `ActiveStateSpans` | rules A5–A8 of state and intent §6.1, one case each: records land in the order the hub received them, the derived instances start, end, are superseded or vanish as each lands, then a cursor visits each "active at" query | `specs/sync/conformance/active-state/` (loaded with `tools/diagrams/active_state_rules.py`); instances after each record from `tools/nsschema/active_state.py`; rule names from `spec/state-intent.md` | synthetic cases; after the last record the instances equal each case's `expected` block, or the scene refuses to render | `diagrams/active-state-a5.svg` … `a8.svg` |
| `hub-active-state` · `hub_active_state_scene.py` `HubActiveState` | cases c1 (cancel), c3 (devicestatus seconds read as minutes), c7 (backfill): records as written, each hub's derived windows or spans, then each hub's reading at each query time, Nocturne's that differ marked ≠ | `tools/lab/hub-active-state/records/cases.json`, `results/crm.json`, `results/nocturne.json`, `results/RESULTS.md` (loaded with `tools/diagrams/hub_active_state.py`) | measured, run date and commits on screen | `diagrams/hub-active-state-*.svg` |
| `command-lifecycle` · `command_lifecycle.py` `CommandLifecycle` | five command cases call by call: propose, approve naming the payload hash, fetch, the controller's hash and expiry check, outcome; an approval after expiry, a received payload whose hash differs, an `unconfirmed` command replaced by a late report, a cancel after hand-over | `specs/sync/conformance/commands/` (replies from each case's `expected`); record states from `tools/nsschema/commands.py`; rule names from `spec/commands.md` | proposed (commands specification), synthetic cases | the poster (`command-lifecycle.png`) |

`sources.py` lists each animation's scene, class and inputs; the scenes import their case lists from
it. An input is a file, hashed whole, or a specification with the rule ids whose bold names the
animation shows: only those names are hashed, so other edits to the specification do not make the
animation stale.

`test_animations.py`: video bytes are not deterministic, so the drift test compares the sidecar's
hashes with the files as they stand; it also checks the poster, sidecar and sizes. Its controls
each change one input in a temporary copy (an active-state case, a Nocturne lab answer, a command
case, a rule name in `commands.md`, a scene file) and require that exactly the animation drawn from
it is reported stale; an edit to `commands.md` outside the rule names must report none.

Rules the scenes keep, as `tools/diagrams` does: data only (every reply, instance and reading comes
from a case, a lab result or a reference function the cases are tested against); text at manim
font size 14 or more (a 12 px capital at 720p); the tools/diagrams palette; roles and products
only, no people or companies; calm motion, about 1.5 s on each state change; a final frame that
summarises and serves as the poster.
