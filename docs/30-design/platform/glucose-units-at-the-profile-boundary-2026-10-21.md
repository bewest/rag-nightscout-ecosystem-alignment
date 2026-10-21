# Glucose units at the profile boundary

*Contributor- and maintainer-facing. Proposal, **DRAFT for maintainer review**, 2026-10-21, against
cgm-remote-monitor `dev` `4bca2ac2` and `v15.0.8` `92d08342`. Defect facts live in the
[backfix register](../remedial/nightscout-backfix-register.md) (BF-172, BF-173, BF-174); the
ecosystem survey of units is [glucose unit conversion](../../10-domain/glucose-unit-conversion-deep-dive.md).
Each claim says whether it was run or read.*

## 1. What Nightscout does today

**Stored values.** Glucose readings (`entries.sgv`) are mg/dl, with no unit field. A profile stores
its sensitivity and targets in its own units and labels them with `units`, both on the document and on
each store entry. In the profile corpus (`specs/nsschema/profile.model.json`) the store-level `units`
is on 100% of 202 documents from 11 sites, spelled `mg/dL`, `mg/dl` or `mmol/L`. A treatment may
carry `units` for its `glucose`.

**Reading the label.** `profile.getUnits()` returns `mmol` for any label containing `mmol`, and
`mg/dl` for everything else, a missing label included (`lib/profilefunctions.js:222-226`).

**Display units.** `settings.units` (`mg/dl` or `mmol`) starts as the site's `DISPLAY_UNITS` and is
then each viewer's browser setting. The server runs the plugins with the site setting, and each
browser runs them with its viewer's setting.

**Where the values meet.** The profile accessors (`getSensitivity`, `getLowBGTarget`,
`getHighBGTarget`) return the stored number. Each consumer that combines it with a reading has to
look up the label and convert:

| consumer | converts | since |
|---|---|---|
| basal profile pill (`lib/plugins/basalprofile.js:65-73`) | yes, sensitivity | #5102, 2019 |
| OpenAPS pill, `lastEnacted.bg` (`lib/plugins/openaps.js`) | yes | `a4e05a16`, 2024 |
| treatment tooltip (`lib/client/renderer.js:613-652`) | yes, from the record's own units | BF-124, #8801 |
| `/pebble` | yes | BF-138, #8777 |
| Bolus Wizard Preview (`lib/plugins/boluswizardpreview.js`) | **no** | BF-172; #8819 proposed |
| Careportal Bolus Wizard (`lib/client/boluscalc.js`) | **no** | BF-173; fixed on `bf/boluscalc-profile-units` |

IOB and COB multiply by sensitivity in the profile's units. Whether any of their results is later
compared with a reading in display units was not examined.

**Writers.** AID apps upload profiles in their user's units (the survey, §1). The profile editor
sets `units` to the editor's display units when it saves (`lib/profile/profileeditor.js:557`,
`:655`) and shows and saves the stored numbers as they are. Read, not run: opening an mmol/L profile
in an mg/dl browser and saving it would relabel it without converting. The editor's DOM test harness
is retired (`tests/profileeditor.test.js`), so this is a lead to reproduce, not a register entry.

**Choosing a profile.** `getCurrentProfile(time, spec_profile)` ignores `spec_profile`, so every
accessor, `getUnits` included, answers for the active profile (BF-174).

## 2. Why the defect recurs

The number and its unit travel separately. The accessors return a bare number, the unit is a
separate property, and each consumer has to remember to join them. Four consumers do this on their
own; the two calculators do not. Before these fixes, no test ran a site whose profile units differed
from its display units. The defect does not show on a site where the two match, which is most sites.

## 3. Proposal

The rule is A11 of the state-intent spec ("Units are declared, never assumed",
[state-intent.md](spec/state-intent.md)), applied to glucose: keep the label that clients already
write, and convert once, where values leave the profile.

