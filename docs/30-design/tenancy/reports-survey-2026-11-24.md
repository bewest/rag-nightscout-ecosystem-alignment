# Reports and statistics survey, for storage tiers and a per-tenant-day summary row

*Research note, 2026-11-24, for the [storage tiering proposal](storage-tiering-proposal-2026-11-24.md)
(sections 4–6). Section numbers "§" below refer to that proposal.*

**Labels.** **[R]** means read-derived from code at the commit given. Nothing in this note was run.
**[C]** means cited from an external source. Anchors are `path:line` within the tree named.

## 0. Trees and heads

All heads below come from `git log -1 --format=%h`.

**Mismatch: `externals/cgm-remote-monitor` is the wrong tree for this survey.** It is a 2014 checkout of a fork
(`6893781f`, 2014-11-06, the 0.5.0 merge) and has no `lib/report_plugins`. It was left unchanged. This note reads
cgm-remote-monitor instead from **`externals/cgm-remote-monitor-official` at `official/dev` = `79144cbd0`**
(2026-11-17), exported with `git archive` into scratch. That worktree itself is checked out at `ca1652d60`, and
its `origin/dev` is `4a482627b`. cgm-remote-monitor anchors below are against `79144cbd0`.

| tree | head |
|---|---|
| cgm-remote-monitor-official @ official/dev | 79144cbd0 |
| nightscout-reporter | 518d61f |
| nocturne | ce9d55e31 |
| nighttroop | 39c182d |
| AndroidAPS | 7e1d537d49 |
| Trio | 0b29cd534 |
| LoopFollow | 4a74b781 |
| xDrip | 1ed760048 |
| xdripswift | c268542e |
| GlycemicGPT | d1a9adb7 |
| Loop | c30b5c89 (nested in LoopWorkspace 548b332) |
| nightguard | 75404bd |
| nightscout-cgm-skill | 91a53ea |
| ns-parquet | not a repo of its own; data only |

What is missing or has nothing to report:
- No top-level `externals/Loop`. Loop sits inside LoopWorkspace and has no statistics view, only a lesson
  (`Loop/Learn/Lessons/TimeInRangeLesson.swift:17`) [R].
- ns-parquet holds parquet data and no statistics code. Its finest aggregate is a 5-minute grid [R].
- Only some of the cgm-remote-monitor-family plugins listed in the brief exist as files. "AGP" is `agp.js`;
  there is no separate CGP plugin, because the pentagon lives in `lib/report/pentagon.js`.

## 1. Clinical standards these reports mirror [C]

