# The Nightscout ecosystem: what it consists of, what depends on it, and what keeping it current takes

*For the Nightscout Foundation board, the maintainers of the ecosystem projects, and the community.
**Observations** (part 1 of the overview; [how the overview is organised](../README.md)). Living
page, assembled 2026-10-02 against this repository at `e3d7b65c`. It describes; it recommends
nothing. Each section names the date and the source or command of its figures; where a figure
lives in a generated table or a record, this page links to that one home instead of copying it.
Re-measure before quoting.*

## 1. What the ecosystem consists of

The [stack census of 2026-09-30](../../60-research/programme/stack-census-2026-09-30.md) listed 63
repositories (62 distinct; one fork is kept level with its upstream), from device drivers to
vendor-cloud connectors, servers, followers and reports:

- 56 of the 62 had commits in the last year, by 219 distinct human authors.
- 13 of the 63 listings are held under personal GitHub accounts; most of the rest sit in GitHub
  organisations run by volunteers.
- 14 device protocols have 41 independent implementations; for 10 of them no two implementations
  test against the same bytes.
- Six code bases log in to Dexcom Share and five to LibreLinkUp.
- There are more than 35,000 test declarations across the stack. CI runs tests in 14 of the 62
  repositories, and no device or connector repository publishes a per-release test report.
- In 25 of the 56 repositories with human commits in the year, one author made 80% or more of them.
  This describes where the knowledge sits, not the quality of the work.

Per-layer and per-repository figures, and the method, are in the census record.

## 2. What depends on the shared server

**Client apps.** Nightscout is a secondary display for CGM and pump data, and it is also where many
other apps read and write that data. The 15.0.9 client survey mapped 40 client repositories against
15 parts of the API ([consumer impact](../../60-research/remedial/consumer-impact-15.0.9-2026-09-23.md)).
Loop, Trio, AndroidAPS, xDrip+, caregiver apps, watch faces and reporting tools rely on how the
server behaves.

