<!-- Draft body for branch bf/profile-switch-percentage at 5a895b49 (tree a93bf148), one commit on dev e3adc91d. Register BF-123, issue #7771. This comment is hidden on GitHub. -->
During an AndroidAPS Profile Switch at a percentage (for example 150%) or with a time shift, Nightscout shows and calculates with the same scaled basal, ISF and carb ratio that AndroidAPS uses. One commit on `dev` `e3adc91d`. Fixes #7771 (register BF-123).

## What changes for you

*Plain-language summary for people running their own Nightscout site for themselves or a family
member. Nightscout is not a medical device and none of this is medical advice. Check your
settings and numbers with your care team before relying on them.*

A few words used below:

- **AndroidAPS (AAPS)**: an app that runs on an Android phone and adjusts insulin delivery
  automatically. It sends its data to Nightscout.
- **Profile**: your saved settings, such as basal rates, insulin sensitivity and carb ratios.
- **Profile Switch**: in AAPS, changing to a profile, or to the same profile at a percentage
  (for example 150% during illness, or 80% for exercise), for a set time or until you change it.
  AAPS can also **time-shift** a profile, so its schedule runs a few hours earlier or later.
- **Basal**: the background insulin rate, in units per hour (U/h).
- **ISF** (insulin sensitivity factor): how far one unit of insulin is expected to lower glucose.
- **Carb ratio (IC)**: how many grams of carbohydrate one unit of insulin covers.
- **Bolus Wizard Preview (BWP)**: the Nightscout pill that estimates insulin needed or in excess.
- **IOB / COB**: insulin on board and carbs on board, as Nightscout calculates them.

### What was wrong

When AAPS switched to a profile at a percentage other than 100%, Nightscout named the active
profile correctly, for example "Default (150%)", but showed and used the **100% values**. With a
150% switch on a 1.0 U/h basal, the basal pill and the chart's basal line showed 1.0 U/h instead
of 1.5 U/h, and ISF and carb ratio were the 100% values. The Bolus Wizard Preview and Nightscout's
own IOB and COB calculations used those same values. A time shift was ignored too.

**AndroidAPS's own insulin delivery was never affected.** AAPS works out its doses on the phone.
This was only what Nightscout displayed and calculated. Temporary basal rates were always shown
correctly, because AAPS sends them as actual rates.

### What this change does

While an AAPS Profile Switch with a percentage or a time shift is active, Nightscout now reads the
profile the way AAPS does:

- basal is multiplied by the percentage (150% of 1.0 U/h is 1.5 U/h);
- ISF and carb ratio are divided by it (at 150%, an ISF of 50 reads 33.33, a carb ratio of 10 reads
  6.67);
- glucose targets are not changed by the percentage;
- a time shift moves the whole schedule, as in AAPS: with +2 h, the value that was set for 09:00
  applies at 11:00.

The basal pill, the chart's basal line, the Bolus Wizard Preview, IOB and COB, and the reports use
these values. Nothing stored in your database changes; this is how Nightscout reads the switch.

Two things to keep in mind:

- If AAPS uses **Dynamic ISF** or another feature that changes ISF on the phone, the ISF AAPS
  doses with can differ from the profile ISF that Nightscout shows. That was true before this
  change and still is.
- Switches from older AAPS versions (2.x, marked "CircadianPercentageProfile") are read exactly as
  before.

**What you should do:** nothing. After upgrading, during a percentage switch the numbers
Nightscout shows should match the numbers in AAPS. If they do not, or you are unsure which
numbers are right, check with your care team.

---

## Technical detail

### What AAPS uploads and how AAPS applies it (read)

AndroidAPS `origin/master` `598e2eb39c` and `origin/dev` `7e1d537d49` (read 2026-09-25); same
semantics on both refs. Line numbers are dev first, master in brackets.