- **2019 International Consensus on Time in Range** (Battelino et al., *Diabetes Care* 42(8):1593–1603,
  doi:10.2337/dci19-0028, https://pmc.ncbi.nlm.nih.gov/articles/PMC6973648/):
  - **Data:** at least 14 days of CGM with at least 70% of the data captured.
  - **Bands:** TBR level 2 below 54 mg/dL; TBR level 1 54–69; TIR 70–180; TAR level 1 181–250; TAR level 2 above
    250.
  - **Adult targets:** TIR above 70%, TBR below 4% (below 1% under 54), TAR below 25% (below 5% over 250).
  - **Other targets:** CV of 36% or less. In pregnancy the range is 63–140 mg/dL.
  - **Reporting:** a standardised AGP report.
- **GMI** (Bergenstal et al., *Diabetes Care* 41(11):2275–2280, 2018): GMI (%) = 3.31 + 0.02392 × mean glucose
  (mg/dL). The older eA1c formula, (mean + 46.7) / 28.7 (ADAG, Nathan et al. 2008), is still used by several
  apps.
- **AGP:** the current AGP report plots the 5/25/50/75/95 percentiles by time of day, "as if in a single day"
  (sample report, https://www.healthpartners.com/institute/wp-content/uploads/2025/05/Ambulatory-Glucose-Profile-Report-Overview.pdf).
  Older AGP renderings use 10/25/50/75/90, and several apps below still do.
- **Comprehensive Glucose Pentagon (CGP):** Vigersky et al. 2018, doi:10.1177/1932296817718561, as cited in
  cgm-remote-monitor `lib/report/pentagon.js:3`.

**What the standards imply for storage:** every standard metric is computed over a 14–90-day window of whole
local days, and it is dominated by mean, SD and band fractions. The one part that is not a daily scalar is the
AGP, a per-time-of-day percentile pooled across days.

## 2. cgm-remote-monitor reports (official/dev 79144cbd0) [R]

These are shared mechanics for every report:
- **Range:** the default is the last 7 days (`lib/report/reportclient.js:92`). Presets run 1/2/3/7/14/31/90 days
  (`views/reportindex.html:52-58`). The hard cap is `maxdays = 6*31` = 186 days (`reportclient.js:35`, `:468`,
  `:493`), and the day before the range is also loaded for treatments (`:504-515`).
- **Loading:** day by day, three API v1 calls per day:
  - `entries.json?find[date][$gte..$lt]&count=10000` (`:698`)
  - `treatments.json?find[created_at]…&count=1000` (`:758`)
  - `devicestatus.json` (`:794`), only when the IOB, COB, OpenAPS or predicted options are on (`:674`)
  - Profiles come from `/api/v1/profiles` by `startDate` (`:855-889`), and Profile Switch treatments from `:818`.
- **Day definition:** a report day is a calendar day in the profile time zone, DST included
  (`lib/report/agp-data.js:5-10`).
- **Deduplication:**
  - SGVs are deduplicated to at most one per minute (`lib/report/uniqsgv.js:21`).
  - AGP data also drops repeated timestamps (`agp-data.js:16-18`).
  - Values outside 39–600 are dropped (`agp-data.js:15`).
- **Statistics library:** mean; population SD; and a nearest-rank quantile that averages the two middle values
  for an even count (`lib/report/statistics.js:31-63`).
- **Targets:** taken from the user's input (`reportclient.js:278`), with defaults `bgTargetBottom` and
  `bgTargetTop` (`:48-53`). The low/in/high split in several reports therefore depends on a per-request
  threshold.

The "needs detail" column means: can this be produced at full fidelity from a per-day summary row of the kind in
section 5?

| report | inputs | statistics | span | needs detail? |
|---|---|---|---|---|
| **agp** (`report_plugins/agp.js`) | entries sgv | <ul><li>% CGM active, time-weighted with the interval capped at 5 min (`agp-data.js:26-36`)</li><li>mean, SD, GMI and mmol/mol (`agp.js:101-106`)</li><li>CV (`:106`)</li><li>5-band % by reading count: <54, 54–69, 70–180, 181–250, >250 (`:128-137`)</li><li>p5/25/50/75/95 in 15-minute time-of-day bins (`:171-187`)</li><li>a daily mini-grid of the last 28 days (`:302-304`)</li></ul> | range ≤186 d | **Partly.** Scalars and bands come from sums plus a histogram. The p5..p95 time-of-day percentiles need per-reading values per time bin: exact from detail, close from a 5-minute grid. The mini-grid needs a trace. |
| **dailystats** | sgv | <ul><li>per day: count, low/in/high by user target (`dailystats.js:103-121`)</li><li>min, max, mean, SD (`:157`)</li><li>quartiles 25/50/75 (`:138`)</li></ul> | range | **No** with a 1 mg/dL per-day histogram, which makes the user-target split and the quartiles exact. Mean and SD come from n, Σ and Σ². |
| **glucosedistribution** | sgv, optionally filtered by hour of day (`glucosedistribution.js:47`, `:210`) | <ul><li>bands: TIR 70–180, tight 70–140, normal 63–140 (`:20-21` of the summary block), or custom</li><li>per band: mean, median, SD (`:403-405`)</li><li>eA1c as DCCT and IFCC (`:464`)</li><li>GMI, CV (`:507-510`)</li><li>GVI, PGS (`:543-614`)</li><li>mean hourly change, out-of-range RMS (`:551-592`)</li><li>runs on a gap-interpolated, de-spiked series (`:281-359`)</li><li>CGP pentagon (`:217`)</li></ul> | range | **Partly.** Bands, band medians, RMS and eA1c can be exact from a 1 mg/dL histogram. GVI, mean hourly change and the t1/t2 rate counts are additive per day if the row stores the per-day path sums, with one approximation at the midnight step. The hour-of-day filter needs per-hour histograms or a trace. The interpolation pass needs a trace. |
| **CGP pentagon** (`lib/report/pentagon.js`) | sgv, time-weighted per source | <ul><li>time out of range, CV, mean</li><li>per-day low AUC, low time, high AUC, high time</li><li>a 70% coverage gate (`:8-12`, `:66-79`, `:137-150`)</li></ul> | range | **No.** It already reduces each day to {minutes, Σbg·t, Σbg²·t, outside, lowAuc, lowTime, highAuc, highTime} and merges days (`:140-148`). This is the template for the summary row. |
| **hourlystats** | sgv pivoted by hour of day (`hourlystats.js:102`) | per hour across days: p10/25/50/75/90, SD, min, max, n (`:123-128`) | range | **Partly.** Exact from per-day × per-hour 1 mg/dL histograms; close from a 5-minute grid. |
| **percentile** | sgv | p10/25/50/75/90 in 30-minute bins (`percentile.js:53`, `:84`) | range | **Partly**, same as hourlystats. |
| **success** | sgv | rolling 7-day periods back from *now*, not calendar-aligned: mean, quartiles, SD, % low/in/high by user target (`success.js:63-142`) | range | **Partly.** Calendar-day-aligned weeks would be exact from day histograms; the now-anchored window is not. |
| **weektoweek** | sgv per day, overlaid by weekday | traces only | range | **Yes.** It is a plot of readings; a 5-minute grid would be a lossy substitute. |
| **daytoday** | sgv, mbg, treatments (insulin, carbs, protein, fat, temp basal, combo bolus, profile switch, notes), profile, optionally devicestatus (IOB, COB, predictions) | <ul><li>per-day plot</li><li>per day: basal = scheduled + positive temps + negative temps, bolus, TDD, carbs, protein, fat (`daytoday.js:1006-1012`)</li><li>average TDD and basal % over days (`:107-125`, `:1017-1021`)</li></ul> | range | **Yes** for the charts. **No** for the daily totals, which are per-day sums. |
| **loopalyzer** | sgv, treatments, profile basal and temp basals, devicestatus IOB/COB, 5-minute slots (`loopalyzer.js:151-217`, `:242-368`) | <ul><li>mean curves by 5-minute slot across days</li><li>meal "time shift" alignment on carb times (`:1032-1089`)</li></ul> | range; the help text advises one day at a time | **Yes.** It needs per-day 5-minute series of SGV, basal, IOB and COB, plus carb timestamps. A per-day 5-minute grid for each series would be enough. |
| **treatments** | treatments, editable (`treatments.js:28-75`) | listing and edit | range | **Yes.** It works on documents. |
| **calibrations** | entries cal and mbg, filtered/unfiltered raw (`calibrations.js:37-58`) | scatter of calibrations | range | **Yes.** Small volume. |
| **profiles** | profile documents | display | n/a | **Yes**, but profiles are tiny. |

Server side, cgm-remote-monitor has no report or statistics endpoint. The only aggregation is the API v1 entries
`aggregate` pass-through (`lib/api/entries/index.js:515`) [R]. Every report above is computed in the browser
from raw API reads.

## 3. nightscout-reporter (518d61f) [R]

**Loading:**
- Day by day, from (start − 1 d) to end (`lib/src/start_component.dart:1200-1344`), calling:
  - `entries.json?find[date]…&count=100000` (`:1213`)
  - `treatments.json?…&count=100000` (`:1257`)
  - `devicestatus.json` (`:1306`), which is parsed but read by no form; IOB and COB are recomputed from
    treatments (`json_data.dart:1409`, `:2287`)
  - `activity.json` (`:1319`)
- Once per report: `status.json`; `profile.json?count=<up to 100000>` with no date filter (`:1006`); and Profile
  Switch treatments since 1 January of the previous year (`:1051-1057`).

**Range:**
- Presets run up to "last 3 months" (`globals.dart:352-402`). **I found no maximum number of days.**
- Comparison periods are the same window shifted 1, 3, 6 or 12 months back (`globals.dart:1155-1160`).

**Resampling:**
- Every statistic runs on a **5-minute interpolated grid**, with gaps of 16 minutes or more flagged
  (`start_component.dart:1357-1408`).
- Counts and percentages are therefore over grid points.

| form | statistics | needs detail? |
|---|---|---|
| analysis (`print-analysis.dart`) | <ul><li>readings/day; days per site, reservoir and sensor change</li><li>TIR (target or 54/70/180/250)</li><li>hypo episodes below 54, separated by more than 30 min (`:670-680`)</li><li>min, max, SD, GVI, PGS, mean, eA1c via 46.7/28.7 (`base-print.dart:475`); GMI is not present</li><li>carbs/day, TDD, basal/bolus %</li></ul> | **No** with counts, sums, a histogram, GVI path sums and an episode count (plus cross-midnight carry). The period **median** (`json_data.dart:2458`) needs the histogram. |
| percentile/AGP (`print-percentile.dart`) | <ul><li>p10/25/50/75/90 at every distinct hh:mm (about 288 bins, `:612-628`), linear interpolation (`globals.dart:1798-1820`)</li><li>a 24-row hourly table with mean, SD and insulin (`:415-495`)</li></ul> | **Partly.** A 5-minute grid row reproduces this exactly, because the grid is the tool's own input (up to rounding). |
| daily statistics (`print-daily-statistics.dart`) | <ul><li>per day: low/in/high, count, min, max, mean, SD, CV, P25/50/75, HbA1c, basal, bolus, TDD</li><li>a total row that pools all readings (`:485-516`)</li></ul> | **No** with day histograms. |
| CGP (`print-cgp.dart:583-745`) | per-day AUC of the grid points at or beyond the limits, averaged over days; PGR | **No.** These are per-day sums. |
| glucose distribution (`print-gluc-distribution.dart:89-131`) | histogram with a 5–50 mg/dL step | **No.** |
| daily hours (`print-daily-hours.dart:110`) | hourly mean per day | **No** with 24 per-hour Σ and n. |
| daily graphic, daily analysis, daily profile, daily trend, daily log, weekly graphic, profile, basal rate | curves, itemised treatments, profile contents | **Yes**, per-day traces and treatments. A 5-minute grid serves the glucose part; the treatment list is needed for logs. |

## 4. Other ecosystem projects [R]

- **AndroidAPS:**
  - TDD by local-midnight day (`implementation/.../stats/TddCalculatorImpl.kt:81-198`) is **persisted** as
    `TotalDailyDose` (basal, bolus, total, carbs, carbInsulin, utcOffset:
    `database/impl/.../entities/TotalDailyDose.kt:34-40`, written at `TddCalculatorImpl.kt:129`).
  - TIR counts per day, with readings under 39 counted as errors (`TirCalculatorImpl.kt:84-102`).
  - A Dexcom-style 14-day, 5-band TIR with a night-time 70–120 variant, plus mean and SD
    (`DexcomTirImpl.kt:25-29`, `:110-161`).
  - The stats screen shows 7- and 28/30-day spans (`ui/.../StatsViewModel.kt:183-316`).
  - The algorithm reads 1-day and 7-day TDD (`OpenAPSSMBPlugin.kt:253-254`).
- **Trio:**
  - GMI, eA1c, sample SD (N−1), CV and readings/day (`Modules/Stat/.../GlucoseMetricsView.swift:103-135`).
  - Spans: day, week, month, 3 months (`StatStateModel.swift:296-345`).
  - Bands 54/63/70/140/180/250; TITR 70–140, TING 63–140 (`Models/TimeInRangeType.swift:5-31`).
  - Per-day p10..p90 (`GlucoseStatsSetup.swift:95-113`).
  - TDD is **persisted** per loop as `TDDStored` (total, bolus, tempBasal, scheduledBasal;
    `TDDStored+CoreDataProperties.swift:9-15`) and read back for 3 months (`TDDSetup.swift:89-91`).
- **LoopFollow** (from Nightscout, nothing persisted):
  - Default 14 days, presets 14/30/90 (`Stats/StatsDataService.swift:15-16`, `DateRangePicker.swift:184-190`).
  - GMI, population SD, CV; TDD rebuilt from temp basals against the profile (`SimpleStatsViewModel.swift:53-210`).
  - TIR by time of day (`TIR/TIRCalculator.swift:11-14`).
  - GRI (`GRI/GRICalculator.swift:18-61`).
  - AGP p5..p95 by hour (`AGP/AGPCalculator.swift:32-36`).
- **xDrip (Android):**
  - Spans: today, yesterday, 7/30/90 days (`stats/StatsActivity.java:48-53`).
  - Default band 70–170; mean, SD, GVI, PGS, carbs, insulin (`StatsResult.java:53-182`).
  - Median and eA1c (`FirstPageFragment.java:164-198`); q10..q90 chart (`PercentileView.java:110`).
  - Nothing persisted.
- **xdripswift:**
  - Report spans 7/30/60/90/180/**365** days (`Reports/ReportModels.swift:12-18`), with a 70% coverage gate
    (`StatisticsManager.swift:185`).
  - It has a per-day summary *struct*, not persisted: date, mean, target/low/high %, sampleCount
    (`ReportModels.swift:431-438`).
  - TDD comes from devicestatus published by AID apps (`StatisticsManager.swift:705-817`).
- **nightguard:** last 8 h, last 24 h, today and yesterday only; mean, eA1c, SD, CV, bands
  (`domain/BasicStats.swift:17-208`).
- **Nocturne** (server-side, computed per request):
  - `StatisticsService.cs` computes GMI, GRI, p5..p95, MAGE, ADRR, J-index, LBGI/HBGI, PGS, TIR and
    personal-range TIR, with a ≥70% coverage check and a 14-day clinical minimum
    (`Core/Nocturne.Core.Clinical/Statistics/StatisticsService.cs:153-1468`, `:529-643`).
  - Period windows of 1/3/7/30/90 days, period comparison, weekday and hourly patterns
    (`API/.../V4/Analytics/StatisticsController.cs:367-693`).
  - A **year overview** with a `DailySummaryDay` (mean, bolus, basal, TDD, carbs, TIR %, count:
    `DataOverviewModels.cs:145-175`), computed from raw tables per request (`DataOverviewService.cs:228-300`).
    No materialised summary table was found.
- **nighttroop** (closest prior art; **persisted**):
  - The `summary_period` table, keyed (period ∈ day/week/fortnight/month, date)
    (`data/sql/sitedb/migrations/000001_init_schema.up.sql:592`). Columns:
    - timezone; TIR; TDD; basal; carbs
    - **a 288-slot glucose JSON array**; AGP JSON
    - reading counts; cgm_slots; mean; SD
    - very-low, low, high and very-high times
    - 5-minute IOB and COB series
    - `stale_at`
  - Daily build: newest reading per 5-minute slot, very-low/very-high bounds 54/250
    (`models/sitemodels/summary_daily.go:16-120`).
  - AGP p5..p95 per 15 minutes, using the 7 days up to the day (`summary_daily.go:32`).
  - Week and month rows are means of days (`summary_period.go:12-44`).
  - Raw writes mark days stale; a background job rebuilds them after 2–15 min of quiet and on a time-zone
    change (`background/summary_daily/job.go:53-304`).
- **GlycemicGPT:**
  - AGP p10..p90 over 7–90 days, default 14 (`apps/api/src/routers/integrations.py:4128-4135`).
  - Insulin summary, default 14 days (`:4229`); raw history capped at 30 days (`:990`).
  - A persisted `daily_briefs` row: TIR %, mean, low/high/readings counts, total insulin
    (`models/daily_brief.py:41-112`).
- **nightscout-cgm-skill:** a local SQLite table of SGVs only; 90-day default analysis with mean, SD, CV, GMI,
  5 bands and p5..p95 (`scripts/cgm.py:395-406`, `:555-619`, `:5600-5619`).

**Spans in practice [R]:**
- Users pick 1/7/14/30/90 days nearly everywhere.
- cgm-remote-monitor caps at 186 days; xdripswift offers 365; nightscout-reporter has no cap and offers
  comparison windows up to 12 months back.
- Persisted daily aggregates exist in AAPS (insulin), Trio (insulin), nighttroop (everything) and GlycemicGPT
  (one brief per period).

## 5. Proposed per-tenant-day summary row

The design rests on three rules:
- **Mergeable fields only:** counts, sums, sums of squares, fixed-bin histograms, and per-day extrema used as
  per-day series. A day range then merges by addition.
- **Keyed by** (tenant, local_date, tz_id). The day is computed in the profile zone with DST, as in
  `agp-data.js:5-10`, and rebuilt when the zone changes (nighttroop `job.go:96`).
- **Built from the same deduplication as the reports** (`uniqsgv.js`, one SGV per minute, values 39–600), so a
  summary and a detail read agree.

| group | fields | approx. bytes |
|---|---|---|
| key and meta | tenant, local_date, tz_id, utc_offset_min, schema_version, built_at, source_srvModified_max, stale flag | 40 |
| coverage | n_sgv, observed_minutes (time-weighted, intervals capped at 5 min, `agp-data.js:31-35`), n_mbg, n_cal, n_invalid (<39 or >600) | 20 |
| glucose moments | Σbg and Σbg² by count; Σbg·t and Σbg²·t by time (`pentagon.js:66-79`); min, max | 40 |
| **glucose histogram** | counts per **1 mg/dL** bin over 39–400, plus under/over; sparse or varint-encoded | ~150–300 compressed (724 raw as uint16) |
| standard bands by time | minutes below 54, 54–69, 70–180, 181–250, above 250, 70–140, 63–140 | 28 |
| CGP / AUC | lowAuc, lowTime, highAuc, highTime (`pentagon.js:69-71`) | 16 |
| path / variability | per-day GVI path length and ideal time, Σ\|Δbg\|, n steps, t1/t2 rate counts, first and last (bg, t) (`glucosedistribution.js:543-600`); max low-risk and max high-risk for ADRR | 48 |
| episodes | count of hypo episodes below 54 and below 70, plus an episode-open-at-midnight flag | 6 |
| **5-minute trace** | 288 × uint16 slot values (newest or mean per slot, 0 for empty), as in nighttroop and loopalyzer slots | ~350 compressed (576 raw) |
| per-hour glucose | 24 × (n, Σ) | 192 raw, ~100 compressed |
| insulin and food | bolus_u, smb_u, basal_scheduled_u, basal_delivered_u (+temp, −temp), carbs_g, protein_g, fat_g, carb_insulin_u (AAPS); counts of boluses, carb entries, temp basals; site, sensor and insulin change counts | 60 |
| per-hour insulin and carbs | 24 × (bolus_u, basal_u, carbs_g) | ~150 compressed |
| optional loop series | 288-slot IOB and COB (nighttroop `loop_iob`/`loop_cob`), int16 at 0.01 U / 1 g | ~700 compressed |

**Size [R, estimated, not measured]:**
- About **1.0–1.3 KB** per tenant-day without the loop series and about 2 KB with it, roughly 1–2% of the
  ~0.13 MB per tenant-day cold-bundle figure in proposal §5.4.
- A year is about 0.4–0.7 MB per tenant.
- Dropping the trace and per-hour arrays leaves a scalar-plus-histogram core of about 0.4 KB.

### 5.1 Exact from the row (merge by addition) [R]
- **Coverage and count statistics:** readings/day, % CGM active, 14-day/70% sufficiency (time-weighted).
- **Moments and indices:**
  - mean, SD and CV over any day range, count- or time-weighted, from n, Σ and Σ²
  - GMI and eA1c from the mean
  - J-index from the mean and SD
- **Bands:**
  - all standard bands
  - **any user target band** (cgm-remote-monitor's per-request `rp_targetlow/high`; reporter's per-day
    targets) from the 1 mg/dL histogram
  - GRI from the band fractions
- **Pooled distribution statistics:** pooled median and quartiles, band medians, the glucose distribution
  histogram, out-of-range RMS against any target, LBGI/HBGI. All are exact because SGV is an integer in mg/dL, so
  the histogram is lossless for the pooled multiset. In display mmol the same holds after the existing
  conversion.
- **Per-day aggregates:**
  - CGP pentagon exactly as `pentagon.js` computes it
  - ADRR (a mean of per-day maxima)
  - TDD with basal/bolus split, carbs/protein/fat per day and averages
  - hourly means (reporter's daily hours)
  - daytoday's distribution totals
  - AAPS- and Trio-style TDD history
- **Calendar-aligned period rollups**, such as week and month rows and comparison periods 1–12 months back.

### 5.2 Approximate from the row [R]

| statistic | from what | fidelity |
|---|---|---|
| AGP and time-of-day percentiles across days (agp 15 min, percentile 30 min, hourlystats 1 h, reporter ~288 bins, Trio/LoopFollow/GlycemicGPT) | the **5-minute trace** | <ul><li>exact for reporter, whose input is already a 5-minute grid</li><li>close for cgm-remote-monitor, whose 15- and 30-minute bins would hold 3–6 grid values per day instead of 3–15 raw readings</li><li>diverges for 1-minute sensors</li></ul> |
| **Daily percentiles** | — | non-mergeable; storing p5..p95 per day does **not** give multi-day percentiles |
| **Exact multi-day AGP** | a per-day × per-time-bin 1 mg/dL histogram: 96 × sparse ≈ 1–2 KB/day | is the alternative if exactness matters more than size |
| GVI, PGS, mean hourly change | per-day path sums | exact except the single midnight step between days, recoverable from first/last (bg, t) |
| MAGE, MODD, CONGA | the trace | approximate; no cgm-remote-monitor or reporter report computes them (Nocturne does) |
| Hypo episode counts across days | episode counts plus the midnight-carry flag | nearly exact |
| cgm-remote-monitor **success** report | calendar-day histograms | exact only if its rolling, now-anchored 7-day windows are aligned to local days |

### 5.3 Not reproducible from daily aggregates: detail needed [R]

**Reports that need detail:**
- Day-by-day charts:
  - cgm-remote-monitor: daytoday, weektoweek, the 28-day AGP mini-grid
  - reporter: daily graphic and daily analysis
  - The trace gives a 5-minute rendition, but not the raw points, mbg markers or the de-spiking
    interpolation (`glucosedistribution.js:281-359`).
- **loopalyzer meal time-shift.** It needs carb timestamps and the IOB/COB series. The optional loop series plus
  treatment detail cover it.
- **Treatment lists and edits:** cgm-remote-monitor treatments, reporter daily log, and food/notes/eventType
  searches (`reportclient.js:342-417`). These are documents.
- **calibrations.** It needs raw filtered/unfiltered and cal entries.
- Predictions and OpenAPS overlays read from devicestatus (`loopalyzer.js:466-473`, daytoday options).
- Audit and v1/v3 reads of individual documents.

**Implication for tiers [R, not measured]:**
- Glucose statistics over long spans can be served from summary rows at any age.
- Charts and lists need detail for the days displayed. Users ask for those at 1–14 days, and occasionally up to
  the 90–186-day range caps; that is the hot and warm tiers, with cold reads acceptable at seconds.
- Treatments are small next to entries and devicestatus and back several "need detail" reports, so treatment
  detail is a candidate for longer retention than entries/devicestatus detail. This is unmeasured; confirm with
  per-collection bytes.

### 5.4 Design cautions [R]

- **Thresholds differ across tools:**
  - cgm-remote-monitor `dailystats`: low `<low`, high `>=high` (`dailystats.js:110-115`)
  - cgm-remote-monitor `agp`: 70–180 inclusive (`agp.js:130`)
  - AAPS: ≥39 and inclusive bounds (`TirCalculatorImpl.kt:84-102`)
  - A 1 mg/dL histogram serves all of them. Precomputed band columns serve only the convention used to build
    them.
- **Weighting differs:** count-weighted (cgm-remote-monitor bands, AAPS) versus time-weighted
  (`pentagon.js`, % active). Keep both moment sets.
- **SD differs:** population SD (cgm-remote-monitor, reporter, LoopFollow) versus sample SD with N−1 (Trio).
  Both follow from n, Σ and Σ².
- **Rows go stale.** Backfill and edits must mark days stale and rebuild them, as nighttroop does with
  `stale_at` (`job.go:210-212`). A cold-tier edit that promotes a document to hot (proposal §5.4) must also mark
  its day stale.
- **Built from detail only.** Summary rows must be produced from detail before any detail-deletion limit takes
  effect. Once detail is gone, a rebuild (new statistic, bug fix) is impossible. `schema_version` records which
  fields a row carries.