**A second server.** Nocturne ([`nightscout/nocturne`](https://github.com/nightscout/nocturne)) is
a second implementation of the API, in .NET with PostgreSQL, with its own web interface and visual
language. xDrip+ ships an uploader for it
([adoption roadmap](../../30-design/nightscout-adoption-roadmap-2026-09-11.md)). Its typed event
model is used as a reference in this repository's data-model work
([primitive coverage](../../30-design/platform/nightscout-primitive-coverage-2026-09-11.md)). On
2026-09-23 Nocturne (`42275c81`, v0.2.x) matched the 15.0.9 candidate on the count and filter fixes
and differed on eight measured behaviours; its parity suite runs against Nightscout 15.0.3
([consumer impact §6](../../60-research/remedial/consumer-impact-15.0.9-2026-09-23.md#6-nocturne-parity)).

**Existing sites.** Operators run cgm-remote-monitor on MongoDB, with their own settings, data and
hosting. A move to another server is a migration each operator chooses.

## 3. Releases and contributors across the main projects

Tag dates in cgm-remote-monitor (`git tag --sort=creatordate`):

| release | tagged | days since the previous release |
|---|---|---:|
| 14.2.6 | 2022-09-30 | 295 |
| 15.0.0 | 2023-10-18 | 383 |
| 15.0.2 | 2023-10-25 | 5 |
| 15.0.3 | 2025-05-08 | 561 |
| 15.0.4 | 2026-02-28 | 296 |
| 15.0.7 | 2026-04-29 | 57 (15.0.5 and 15.0.6 in between) |
| 15.0.8 | 2026-09-04 | 128 |
| 15.0.9 | candidate `dev` `ca6fcfaf` (2026-10-02), not tagged; [how it was made](../../../releases/cgm-remote-monitor-15.0.9/colophon.md) | — |

Longest gaps between stable GitHub releases in the main projects
(`gh api repos/<owner>/<repo>/releases`, measured 2026-09-29):

| project | longest gaps between stable releases | recent releases |
|---|---|---|
| cgm-remote-monitor | 383 days (2022–23), 561 (2023–25), 296 (2025–26), from the tag table above | 5 in 2026 |
| AndroidAPS | 443 days (Aug 2022–Oct 2023), 306 (Feb–Dec 2024) | 6 in 2025, 8 in 2026 |
| Loop | 323 days (2020–21), 284 (2022–23), 297 (2023–24) | 15 since April 2025, now published from LoopWorkspace |
| Trio | 255 days (Aug 2025–Apr 2026) | 8 in 2026, including 1.0 |
| xDrip+ | 422 days (2019–20), 234 (2024–25) | pre-release builds at least every 45 days since 2016 |
| oref0 | 951 days (2019–22); none since v0.7.1 in June 2022 | its algorithm is now maintained inside AndroidAPS and Trio |

Commits / distinct author emails per year (all branches, merge commits and bots excluded, from this
workspace's clones fetched 2026-09-09 to 2026-09-23, so 2026 is partial; Loop is the Loop app plus
LoopKit; Trio is left out because its history before 2024 is FreeAPS X's):

| project | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cgm-remote-monitor | 440/49 | 310/47 | 193/34 | 220/18 | 67/14 | 169/16 | 50/11 | 115/13 | 1050/27 |
| AndroidAPS | 1993/50 | 1465/42 | 1653/42 | 2041/32 | 1531/34 | 1563/36 | 566/24 | 916/33 | 2944/28 |
| Loop + LoopKit | 114/6 | 275/16 | 757/21 | 327/8 | 360/25 | 516/25 | 425/12 | 442/17 | 324/13 |
| xDrip+ | 1217/28 | 832/18 | 402/17 | 791/23 | 832/17 | 640/16 | 480/13 | 408/19 | 521/16 |

What the tables show, and what they do not:

- In cgm-remote-monitor the number of people committing fell first, from 47 in 2019 to 18 in 2021
  and 11 in 2024; the years of one release a year followed. AndroidAPS's lowest year, 2024, is also
  the year of its 306-day gap. Loop's commits held steady through its gaps. The 2026
  cgm-remote-monitor figure includes agent-written commits (§4).
- Every main project has had gaps of similar length in the same years, and most released more often
  in 2025–26.
- **Dates do not show causes.** Several gaps coincide with large rewrites and with Apple and Google
  platform changes. xDrip+ could not be built with current Android tools from September 2019 to
  December 2020 ([#1012](https://github.com/NightscoutFoundation/xDrip/issues/1012)), because of
  toolchain changes the project did not control. Each project's maintainers are the people to say
  what held their releases.

**A long-running change.** The MongoDB 5 driver upgrade was first proposed in #7344, opened
2022-02-16. The upgrade that shipped was #8421: opened 2026-01-19, merged 2026-03-16, released in
15.0.7 on 2026-04-29 (`mongodb` `^3.6.0` → `^5.9.2`). #7344 was closed as superseded on 2026-05-01.
Hosting providers retire old database versions on their own schedule.

## 4. Where the maintenance time goes today

Much of the cgm-remote-monitor engineering in 2026 was done with AI coding agents under a
maintainer's direction. The steps that still need a person:

| work that needs a person | where it is measured |
|---|---|
| review | the generated reviewer-load table on [PROGRAMME-STATUS](../PROGRAMME-STATUS.md#the-two-constraints-neither-of-them-engineering): how many queue items route review to the maintainer, and how many to a SECURITY or SAFETY reviewer, a kind of reviewer to which most items name no individual |
| decisions | [NEEDS-A-HUMAN](../NEEDS-A-HUMAN.md), plus the release decisions themselves |
| hand checks and real-system checks | the checks owed before the 15.0.9 tag ([contents](../../../releases/cgm-remote-monitor-15.0.9/contents.md#open-items-a-releaser-must-settle)); on 2026-09-27 no real Loop, Trio, AndroidAPS or xDrip+ setup had yet run against the candidate |
| dependency alerts | measured on `dev` `7000eb18` (2026-09-27): 80 Dependabot alerts open against `master`, the last release, 74 of them already fixed on `dev` and closing only when a release ships; each remaining finding needs a person to establish whether Nightscout reaches it ([triage](../../../releases/cgm-remote-monitor-15.0.9/contents.md#npm-audit-and-dependabot-triage)) |
| backlog | 35 open pull requests (18 opened in 2026, the oldest in 2021) and 102 open issues in cgm-remote-monitor (`gh pr list`, `gh issue list`, 2026-09-27) |
| the 15.0.9 release itself | [how 15.0.9 was made](../../../releases/cgm-remote-monitor-15.0.9/colophon.md): merges, commits, tests, defect arrival and process controls, measured on `ca6fcfaf` |

**Who pays for this time.** Some of the people doing this work are paid for part of their time by
the commercial hosts they work for, on terms each host sets; those arrangements differ in scope,
availability and the compliance obligations each host carries. No organisation pays for maintenance
as shared ecosystem work, on published terms, with a public report.

## 5. Work that arrives on other organisations' calendars

Dates from each vendor's own pages, read 2026-09-29; "announced" means the vendor gives a month or
year, not a day.

| date | event | who it reaches |
|---|---|---|
| 2026-10-05 to 11-02 | GitHub's macos-14 runner image has brownouts, then is removed ([runner-images #13518](https://github.com/actions/runner-images/issues/13518)) | Loop, Trio, LoopFollow, LoopCaregiver browser builds still pinned to it |
| 2026-10-28 | Node 26 becomes Active LTS; Node 24 entered maintenance on 10-20 ([Node release schedule](https://github.com/nodejs/Release)) | cgm-remote-monitor, nightscout-connect |
| 2026-11-10 / 11-12 | .NET 8 and 9 end of support ([policy](https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core)); PostgreSQL 14 end of life ([versioning](https://www.postgresql.org/support/versioning/)) | Nocturne and its operators |
| early 2027 (announced) | existing Health & Fitness or Medical apps in the EEA, UK and US must declare a regulated-medical-device status in App Store Connect, or "you'll no longer be able to submit app updates" ([Apple, 2026-03-26](https://developer.apple.com/news/?id=nyqbfz1y)) | every person who builds Loop, Trio or a follower app under their own App Store Connect record, if the app meets Apple's criteria |
| 2027 (announced) | Android developer verification expands "to the rest of the world and to all installations"; ADB installs are exempt; every self-built AndroidAPS shares one package name with a different key, which Google says needs additional review ([AndroidAPS docs](https://androidaps.readthedocs.io/en/latest/SettingUpAaps/AndroidDeveloperVerification.html), [Android](https://developer.android.com/developer-verification/guides)) | every AndroidAPS and xDrip+ builder, and sideloaded companion apps |
| April 2027 (announced) | uploads to App Store Connect, TestFlight included, need the iOS 27 SDK / Xcode 27 ([Apple](https://developer.apple.com/news/?id=k1mtkt1k)) | every iOS app builder; builds expire after 90 days, so a missed migration stops the app, not just updates |
| 2027-04-30 | Node 22 end of life, and the Heroku-22 stack end of life the same day: running apps keep running, but deploys are blocked until the stack is upgraded ([Heroku](https://devcenter.heroku.com/articles/heroku-22-stack)) | Nightscout sites on Heroku or on Node 22 |
| August 2027 (announced) | GitHub removes Intel macOS runners ([runner-images #13045](https://github.com/actions/runner-images/issues/13045)) | iOS build workflows pinned to Intel |
| 2027-08-31 | MongoDB 7.0 end of life; Atlas upgrades clusters automatically after notice ([lifecycles](https://www.mongodb.com/legal/support-policy/lifecycles)) | Nightscout sites on Atlas M10+ or self-hosted 7.0 |
| about September 2027 (estimated from cadence) | iOS 28 | iOS apps; each new iOS has historically needed an app release |
| no date | vendor cloud changes (below) | every server's connectors |

**Vendor-cloud changes the connectors had to follow**, from the connectors' commit histories and
issue trackers. When a vendor changes its service, glucose data stops arriving at the site until a
fix ships.

| vendor | change the connector had to follow | where |
|---|---|---|
| Abbott LibreLinkUp | version header raised to 4.7.0, June 2023 | nightscout-librelink-up |
| Abbott LibreLinkUp | requests blocked by Cloudflare from late March 2024; fixed 2024-04-02 ([#128](https://github.com/timoschlueter/nightscout-librelink-up/issues/128), 39 comments) | nightscout-librelink-up |
| Abbott LibreLinkUp | version header raised to 4.12.0, November 2024; China region added, March 2025 | nightscout-librelink-up |
| Abbott LibreLinkUp | "October 2025 changes", 2025-10-21 (`f52d929`) | nightscout-connect |
| Abbott LibreLinkUp | new response shape and login handling, 2026-09-22 (`370d9f4`) | nightscout-connect |
| Medtronic CareLink | OAuth and token-refresh changes, December 2020; care-partner login error 400, June 2023 | minimed-connect-to-nightscout, now deprecated |
| Dexcom Share | trend field changed from a number to a string, November 2021 | share2nightscout-bridge, now deprecated in favour of nightscout-connect |

Nocturne carries its own connectors for the same vendors (Dexcom, FreeStyle for LibreLinkUp,
CareLink, and others; `externals/nocturne/src/Connectors` at `42275c81`) and pins the same
LibreLinkUp version header, 4.16.0.

## 6. Published clinical evidence for open-source AID

Abstracts read on PubMed, 2026-09-30. A clinician or clinical researcher should check this summary
before it is relied on.

| study | design | what it found | caveats the authors state or the design implies |
|---|---|---|---|
| CREATE ([Burnside et al., NEJM 2022;387:869–881](https://www.nejm.org/doi/full/10.1056/NEJMoa2203913)) | randomised controlled trial, 97 children and adults, 24 weeks; AndroidAPS 2.8 with the OpenAPS 0.7.0 algorithm against a sensor-augmented pump | time in range rose from 61.2% to 71.2% with AID and fell from 57.7% to 54.5% in the control group (adjusted difference 14 percentage points, 95% CI 9.2–18.8); no severe hypoglycaemia or DKA in either group | the comparator was a pump without automation, not a commercial AID system; two AID participants withdrew because of connectivity issues |
| Loop observational study ([Lum et al., Diabetes Technol Ther 2021;23:367–375](https://pubmed.ncbi.nlm.nih.gov/33226840/)) | prospective, real-world, 558 adults and children, 6 months | time in range rose from 67% to 73%; time below 54 mg/dL fell slightly | people who chose to start Loop themselves; no control group |
| Canadian comparison ([Wu et al., Diabetes Technol Ther 2025;27:517–526](https://pubmed.ncbi.nlm.nih.gov/40100927/)) | prospective, observational non-inferiority study, 26 open-source and 52 commercial AID users, 12 weeks | open-source non-inferior on 24-hour time in range (78.3% against 71.2%) | open-source users spent more time below 3.9 mmol/L (3.9% against 1.8%, "yet within the recommended range"); not randomised |
| Systematic review ([Knoll et al., Diabet Med 2022;39:e14741](https://pubmed.ncbi.nlm.nih.gov/34773301/)) | 21 real-world studies, 2018–2021 | improvements "observed in open-source and commercially developed AID systems alike" | real-world studies; most were of one commercial system |

Open-source AID improved time in range over pump therapy in one randomised trial. In real-world
comparisons it matched or exceeded commercial systems on time in range, with differences in time
below range. No randomised head-to-head trial against commercial AID systems is among the studies
read here. The people in the real-world studies chose these systems themselves; the authors of one
comparison describe them as "a very selected group of people"
([Journal of Diabetes Science and Technology, 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11571566/)).
Which system does better, for whom and in which circumstances is a question these studies do not
answer.

## 7. Limits of this page

- The release and contributor tables are from 2026-09-29 and the clones named; author counts are by
  email, so one person under two addresses counts twice.
- The maintenance-time rows dated 2026-09-27 are a snapshot; the generated tables they link to are
  current.
- Vendor dates marked "announced" or "estimated" will move.
- Nothing here measures user numbers, installations or outcomes beyond the studies cited.
