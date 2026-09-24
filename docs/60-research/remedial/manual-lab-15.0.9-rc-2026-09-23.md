# Manual browser checks on the 15.0.9 combined rc

> **Snapshot: checked by hand on 2026-09-23 (US afternoon; the server clocks read 19:00 to 22:45 UTC) against `ec70aab0`, the head of `rc/15.0.9-combined-36b` at the time: `origin/dev` `1f9a9d10` plus the nine pending PRs #8748, #8749, #8751, #8753, #8754, #8755, #8756, #8757 and #8758. 15.0.8 (`92d08342`) was checked for comparison where noted. Nothing here is released. Current facts: [`queue/work-queue.yaml`](../../../queue/work-queue.yaml) (RT-D3, ADV-ALARM, RT-0, BFQ-103) and the [backfix register](../../30-design/remedial/nightscout-backfix-register.md).**

Audience: contributors and the maintainer. Contributor-facing and technical. Not medical advice.

The maintainer ran every check below in Chrome, with an agent seeding each scenario and firing its triggers. This covers the checks the [15.0.9 release readiness](../../30-design/modernization/release-readiness-15.0.9-2026-09-22.md) §3.3 asks a person with a browser to do, and the paths the [automated browser evidence](../modernization/rt-d3-and-alarm-browser-evidence-2026-09-22.md) lists as not covered.

## Summary

