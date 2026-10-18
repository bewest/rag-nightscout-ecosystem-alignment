# diagrams — figures drawn from data

*Contributor-facing.* Generates the SVG figures under
[`docs/30-design/platform/diagrams/`](../../docs/30-design/platform/diagrams/) from the files that
hold the facts they show, so a figure changes only when its source does. Pure Python (PyYAML);
same card, font and text measure as [`tools/structure-diagrams`](../structure-diagrams/README.md).

```sh
make diagrams-svg          # regenerate every figure
make diagrams-svg-check    # fail naming each committed figure that differs from its sources
```

| Module · function | Figures | Source | Grade |
|---|---|---|---|
| `hub_active_state.py` · `figure()` | `hub-active-state-treatments.svg`, `hub-active-state-devicestatus-profile.svg` | `tools/lab/hub-active-state/records/cases.json`, `results/crm.json`, `results/nocturne.json`, `results/RESULTS.md` (run date and commits) | measured |
| `end_encoding.py` · `figure()` | `end-encoding-loop.svg`, `end-encoding-trio.svg`, `end-encoding-androidaps.svg` | `specs/sync/registrations/{loop,trio,androidaps}.yaml`, `stateSpans` | read-derived |
| `active_state_rules.py` · `figure()` | `active-state-a3.svg` … `active-state-a9.svg`, `active-state-a13.svg` | `specs/sync/conformance/active-state/*.yaml` (the cases' records and `expected` blocks); the rule's name and sentence from `docs/30-design/platform/spec/state-intent.md` §6.1 | synthetic cases |

`build.py` collects every module's `build()` (`{file name: SVG text}`) and writes them; `--check`
compares instead. Each module's docstring says what each mark means.

Rules the generators keep:

- **Data only.** A figure draws what its source states. The rule figures draw each case's
  `expected` answer and apply no rule themselves; `active_state_rules.RULES` lists the cases drawn
  per rule, and `build()` refuses a case that neither cites the rule nor is the control of a drawn
  case that does.
- **Deterministic.** No timestamps or random ids; every coordinate goes through `svgkit.num()`.
- **Legible at the site's width.** Drawn 720 px wide, shown 1:1, text at 12 px or more.
  `svgkit.svg()` refuses a figure with text measured past the card edge.
- **Accessible.** Each SVG carries `<title>` and `<desc>`; the desc states the figure's finding
  from the data. A state is never colour alone: a disagreement cell is red and marked `≠`, a
  deletion is a cross, an end reason is written out.
- **Roles and products only.** Controller and hub product names; no people or companies.

`test_diagrams.py`: the staleness test regenerates every figure and compares it with the committed
file; three controls each change one input in a temporary copy (a lab answer, a registration's
`endedEncoding`, a case's expected end) and require that exactly the figure drawn from it is
reported stale. A change to a rule's wording in `state-intent.md` §6.1 makes that rule's figure
stale too: run `make diagrams-svg` after editing it.