- **Upload.** `PS.toNSProfileSwitch`,
  `plugins/sync/.../nsclientV3/extensions/ProfileSwitchExtension.kt:52-78` [`:42-67`], copies the
  switch with `timeshift = 0` and `percentage = 100` before serialising `profileJson`
  (`:54-57` [`:44-47`]), so `profileJson` is the unscaled profile. `percentage` (Int) and
  `timeShift` go out as `percentage` and `timeshift`
  (`core/nssdk/.../mapper/TreatmentMapper.kt:540-541` [`:535-536`],
  `RemoteTreatment.kt:101` [`:85`]). The NSClient v1 uploader on master does the same
  (`plugins/sync/.../nsclient/extensions/ProfileSwitchExtension.kt:16-32`, reset at `:28-31`).
  **`timeshift` is in milliseconds** (`core/data/.../model/PS.kt:22`). No
  `CircadianPercentageProfile` anywhere in either tree.
- **Name.** `getCustomizedName`, `core/objects/.../extensions/ProfileSwitchExtension.kt:28-30`
  [`:20-22`]: `"<name> (<pct>%)"`, or `"<name> (<pct>%,<h>h)"` with a shift.
- **Timeshift to hours.** `ProfileSealed.PS`: `T.msecs(value.timeshift).hours().toInt()`,
  `core/objects/.../profile/ProfileSealed.kt:77` [`:70`], a truncating division to whole hours.
- **Scaling.** `ProfileSealed.kt:324-365` [`:258-300`]: basal `x percentage/100`, ISF and IC
  `x 100/percentage`, targets `targetBlockValueBySeconds(secs, timeshift)` with no multiplier.
- **Direction.** `core/objects/.../extensions/BlockExtension.kt:14-18` [`:10-14`]:
  `shiftedSeconds = (secondsFromMidnight - timeShiftHours * 3600 + 86400) % 86400`, and every
  lookup (`:55-93` [`:43-...`]) reads the schedule at that shifted time. So the value at wall time
  *t* is the schedule's value at *t - timeshift*; AAPS's own test
  `BlockExtensionKtTest.shiftBlock` shows +1 h moving the 01:00 value to 02:00.
- **Download.** `NSProfileSwitch.toProfileSwitch` (`ProfileSwitchExtension.kt:19-50`) treats
  `profileJson` as the pure profile and reapplies `percentage`/`timeShift`. This change does not
  alter stored treatments, so AAPS's round trip is unaffected.

### What Nightscout did

`lib/profilefunctions.js` `getValueByTime` applied `percentage` only when the active switch had
`CircadianPercentageProfile` (`isCcpProfile`, `:128` on `e3adc91d`). An AAPS 3.x switch never has
it, so the injected unscaled `profileJson` was reported as is.

### The change

- `profile.aapsSwitchAdjustment(treatment)` returns `{percentage, timeshiftHours}` for the AAPS 3.x
  shape: no `CircadianPercentageProfile`, an embedded `profileJson`, `percentage` a finite number
  `> 0`. `timeshiftHours = trunc(timeshift / 3600000) % 24` when `timeshift` is a finite number,
  else 0. It returns null for 100% with no shift.
- `getValueByTime`, when no specific profile is requested and the switch is not
  CircadianPercentageProfile, reads every schedule at
  `(secondsFromMidnight - timeshiftHours*3600)` wrapped to one day, then scales `basal` by
  `pct/100` and `sens`/`carbratio` by `100/pct`. Targets, DIA and `carbs_hr` are not scaled.
- The CircadianPercentageProfile path is byte-for-byte unchanged.

### Scope decisions for review

- **CircadianPercentageProfile timeshift is left alone.** Its intended direction is the opposite
  of AAPS 3.x: `time + offset` (`:133-134`), matching AAPS 2.x
  (`v2.8.2.1` `fb93253849`, `core/.../data/Profile.java:320-324`, `originalTime + timeshift`),
  while AAPS 3.x reads `t - timeshift`. AAPS changed direction in `37e3c4532a` (2021-04-29,
  "Profiles -> room"). The CircadianPercentageProfile code also never moves the schedule lookup
  (it shifts `time` by `offset * hours(offset)`, then looks up at the unshifted `minuteTime`), so
  those switches read unshifted today and still do. Only AAPS 2.x sent that flag
  (`NSUpload.java:338-342`, timeshift in hours).