| step | what | where | changes stored data |
|---|---|---|---|
| **U0** | The local fixes: BF-174 (`getCurrentProfile` honours a name in the store), BF-173 (bolus calculator), BF-172 (#8819, with the review notes in the register) | in-tree | no |
| **U1** | **Accessors that answer in the caller's units.** An optional last argument, e.g. `getSensitivity(time, spec_profile, units)`, and the same for both targets. Without it, the accessor returns the stored value as today. Conversion and rounding (1 mg/dl, 0.1 mmol/L) live in one helper in `lib/units.js`. Then BWP, the bolus calculator, the basal profile pill and the tooltip move onto it, and the per-consumer code goes | `lib/profilefunctions.js`, `lib/units.js`, consumers | no |
| **U2** | **Labelled quantities in new code.** A JSDoc type `{ value: number, units: 'mg/dl' \| 'mmol' }` for glucose levels and sensitivities that cross a module boundary, and a `units` field on any new API or record shape that carries a glucose value. It applies to new code; existing plugins keep U1's numbers | new modules, platform specs | no |
| **U3** | **Declare the label as it is written.** The profile schema accepts the spellings in use (`mg/dl`, `mg/dL`, `mmol`, `mmol/L`, read by "contains `mmol`") and names the label's two places (document and store entry). Nightscout's own writers keep writing what they write today | `specs/`, API docs | no |
| **U4** | **A missing label.** Today it is read as mg/dl. Options are in §5; whichever is chosen is recorded as a quirk with its versions (D20), not added as a silent heuristic | `getUnits` | no |
| **U5** | **The profile editor.** After the lead in §1 is reproduced: on save, convert the values to the label being written, or keep the profile's own label | `lib/profile/profileeditor.js` | yes, for profiles the editor saves |

**Not proposed:** per-value unit objects in stored profiles, which every reader of today's shape
would fail to parse, and a request parameter asking the server to convert profile values. Every
client converts already; a parameter would add a second place for the rule to live.

## 4. Compatibility

"Old" means a client or record that exists today; "new" means code written to this proposal.

| step | old records read by new code | new records read by old clients | old clients writing | operator-visible | version class |
|---|---|---|---|---|---|
| U0 BF-172, BF-173 | unchanged; each value read in its labelled units | the `Bolus Wizard` treatment's `boluscalc.isf` and targets are in its `units` (display units) where they were the profile's numbers; consistent with its own label for the first time | unchanged | on sites with mismatched units, the estimate, the BWP warning and the calculator's suggestion change from wrong to right | patch, named in the notes |
| U0 BF-174 | unchanged | a saved record's values now match its `profile` name | unchanged | with the picker shown, a chosen non-active profile is used | patch, named in the notes |
| U1 | unchanged | no shape change | unchanged | none beyond U0 | patch |
| U2 | n/a | new fields only, additive | unaffected | none | follows the shape it is added to |
| U3 | unchanged | unchanged | unchanged; the declared vocabulary is what they write | none | none (documentation) |
| U4 "keep" | unchanged | unchanged | unchanged | none | none |
| U4 "infer" or "refuse" | a profile without a label changes how it is read | unchanged | a writer that omits the label gets the new reading | yes, for unlabelled profiles | minor, with a quirk entry and a note |
| U5 | unchanged | a profile saved by the editor in the other units has converted values and a matching label | unchanged | yes, for profiles edited in the other units | patch, named in the notes |

**Records already saved.** A `Bolus Wizard` treatment saved on a mismatched site before BF-173's fix
holds the profile's numbers next to a display-units label. Nothing in the record separates those from
correct ones, so no migration is proposed. A profile already relabelled by the editor (§1) cannot be
told apart from a correct one either.

**Forward.** Once U1 is in, a consumer added later gets converted values by passing
`sbx.settings.units`. A test that runs one site with mismatched units (the BF-173 tests in
`tests/careportal.test.js`, the #8819 test in `tests/boluswizardpreview.test.js`) is the guard against
the next consumer that forgets.

## 5. Decisions for the maintainers

| # | question | options |
|---|---|---|
| UD1 | Do BF-173 and BF-174 go into the 15.0.9 notes as known issues, like BF-172? | **decided 2026-10-21:** named, without ids, beside BF-172 in the rewritten release notes (`9ed4a5441`) |
| UD2 | Land U0 as three small PRs, or wait for U1 and land one change? | U0 first, then U1 as a refactor that keeps U0's tests green / U1 only |
| UD3 | U1's form | optional `units` argument (the smallest change, matches the existing signatures) / a converted view `profile.inUnits(units)` |
| UD4 | A profile without `units` (U4) | keep reading it as mg/dl / infer mmol/L below a threshold, as oref0 (20) and Nightscout's alarm thresholds (50) do / report it as unreadable for unit-sensitive consumers (A11) |
| UD5 | The profile editor (U5), once reproduced | convert on save / keep the profile's label / ask the user |