| # | scenario | instance | result |
|---|---|---|---|
| 1 | Treatment drag, mouse, mg/dL (RT-D3) | `drag` | pass: move, cancel, right-edge limit, left-edge Remove (accepted Remove deletes). **Split drop fails: BF-103** |
| 2 | Same, on 15.0.8 | `drag-1508` | same as #1, **BF-103 included** |
| 3 | Treatment drag, mouse, mmol/L | `drag-mmol` | pass (move, cancel, right edge, left-edge Remove) |
| 4 | Treatment drag, touch (device emulation), plus brush pan and phone-width layout | `drag` | pass |
| 5 | Alarms, `AUTH_DEFAULT_ROLES=denied` | `alarm` | pass |
| 6 | Alarms, `denied` with `AUTHENTICATION_PROMPT_ON_LOAD=true` | `alarm-prompt` | pass |
| 7 | Alarm on a page with no glucose reading (BF-90, #8755) | `noreading` | pass |
| 8 | Bolus Wizard quick picks (BF-69 #8756, BF-35 #8735) | `quickpick` | pass |
| 9 | Empty site (#8732) | `empty` | pass |
| 10 | COB from device status (`34e9b2da`), pills and cold load (#8732, #8729) | `cob` | pass; the fallback to treatment COB after 10 min was not observed |

One new defect: **BF-103**, which is on 15.0.8 too.

## Setup

| item | value |
|---|---|
| tree under test | worktree `externals/work/crm-lab-manual`, detached at `ec70aab0`, `npm ci --ignore-scripts` (connector pin as committed there: `0.1.0-dev.2`) |
| 15.0.8 comparison | `externals/work/crm-w2-d3-1508` at `92d08342` |
| server | Node 22.22.0, `NODE_ENV=development`, so each server builds and serves its own worktree's client; `TZ=UTC` |
| database | `mongo:7` container `ns-lab-manual` on 127.0.0.1:27094, one database per instance |
| browser | the maintainer's Chrome. In #5 and #6 each page ran in its own profile: normal window, Incognito, and Guest |
| data | synthetic only, every value a literal in `tools/review/manual-lab/seed.js` |
| tooling | `tools/review/manual-lab/lab.sh` over `tools/review/probes/w2-instance.sh`. The API secret is generated into the state directory and never printed |

| instance | port | settings | seeded |
|---|---|---|---|
| `drag` | 15201 | `denied` | profile; 72 readings; six labelled treatments (two carbs + insulin, one of them in the split zone, one carbs-only near now, one insulin-only); a subject with `*:*:read` + `api:treatments:*` |
| `drag-mmol` | 15202 | `denied`, `DISPLAY_UNITS=mmol` | as `drag` |
| `drag-1508` | 15203 | `denied`, on 15.0.8 | as `drag` |
| `alarm` | 15211 | `denied`, `ALARM_TYPES=simple BG_LOW=55 BG_TARGET_BOTTOM=80` | profile; 36 readings at 105; a `readable` subject and a `status-only` subject |
| `alarm-prompt` | 15212 | as `alarm` plus `AUTHENTICATION_PROMPT_ON_LOAD=true` | as `alarm` |
| `noreading` | 15221 | `readable`, `pump` enabled, `PUMP_ENABLE_ALERTS=true` | profile only, no readings |
| `quickpick` | 15231 | `denied`, `boluscalc food` enabled | profile; 12 readings; four quick picks (one hidden, one hide-after-use) interleaved with two plain foods; a subject with `*:*:read`, `api:treatments:create`, `api:food:*` |
| `empty` | 15241 | `readable` | nothing |
| `cob` | 15251 | `readable`, `openaps loop sage cage` enabled, `DEVICESTATUS_ADVANCED=true` | profile; 72 readings; a 40 g + 3 U meal 1 h ago; a site change 3 days ago; no sensor start; an AndroidAPS-shaped device status with `openaps.suggested.COB` 22 and no timestamp |

## Results

### 1–4. Treatment drag (RT-D3)

The page was opened with the editor token, and edit mode was switched on.

| check | #1 mouse mg/dL | #2 15.0.8 | #3 mouse mmol/L | #4 touch |
|---|---|---|---|---|
| move inside the chart stores the prompt's time | pass | pass | pass | pass |
| cancelled move leaves it unchanged | pass | not run | pass | not run |
| drag past the right edge stops at the chart edge | pass, about 1 h after now | pass | pass | pass |
| drag past the left edge becomes "Remove treatment?" | pass; accepting deleted it | pass | pass | pass |
| split drop "Move carbs" (top 50 px) | **fails (BF-103)** | **fails, same way** | not run | not run |
| brush / context pan | n/a | n/a | n/a | pass |

In #4 the page was also reloaded several times at phone width. The chart never loaded blank (#8729), and the pills did not overlap.

**BF-103.** After "Move carbs", the page shows and stores the new `created_at`, but the new record keeps `mills` and `date` at the pre-move time, plus `mgdl` / `scaled`. The page then logs `<g> attribute transform: Expected number, "translate(undefined, …"` and draws the carbs glyph at the chart's top-left corner. Stored values:

| tree | `created_at` | `mills` / `date` | extra fields |
|---|---|---|---|
| rc | 20:02:06.701Z | 19:09:23.509Z | `mgdl: 110`, `scaled: 110` |
| 15.0.8 | 19:30:04.900Z | 19:17:09.526Z | `mgdl: 110` |

The IOB/COB effect was measured afterwards on the rc with a control (COB 0 vs 25 g, IOB 0 vs 2.49 U). The mechanism and the control are in the [BF-103 evidence](bf103-split-drag-stale-time-2026-09-23.md).

### 5. Alarms with `AUTH_DEFAULT_ROLES=denied`

| page | browser profile | how it logged in | warning (70) | urgent (45) |
|---|---|---|---|---|
| A | normal | `readable` token typed at the lock prompt, not remembered | received | received |
| B | Incognito | API secret typed at the prompt, "Remember this device" ticked | received | received |
| C | Guest | `?token=` for a `status-only` subject; no data shown | **not received** | **not received** |

- **Silencing.** A's silence stayed on A. Its subject lacks `notifications:*:ack`, so the server ignores the ack without logging anything, and B kept sounding. B's silence reached every page; the server logged `ack received 2 default 900000`.
- **Reloads.** After a reload, B stayed logged in (remembered secret), A asked again, and C still had no data.
- **Automated re-run.** `tools/review/probes/alarm-denied-browser.js` on a fresh instance of the same tree (port 15219) gave 10 checked, 0 failing. The status-only page received 0 alarms while its connection was shown live, and the secret-at-prompt and token pages received 2 of 2.

### 6. Alarms with `AUTHENTICATION_PROMPT_ON_LOAD=true`

| page | browser profile | how it logged in | urgent (45) |
|---|---|---|---|
| A | normal | the login prompt appeared on load; `readable` token typed into it | received immediately |
| B | Incognito | `?token=` readable, no prompt | received immediately |
| C | Guest | `?token=` status-only; no data, asked for login | not received |

A's and B's silences each stayed local, because both subjects are `readable`.

### 7. Alarm with no reading (BF-90)

A pump reservoir alert is the alarm source (8 U warning, then 3 U urgent), with no glucose reading stored. The page raised no console error and did not sound, and logged `urgent alarm was disabled locally no reading loaded`. **Control:** after 12 readings were posted, the same 3 U alert sounded and the chart showed 105.

### 8. Bolus Wizard quick picks

- **The list:** the chooser offered exactly lab-breakfast (45 g), lab-lunch (70 g) and lab-snack (hides after use) (20 g), in position order. It offered no plain food and no hidden pick (BF-69).
- **Selection:** each pick entered its own grams (BF-35).
- **Hide after use:** submitting lab-snack stored the treatment and hid the pick.
- **A pick added while the page was open** (lab-late, 33 g) did not appear until a reload, and did after it. This is the known delivery gap, BFQ-93 (food is not in the broadcast delta), not BF-69.

The wizard's IOB read 0.00 with no insulin given.

### 9. Empty site

- **Redirect:** one "Redirecting you to the Profile Editor" alert, then `/profile`.
- **Warning:** the Profile Editor showed its default-values warning.

### 10. COB, pills, cold load

| check | result |
|---|---|
| COB pill with the AndroidAPS-shaped status | 22 g; tooltip Source OpenAPS, Device `openaps://lab-phone`, and the treatment-derived value (about 27 g) |
| a Loop-shaped status posted while the page was open (`loop.cob.cob` 18) | the pill updated without a reload to 18 g, Source Loop |
| SAGE with no sensor start | `n/a` (#8732); CAGE about 72 h |
| pill and toolbar hover feedback; titles on pills without a tooltip | present (#8732) |
| repeated reloads, including at phone width | the chart never loaded blank (#8729) |

This checked what the pill displays. It is not a review of `34e9b2da` (BF-57).

## Observations that are not defects

- **Browser storage is shared per profile.** In a first attempt at #5 all three pages ran as tabs of one profile. B's remembered secret then authenticated C as well, and C alarmed. With each page in its own profile the result is as above. Any repeat of #5 needs separate profiles.
- **Alarms fire on a change of level, and a silence is site-wide.** A repeated 70 mg/dL raises no new warning. A silence from a subject with `notifications:*:ack` holds for every page on the site until it expires. Clearing it in the lab took a server restart.
- **Two scenario 6 symptoms were setup errors.** "Wrong API secret" for a typed token, and a page stuck on 105 while the server emitted: both came from windows still open on the scenario 5 port. The token for one instance is not valid on another, and those pages were watching a server that never received the reading.
- **A readable token's silence is local-only, and the page does not say so.** This is the designed behaviour for a subject without `notifications:*:ack`. The server-side branch carries a TODO for telling the client.
- **The food `hidden` field is stored as the string `"true"` after hide-after-use**, next to booleans on the seeded picks. #8735 documents this and matches both spellings (`lib/food/quickpick.js`, `lib/server/food.js`).
- **An "IOB ---U undefined" sighting was not reproduced.** `---U` is the IOB pill with no treatment or pump data (`lib/plugins/iob.js`); a no-reading instance shows exactly that. "undefined" was not found on any page checked by script.

## Relation to PR #8598

PR #8598's head `4011193e` contains seven of the nine PRs above; #8754 and #8758 were open when this was written. Every client file these checks exercise is identical between `ec70aab0` and `4011193e`, **except `lib/api3/alarmSocket.js`, which differs by #8754**. So #5 and #6 were run on a tree with one alarm-socket change the release PR does not yet carry.

## Not covered

- Browsers other than Chrome; a real phone (the servers listened on 127.0.0.1); the split drops in mmol/L and by touch; "Move insulin" by hand. Its code path is the same as "Move carbs", and the IOB effect was measured by control.
- A warning-level alarm on the `alarm-prompt` instance, and whether an urgent alarm breaks through a local warning silence.
- COB falling back from device status to the treatment-derived value after 10 minutes.
- Profile editing disabled after a failed profile load (#8732), which needs a load failure to be arranged.

## Reproduce

```bash
export LAB_RC=$PWD/externals/work/crm-lab-manual        # detached at the tree under test
export LAB_REF=$PWD/externals/work/crm-w2-d3-1508        # optional, 15.0.8 for drag-1508
export LAB_STATE=/path/to/scratch/manual-lab-state
tools/review/probes/w2-instance.sh prep "$LAB_RC"        # once per worktree (W2_STATE=$LAB_STATE)
tools/review/manual-lab/lab.sh up                        # all nine instances, or name some
tools/review/manual-lab/lab.sh urls                      # addresses and lab tokens
tools/review/manual-lab/lab.sh fire alarm warn           # triggers: alarm warn|urgent|normal,
                                                         #   noreading warn|urgent|readings,
                                                         #   quickpick late, cob openaps|loop
tools/review/manual-lab/lab.sh down
```

Data ages from the moment of seeding; re-run `up <name>` for a fresh instance.