- **Already-scaled `profileJson`.** If a client sent a `profileJson` already scaled together with
  a `percentage`, this change would scale it twice. That cannot be told apart from the record
  alone (comparing against the stored profile of `originalProfileName` is unreliable, since that
  profile may have been edited since). No uploader in the corpus does this: AAPS resets to 100%
  before serialising (above), and no other client sends `percentage` on a Profile Switch (below).
- **Specific-profile requests** (`spec_profile`, used by the careportal bolus calculator when a
  profile is picked) are not adjusted, as for CircadianPercentageProfile.
- **Not changed:** `/api/v2/summary` returns the raw active profile
  (`lib/api2/summary/index.js:117`, `getCurrentProfile()`), which is the unscaled `profileJson`
  for both AAPS and CircadianPercentageProfile switches; its `state.bwp` uses the plugins and so
  the scaled values.

### Tests

`tests/profile-switch-percentage.test.js`, 35 tests, stepped schedules (basal 1/2/3, ISF 50/40/30,
IC 10/8/6, targets 90-110/100-120/110-130, steps at 00:00, 10:00, 12:00 UTC), literal expected
values:

- 150%, 50%, 100% with timeshift 0, +2 h and -2 h at 07:00-14:30: basal, temp-basal total, ISF,
  IC, low and high target, DIA;
- midnight wrap (+2 h at 01:00 reads 23:00; -2 h at 23:00 reads 01:00);
- a 90-minute timeshift acts as 1 h (AAPS truncation);
- the active profile name stays "Default (150%)" / "Default (150%,2h)";
- after the switch ends, the stored profile;
- unchanged: a switch without percentage/timeshift, a string percentage, a switch with no
  `profileJson`, a specific-profile request;
- an absolute temp basal during a 150% switch reads 0.4 U/h over a 3.0 U/h scheduled basal;
- CircadianPercentageProfile control at 150% with timeshift 0, 2, -2 (hours): percentage applied,
  lookup unshifted (unchanged);
- plugins in-process: basal pill, IOB activity, Bolus Wizard Preview at 150% and with no switch.

On `e3adc91d` the same file gives 12 passing / 23 failing; on this branch 35 passing.

Probe `tools/lab/triage-2026-09/profile-switch-percentage.js` (alignment repo): exit 1 on
`e3adc91d` (basal 1.0, ISF 50, IC 10 under "Default (150%)"), exit 0 on `5a895b49` (1.5, 33.33,
6.67), controls passing.

Full suite, `npm test` on `5a895b49`, Node 22.23.2, MongoDB 7.0.43 (version read from the server):
**3205 passing, 3 pending, 0 failing** (3170 on `e3adc91d` plus the 35 new tests).

### What the plugins compute (in-process, before / after)

Profile basal 1.0 U/h, ISF 50, IC 10, target 100-120; glucose 200 mg/dL flat; 1 U and 20 g
30 minutes ago; an AAPS switch 60 minutes ago for 180 minutes. Synthetic data.

| switch | tree | basal pill | ISF | IC | IOB | IOB activity | COB | BWP effect | BWP estimate |
|---|---|---|---|---|---|---|---|---|---|
| none | both | 1.000U | 50 | 10 | 0.969 | 0.08 | 15 | 48.45 | 0.63 U |
| AAPS 150% | `e3adc91d` | 1.000U | 50 | 10 | 0.969 | 0.08 | 15 | 48.45 | 0.63 U |
| AAPS 150% | this branch | **1.500U** | **33.33** | **6.67** | 0.969 | 0.05333 | 15 | 32.3 | 1.43 U |
| AAPS 50% | `e3adc91d` | 1.000U | 50 | 10 | 0.969 | 0.08 | 15 | 48.45 | 0.63 U |
| AAPS 50% | this branch | **0.500U** | **100** | **20** | 0.969 | 0.16 | 15.5 | 96.9 | 0 U |
| 150% + CircadianPercentageProfile | both | 1.500U | 33.33 | 6.67 | 0.969 | 0.05333 | 15 | 32.3 | 1.43 U |

IOB in units does not depend on ISF; its activity (glucose effect) does. These numbers show how
Nightscout's display follows the switch; they are not dosing guidance.

### Break-its (each hunk reverted or altered singly, then restored)

| break | new tests | probe | named failure |
|---|---|---|---|
| gate off (original behaviour) | 12 pass / 23 fail | 1 | same 23 as `e3adc91d` |
| no percentage scaling | 15 / 20 | 1 | "150% timeshift 0 h at 11:00 reads window B" |
| no timeshift | 24 / 11 | 0 | "150% timeshift 2 h at 11:00 reads window A" |
| timeshift direction flipped | 21 / 14 | 0 | "150% timeshift -2 h at 09:00 reads window B" |
| timeshift read as hours, not ms | 24 / 11 | 0 | "100% timeshift 2 h at 13:00 reads window B" |
| no whole-hour truncation | 34 / 1 | 0 | "100% timeshift 1.5 h at 11:00 reads window B" |
| no `profileJson` requirement | 34 / 1 | 0 | "does not scale a named switch that embeds no profileJson" |
| CircadianPercentageProfile not excluded (double scale) | 34 / 1 | 2 | "CircadianPercentageProfile control ..." |
| string percentage accepted | 34 / 1 | 0 | "does not scale when percentage is not a number" |
| specific-profile request adjusted | 34 / 1 | 0 | "does not scale when a specific profile is requested" |

### Client impact (read)

Who sends `percentage` or `timeshift` on a Profile Switch, from `grep` over the corpus under
`externals/` (heads as checked out 2026-09-25):

- **AndroidAPS 3.x** (`598e2eb39c`, `7e1d537d49`): yes, the shape this change reads. Its display in
  Nightscout gets correct; its own records and download are unchanged.
- **AndroidAPS 2.x** (`v2.8.2.1`): only with `CircadianPercentageProfile`; unchanged path.
- **xDrip** (`1ed760048`): reads AAPS Profile Switches only
  (`profileeditor/ImportAapsProfile.java:48-52`); does not upload them.
- **Loop** (LoopWorkspace `f841285`, NightscoutKit `4ec9fd1`), **Trio** (`e41c9db37`),
  **xDrip4iOS** (`c268542e`), **LoopFollow** (`4a74b781`), **nightguard** (`75404bd`),
  **nightscout-connect** (`04102f9`), **tconnectsync** (`7c4b2f4`), **oref0** (`d219baf9`),
  **openaps**, **minimed-connect-to-nightscout**, **nightscout-librelink-up**,
  **share2nightscout-bridge**, **glooko** bridges: no Profile Switch with `percentage`/`timeshift`.
  Loop's override `insulinNeedsScaleFactor` is a "Temporary Override", not read here.
- **Readers that already assume AAPS semantics:** cgmsim-lib (`c09f9c0`,
  `src/pump.ts:32-53`) scales basal by `percentage` for a switch with `profileJson` and no flag;
  nightscout-reporter (`518d61f`, `lib/src/json_data.dart:790-805`) scales by `percentage` without
  the flag. Neither is changed by this PR.
- Nightscout's own careportal Profile Switch sends no `percentage`/`timeshift`.

No client gets worse: the only records whose reading changes are Profile Switches with an
embedded `profileJson`, a numeric `percentage` other than 100 or a non-zero `timeshift`, and no
`CircadianPercentageProfile`, which only AAPS 3.x sends.

Not measured in a browser: the chart's basal line and the reports read the same
`lib/profilefunctions.js` through the client bundle (read).
