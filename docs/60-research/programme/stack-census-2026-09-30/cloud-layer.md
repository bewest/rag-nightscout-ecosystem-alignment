# The cloud layer: connectors, documented routes, and what quality control would need

*Contributor-facing. Annex to the [stack census record of 2026-09-30](../stack-census-2026-09-30.md); a snapshot, not rewritten as the world moves. Prepared by research agents from the clones and pages named in it, and checked by the session that wrote the record.*

*Research note for the Nightscout Foundation, 2026-09-30. Draft; the legal and regulatory
items in §2.2 are for review by counsel and a regulatory professional before anything relies
on them, and the effort figures in §4 are estimates. Every external fact carries its URL and
was read on 2026-09-30. Commit shas are short shas from the clones under
`externals/stack/`. This note does not repeat the vendor-change table in the sponsored-team
proposal §6a, the vendor calendar in COLLABORATION-MODEL §3, `docs/DIGITAL-RIGHTS.md` or
`docs/state-of-diabetes-2026.md` Part III; it adds to them. The `mapping/` entries for
nightscout-connect, nightscout-librelink-up, share2nightscout-bridge, tconnectsync and
nocturne date from 2026-01-29 and list eight Nocturne connectors; the current tree has
fourteen (§1.1).*

*Scope of "data sovereignty" here: the data holder (the person with diabetes or their
caregiver) being able to get their data out of vendor clouds, in a form they can compute on,
and to hand that job to tools and helpers they choose. The five rights used in §4 are the
ones in `docs/state-of-diabetes-2026.md` Part III: access, export, share, delegate, audit.*

## 1. Cloud connectors in the corpus

Clones under `externals/stack/<owner>__<repo>`, fetched for the stack census
(`tools/programme/stack-census/repos.tsv`), read 2026-09-30. Commit and author figures are in the census table
(`tools/programme/stack-census/results/census-2026-09-30.md`), not here. Test counts are `test(`/`it(`, `def test_`,
`func test`, `@Test`, `[Fact]`/`[Theory]` or Ginkgo `It(` occurrences, so they count cases as
written, not parameterised expansions. "Official" and "unofficial" are what each project says
about itself; where it says nothing, the entry says so.

### 1.1 Per connector

| connector (HEAD) | vendor clouds reached | API status as the project states it | tests | CI |
|---|---|---|---|---|
| nightscout/nightscout-connect (`4dde1ecd` main = v0.1.0, 2026-09-24; dev `04102f9` starts 0.1.1) | LibreLinkUp (`lib/sources/librelinkup.js`), Dexcom Share (`dexcomshare.js`), Glooko (`lib/sources/glooko/`), Medtronic CareLink (`lib/sources/minimedcarelink/`, README roadmap strikes "Medtronic" through), Nightscout-to-Nightscout | Glooko: "not an official supported Glooko API contract" (`docs/glooko-sync.md`); no statement for the others | 34 files in `test/`, 258 cases; synthetic responses written in the tests, one JSON fixture (`test/fixtures/nightscout-full-sync.json`); a LibreLinkUp lab (`scripts/librelinkup-lab/fixture.js`) replaces the vendor transport with a synthetic one; live probes (`scripts/glooko-live-probe.js`, LibreLinkUp regional lab) refuse to run without an explicit flag and are not in CI (`test/glooko-live-probe.test.js`) | GitHub Actions `test.yml`: Node 22 and 24, LibreLinkUp tests under three host time zones, and a job that builds cgm-remote-monitor at a pinned commit and runs the synthetic source against real Nightscout storage |
| timoschlueter/nightscout-librelink-up (`bff2317f`, 2026-03-04) | LibreLinkUp, 13 regions listed in README (`LINK_UP_REGION`) | no statement found; README says the app-version value "may need to be updated" | 2 files, 10 cases (jest); recorded-shape JSON in `tests/data/` (login, login-failed, connections, graph, entries) | tests run inside the Docker build (`Dockerfile` "Run tests"), triggered by `docker-image.yml` |
| nightscout/share2nightscout-bridge (`518c85c4`, 2026-03-03) | Dexcom Share | none; README: "DEPRECATED ... will be archived on 2026-03-31", migrate to nightscout-connect | 3 files, 6 cases (mocha) | `wercker.yml` only; no GitHub Actions |
| nightscout/minimed-connect-to-nightscout (`57bb042c`, 2026-03-03) | Medtronic CareLink (US and EU servers) | none; README: deprecated, migrate to nightscout-connect. The cgm-remote-monitor maintainer reports that it no longer works; not measured here | 8 files, 24 cases; `_fixtures.js`/`_samples.js` hold sample payloads; `connectEu.js`/`connectUs.js` were added as live "connection test for EU and US server" (`bc1e47a`) | CircleCI `config.yml` |
| jwoglom/tconnectsync (`7c4b2f4d` = v3.0.1, 2026-07-21) | Tandem Source (US and EU; t:connect retired) | README: "querying Tandem's undocumented APIs" | 54 files, 463 cases (pytest); parser and processor tests "from real captured pump-log data" (`9d8ab28`, `cb04579`, `6f98798`); fake API and fake Nightscout (`tests/api/fake.py`, `tests/nightscout_fake.py`); EU integration tests (`4655e31`) | GitHub Actions `python-package.yml`, Python 3.8-3.11 |
| LoopKit/TidepoolService (`99ac3544`, dev, 2026-09-26) | Tidepool (upload), through TidepoolKit | Tidepool's own client library; Tidepool publishes its API (see §2) | `TidepoolServiceKitTests`, 61 cases | no CI configuration in the repository |
| LoopKit/dexcom-share-client-swift (`ff0d7143`, dev, 2026-09-26) | Dexcom Share (US, worldwide, Japan/APAC hosts) | none (no README) | 0 cases | `.travis.yml` only |
| tidepool-org/uploader (`22f53325`, develop, 2026-09-22) | none for data; reads devices over USB/BLE (`lib/drivers/`: abbott, dexcom, insulet, medtronic, medtronic600, tandem, roche and others) and parses a user-exported LibreView CSV (`lib/drivers/abbott/libreViewDriver.js`); a CareLink option is being phased out (`app/components/Upload.js`) | device protocols; export file | 30 files, 994 cases (jest) | CircleCI |
| tidepool-org/platform (`ea099262`, 2026-09-24) | Dexcom developer API through OAuth (`dexcom/`, metrics `tidepool_dexcom_api_*` in README); Abbott through a private plugin (`.gitmodules`: `private/plugin/abbott`, `update = none`; the public tree holds a stub `plugin/abbott/`); Oura partner API with webhooks (`oura/`); twiist (`twiist/`) | partner integrations (OAuth provider sessions, `oauth/`, `provider/`) | 625 `_test.go` files; `dexcom/` alone 69 files, 466 cases; generated test data (`dexcom/test/`) | `.travis.yml` |
| nightscout/nocturne (`f9c1f889`, 2026-09-30) in-tree `src/Connectors/` | Dexcom Share, LibreLinkUp (`FreeStyle`, 10 regional hosts, an app-version value in the installer), CareLink, Tandem Source, Glooko, Eversense, twiist, mylife (Ypsomed), Gluroo, MyFitnessPal, Tidepool (read), Nightscout, Home Assistant, Nocturne-to-Nocturne | Tandem: derived from tconnectsync, "which reverse-engineered" the API (`TandemConstants.cs`); twiist: "Reverse-engineered from the Twiist Insight iOS app" (`TwiistConstants.cs`); others: no statement | one xUnit project per connector; cases: CareLink 86, Dexcom 15, Eversense 23, FreeStyle 6, Glooko 222, MyFitnessPal 45, MyLife 45, Tandem 69, Tidepool 18, Twiist 26, Nightscout 106, Core 190; HTTP mocked in code, no recorded data files | GitHub Actions `tests.yml` (`dotnet test --filter "Category!=Integration"`) and CodeQL |

Followers and controllers with cloud clients in-tree:

| app (HEAD) | vendor clouds reached | tests on those clients |
|---|---|---|
| NightscoutFoundation/xDrip (`9898cb8e`, 2026-09-25) | Dexcom Share (`cgm/sharefollow`), CareLink (`cgm/carelinkfollow`), Tidepool upload (`tidepool/`), "WebFollow" (`cgm/webfollow`), a "Community script template loader" whose target service is defined by a downloaded template, not in app code; Health Connect | carelinkfollow 12, sharefollow 13, webfollow 6 (`@Test`); CI `unit_test.yml` |
| JohanDegraeve/xdripswift (`c268542e`, 2026-09-22) | LibreLinkUp, Dexcom Share (follow and upload), CareLink (follower mode added 2026-08-08, `48c9905d`), Medtrum EasyView (added 2025-12-16, `bc7f4534`); HealthKit | `CareLinkTests.swift` 107 cases; no LibreLinkUp, Dexcom Share or Medtrum tests found; CI builds only |
| gui-dos/DiaBLE (`e6a909c8`, 2026-07-30) | LibreLinkUp and LibreView (`DiaBLE/LibreLink.swift`) | none found |
| j-kaltes/Juggluco (`db70dc14`, 2026-09-30) | uploads to LibreView (`tk.glucodata.Libreview`); Health Connect (glucose only) | none found |
| loopandlearn/LoopFollow (`4a74b781`, 2026-09-20) | Dexcom Share through a vendored copy of ShareClient (`Pods/ShareClient/`) | none found for ShareClient |
| Loop and Trio | Dexcom Share and Tidepool through the loopandlearn forks of dexcom-share-client-swift and TidepoolService (Trio `.gitmodules`) | as the upstream packages |
| nightscout/AndroidAPS | Tidepool upload (`plugins/sync/.../tidepool/comm/TidepoolUploader.kt`); `medtrum.com` hits are licence headers in the pump driver, not a cloud client | — |

Outside the census but present in the workspace (`externals/`): four more Glooko clients,
lsandini/glooko2nightscout (`9ab8c608`, 2025-09-01), itconor/glooko-nightscout-eu
(`2b7fbc45`, 2026-06-25), spamsch/glooko-reader (`22837f6c`, 2026-03-30) and
nightscout/GlookoServiceKit (`8e2cad1c`, 2026-06-27). They were not examined further.

### 1.2 Independent implementations per vendor cloud

Counted as separate code bases that log in to the vendor cloud themselves. A vendored copy
(LoopFollow's ShareClient) or a fork used by Loop and Trio is not counted again. A port that
says it follows another project (Nocturne's Tandem connector, "following tconnectsync v3.0.0",
`e671a00e`) is counted but marked.

| vendor cloud | kind of access | implementations in the corpus | count |
|---|---|---|---:|
| Abbott LibreLinkUp (follower service) | unofficial | nightscout-librelink-up, nightscout-connect, xdripswift, DiaBLE, Nocturne FreeStyle; xDrip+ WebFollow possibly (template-defined) | 5 (+1) |
| Abbott LibreView | upload (Juggluco); CSV export parser (Tidepool uploader); partner route (Tidepool private plugin) | Juggluco, Tidepool uploader, Tidepool platform | 3, each a different route |
| Dexcom Share (follower service) | unofficial | nightscout-connect, share2nightscout-bridge (deprecated), dexcom-share-client-swift (also used by Loop, Trio, LoopFollow), xDrip+, xdripswift, Nocturne | 6 (5 once the bridge is archived) |
| Dexcom developer API | official, OAuth | Tidepool platform | 1 |
| Medtronic CareLink | unofficial | minimed-connect-to-nightscout (deprecated, reported not working), nightscout-connect, xDrip+, xdripswift, Nocturne | 5 (4 current) |
| Tandem Source | unofficial ("undocumented APIs") | tconnectsync; Nocturne Tandem (derived) | 1 + 1 derived |
| Glooko | unofficial per nightscout-connect | nightscout-connect, Nocturne; four more outside the census | 2 (+4) |
| Tidepool | published API | TidepoolService/TidepoolKit, xDrip+, AndroidAPS (upload); Nocturne (read) | 4 |
| Eversense cloud | no statement | Nocturne | 1 |
| twiist | Nocturne "reverse-engineered"; Tidepool platform partner provider | Nocturne, Tidepool platform | 2 |
| Medtrum EasyView | no statement | xdripswift | 1 |
| mylife (Ypsomed), Gluroo | no statement | Nocturne | 1 each |
| MyFitnessPal | no statement | Nocturne | 1 |
| Oura | partner API | Tidepool platform | 1 |

Every one of these implementations meets the same vendor change separately. The widest
fan-out is Dexcom Share (six code bases, four languages) and LibreLinkUp (five or six).

### 1.3 Vendor-driven changes, 2023-09-30 to 2026-09-30

Method: `git log` subjects matching login, token, OAuth/SSO, header, app-version, region,
endpoint, response shape, WAF/Cloudflare, API-version terms, read one by one; only commits
whose subject says the vendor side changed (or that a new vendor region or service
generation had to be supported) are counted. Author dates. Counts are events (one vendor
change may take several commits), with commits in brackets. This is read from commit
subjects, not reproduced against the vendors; subjects can overstate or understate cause.

| connector | vendor | events (commits) | examples |
|---|---|---:|---|
| timoschlueter/nightscout-librelink-up | LibreLinkUp | 6 (10) | requests blocked, 2024-04-02 `8d173e8`, app version and user agent 2024-04-05 `f5310f6`; endpoints and LA region 2024-06-27/07-09 `64a89a8` `13b46f9`; "connection errors starting November 2024" `420b340`, an app-version value `e406ae4`, RU endpoint `b77fd4e` (2024-11-15); account id from the login response 2025-01-03 `9bd2a9d`; CN region 2025-03-05 `1b13082`; an app-version value 2025-10-02 `1dadafe` |
| xdripswift | LibreLinkUp | 7 (7) | GB accounts (eu2) 2023-12-28 `3b083376`; account header "required by" a newer app version 2024-07-12 `13e4a1e7`, LA subdomain `132b14a3`; app version 2024-10-04 `09995b25`; Russia 2025-03-10 `7347cc5f`; an app-version value 2025-10-02 `512c0b16`; an app-version value 2025-12-04 `b69dc490` |
| nightscout-connect | LibreLinkUp | 3 (4) | "Fixing librelinkup failure" 2024-01-11 `0e8cf6e`; "October 2025 changes", authored 2025-10-21, landed 2026-09-22 `f52d929`; v4 login and response shape 2026-09-22 `370d9f4` `3dbd1a6` |
| DiaBLE | LibreLinkUp | 1 (3) | a newer LibreLinkUp generation ("LLU 5") whose graph data the project describes as encrypted and signed, 2026-04-25 `ad597a6` `a26a9d3` `c24b234` |
| Nocturne FreeStyle | LibreLinkUp | 1-2 (2) | "Fix Freestyle API integration" 2026-01-13 `4b371634` (cause not stated); LibreLinkUp terms prompts reported as refusals 2026-09-27 `828b25ce` |
| nightscout-connect | Dexcom Share | 1 (1) | "handle modern response shape" 2026-06-29 `980c8a5` |
| xdripswift | Dexcom Share | 1 (1) | two-step login and Japan region 2025-11-03 `f6942117` |
| dexcom-share-client-swift | Dexcom Share | 1 (1) | Japan and APAC 2024-04-07 `21d8657` |
| share2nightscout-bridge | Dexcom Share | 0 | last one 2021-11-30 (trend as string, `62b7d2a`), already in the sponsored-team proposal §6a |
| Tidepool platform | Dexcom developer API | 1 (1) | "Do not specify last sync time for Dexcom data range API, per Dexcom" and response "oddities", 2026-07-24 `e62f6b58`; other Dexcom commits in the window are additive (G7 15-day, 2025-12-05 `51a79a53`) or error handling (`902f3051`) |
| xDrip+ | CareLink | 7 (9) | reCAPTCHA and token refresh 2023-10-07 `a5b9af49`; care-partner app login 2023-11-26 `84efa6a6`; discovery URL 2024-11-16 `79ac7a12`; "v11 cloud data endpoint" EU 2025-01-18 `2baa087d`, US 2025-02-09 `f70d8470`; standalone sensors "migrated from legacy servers to cloud servers" 2025-03-12 `400d6968`; discovery URL and SSO configuration 2026-01-03 `bbcbb39e` `ddbca756`; app version 3.8.0 2026-08-25 `1f9c66d6` |
| xdripswift | CareLink | 0-1 | follower written 2026-08; "Use CarePartner OAuth" 2026-08-21 `7415ede3` is a design choice in a new client |
| Nocturne CareLink | CareLink | 0-1 (1) | a WAF answering requests without a user agent with 403, 2026-07-30 `5b7fad9e` (the commit lists it with two local faults) |
| minimed-connect-to-nightscout | CareLink | 0 | last one 2023-06-07 (`54b61fe`, just before the window) |
| nightscout-connect | CareLink | 0 | source disabled 2023-10-11 (`2fb8d21`), later kept in-tree with contract and logging fixes |
| tconnectsync | Tandem | 5 (7) | web login broke and WAF block 2024-09-08 `c9f6362` `c60b19d`; move to Tandem Source 2024-09-18 `a77ebb5` (README: t:connect shut down in the US from 2024-09-30); EU region 2025-06-07 `4888426`; WAF 403 2026-06-30 `e5195b2`; new client id and new Source APIs 2026-07-01 `d568a5b` `afbc990` (v3.0.0) |
| Nocturne Tandem | Tandem | 1 (1) | the vendor "retired the reportsfacade endpoints on June 30th"; ported from tconnectsync 2026-07-04 `e671a00e` |
| nightscout-connect | Glooko | 1 (2) | web login and v3 graph fallback 2026-07-07 `c06c037` `2d733c9` |

Readings from the table:

- **LibreLinkUp changes arrive about twice a year and reach every client.** Across the five
  clients there are 18 to 19 dated events in three years. The same change lands on different days:
  account-id handling appears in xdripswift on 2024-07-12 and in nightscout-librelink-up on
  2024-11-15 (its diff adds it; `420b340`); the same app-version change lands in both on 2025-10-02; nightscout-connect's fix for the
  October 2025 change was written on 2025-10-21 and reached a release on 2026-09-24
  (v0.1.0). No shared notice channel between the clients appears in the repositories.
- **CareLink changes were at least as frequent** in xDrip+ (7 events), and two of four current
  clients started in 2026.
- **Tandem's move to Tandem Source and its June 2026 endpoint retirement** were absorbed by
  tconnectsync; the second implementation (Nocturne) followed it four days later.
- **The one official-API client in the corpus** (Tidepool's Dexcom integration) shows vendor
  guidance and additive device support in the same window, and no login or header changes in
  its commit subjects. One client is too few to generalise from.

These counts extend, and do not repeat, the table in
sponsored-team proposal §6a (`docs/00-overview/SPONSORED-TEAM-PROPOSAL.md`)
and the "no date" row of COLLABORATION-MODEL §3 (`docs/00-overview/COLLABORATION-MODEL.md`)
("about two connector changes a year").

## 2. Documented routes out of the vendor clouds, and the rules around them

All pages read 2026-09-30. Quotes are short and verbatim. Where a page was blocked, the entry
says so and names what was read instead. EUR-Lex returned a bot challenge, so the EU texts
were read from the EU Publications Office copy of the Official Journal
(`http://publications.europa.eu/resource/celex/<CELEX>`); hhs.gov returned 403, so HIPAA was
read from eCFR (Title 45, current to 2026-09-28). Several vendor help centres returned 403;
those items are marked "snippet only" and need a person to open the page.

### 2.1 Vendor and platform routes

| route | what the vendor documents | source |
|---|---|---|
| Dexcom developer API (v3) | six endpoints (alerts, calibrations, dataRange, devices, egvs, events) for G6, G7, G7 15-day, ONE and ONE+; data "with a one-hour delay in the United States and with a three-hour delay outside the United States"; OAuth 2.0, and "Users ... can revoke the access at any time"; a sandbox with simulated data; free registration under a "Registered Developer Agreement"; an "Individual" path to "Limited Access", which "allows you to authenticate up to 5 users"; commercial apps "must submit a request for a commercial partnership"; scopes are all or nothing | https://developer.dexcom.com/docs/dexcomv3/endpoint-overview/ , /docs/dexcom/authentication/ , /docs/dexcom/sandbox-data/ , /docs/dexcom/scopes-access/ , /docs/dexcom/getting-started/ |
| Abbott LibreView | personal CSV download: "select 'Download Glucose Data'" (**snippet only**, page 403); Abbott publishes a partner-integrations table (MiniMed 780G, NovoPen 6, mylife Loop/CamAPS FX, Omnipod 5) and an EHR agreement with Epic (2025-04-29); no public self-service developer API found | https://www.support.freestyle.abbott/hc/en-us/articles/14806679954199 ; https://www.diabetescare.abbott/partnerships/integrations/en.html ; https://abbott.mediaroom.com/2025-04-29-Abbott-Integrates-Libres-Data-with-Epics-Electronic-Health-Record-System,-Providing-Healthcare-Professionals-Seamless-Glucose-Monitoring-Information |
| Medtronic CareLink | clinic edition: "Click Data Export (CSV)", maximum 90 days (guide dated 2019); CareLink Personal FAQ describes reports ("Generate Reports"), not CSV. **Gap:** no current Medtronic page read here confirms CSV export for individuals | https://www.medtronicdiabetes.com/sites/default/files/library/download-library/workbooks/CareLink-System-User-Guide.pdf ; https://carelink.minimed.eu/media/en/ca/faq.pdf |
| Tandem Source | t:connect "officially retired as of September 2024"; personal guide: "click Export CSV to export the report contents to a CSV" from the Daily Timeline; Glooko states (2026-06-29) that linked Tandem Source accounts "synchronize automatically and continuously" to Glooko | https://www.tandemdiabetes.com/hc/en-us/articles/26484399231511-Retirement-of-t-connect-Platforms ; https://www.tandemdiabetes.com/docs/default-source/user-guide/user-guide-tandem-source-personal-mgdl-aw1014831.pdf ; https://glooko.com/glooko-platform-adds-tandem-cloud-connectivity/ |
| Tidepool | "APIs not marked Internal ... are available to everyone"; a client identifier must be requested; separate integration and production environments; export to "Excel (XLSX) or JSON" (**snippet only**) | https://tidepool.redocly.app/ ; https://developer.tidepool.org/ ; https://support.tidepool.org/hc/en-us/articles/360044350552-Exporting-Tidepool-data |
| Glooko | personal "Export to CSV" on the web, "not accessible via the Glooko Mobile App" (**snippet only**); an "API and EHR Integration Portal" aimed at clinics and partners (JavaScript-only page, not read further) | https://support.glooko.com/hc/en-us/articles/4460340377875 ; https://developers.glooko.com/ |
| Apple HealthKit (on-device hub) | `bloodGlucose` (iOS 8) and `insulinDelivery` in IU (iOS 11) with a delivery-reason key; App Review 5.1.3: health data may not be used "for advertising, marketing, or other use-based data mining purposes other than improving health management" and apps "must not write false or inaccurate data into HealthKit" | https://developer.apple.com/documentation/healthkit/hkquantitytypeidentifier/bloodglucose ; .../insulindelivery ; https://developer.apple.com/app-store/review/guidelines/ |
| Android Health Connect (on-device hub) | `BloodGlucoseRecord` (connect-client 1.1.0); the records package lists 41 types and none for insulin; "a database that's stored on your device"; Google Fit APIs "will be deprecated in 2026", closed to new developers since 2024-05-01, "supported until the end of 2026" | https://developer.android.com/reference/kotlin/androidx/health/connect/client/records/package-summary ; https://support.google.com/android/answer/13770320 ; https://developers.google.com/fit ; https://developer.android.com/health-and-fitness/guides/health-connect/migrate/comparison-guide |

In the corpus, the documented routes are used as follows: the Dexcom developer API by
Tidepool platform only; the LibreView CSV by Tidepool uploader; Tidepool's API by
TidepoolService, xDrip+, AndroidAPS and Nocturne; HealthKit by Loop, Trio, iAPS, xdripswift,
LoopFollow, LoopCaregiver, nightguard and DiaBLE; Health Connect by xDrip+ and Juggluco (§3).
None of the Nightscout-side connectors (nightscout-connect, Nocturne, tconnectsync) uses a
documented vendor route for real-time data. The documented routes differ from the follower
routes in timing (Dexcom's one-to-three-hour delay; export files on demand) and in who may
register (Dexcom's five-user Limited Access, partnership for commercial apps).

### 2.2 Data-rights law and regulation

Every item below is **for counsel review**. This section reports what the texts and the
regulators' own pages say; it draws no conclusion about how they apply to any vendor, to the
foundation or to a person.

| instrument | what the text says (short quotes) | source | for counsel to verify |
|---|---|---|---|
| GDPR Art. 15 | right to "confirmation as to whether or not personal data ... are being processed, and ... access"; "The controller shall provide a copy", for electronic requests "in a commonly used electronic form"; Art. 12(3): "within one month", extendable "by two further months" | http://publications.europa.eu/resource/celex/32016R0679 | whether a CGM or pump vendor cloud is the controller for the data it holds; timing in practice |
| GDPR Art. 20 | data "which he or she has provided", where processing is based on consent or contract and automated, "in a structured, commonly used and machine-readable format", with direct transmission "where technically feasible" | same | whether sensor readings are data "provided by" the data subject; Art. 9 bases for health data |
| EU Data Act, Regulation (EU) 2023/2854 | "It shall apply from 12 September 2025"; the Art. 3(1) design obligation applies to products "placed on the market after 12 September 2026"; Art. 2(5) connected product; Art. 3(1) data "by default, easily, securely, free of charge, in a comprehensive, structured, commonly used and machine-readable format"; Art. 4(1) access "where relevant and technically feasible, continuously and in real-time"; Recital 14 names "medical and health devices"; Recital 15 excludes information "inferred or derived ... by means of proprietary, complex algorithms"; Recital 16 excludes "content" | http://publications.europa.eu/resource/celex/32023R2854 | whether CGM and pump raw data is in scope and which outputs count as derived; who the "data holder" is for a vendor cloud; the trade-secret and safety limits from Art. 4(2) |
| Data Act, Commission FAQ v1.4 (2026-01-22) | "applies to all connected products, including those that are subject to specific type approval or conformity assessment regimes (e.g. motor vehicles, aircraft, and medical devices)"; in scope "raw data and pre-processed data", out of scope "inferred or derived data"; the FAQ says it "should not be considered as representative of the European Commission's official position" | https://digital-strategy.ec.europa.eu/en/library/commission-publishes-frequently-asked-questions-about-data-act | weight of the FAQ; effect of the Commission's "digital omnibus" proposal (https://digital-strategy.ec.europa.eu/en/faqs/digital-package), whose status was not checked |
| EHDS, Regulation (EU) 2025/327 (new detail beyond ECOSYSTEM-PROGRAMME) | "shall apply from 26 March 2027"; access rights and EHR-system rules from 26 March 2029 (patient summaries, prescriptions) and 26 March 2031 (images, results, discharge reports); defines "wellness application"; Art. 47 labelling "Where a manufacturer of a wellness application claims interoperability with an EHR system"; Art. 51(1)(h) lists data "automatically generated through medical devices" for secondary use | http://publications.europa.eu/resource/celex/32025R0327 | whether self-built open-source software has a "manufacturer" in the EHDS sense |
| US HIPAA right of access, 45 CFR 164.524 | binds covered entities: "(1) A health plan. (2) A health care clearinghouse. (3) A health care provider who transmits any health information in electronic form" (45 CFR 160.103); action "no later than 30 days", one extension "by no more than 30 days"; "in the form and format requested by the individual, if it is readily producible" | https://www.ecfr.gov/current/title-45/section-164.524 ; https://www.ecfr.gov/current/title-45/section-160.103 | whether a device-maker cloud is a covered entity or business associate in any arrangement; pending rule changes (not checked) |
| US information blocking (Cures Act), 45 CFR 171 | "Actor means a health care provider, health IT developer of certified health IT, health information network or health information exchange"; a developer is an actor if it has "one or more Health IT Modules certified"; ASTP/ONC names the same three groups and does not name device manufacturers as a separate category | https://www.ecfr.gov/current/title-45/section-171.102 ; https://www.healthit.gov/topic/information-blocking | actor status of any particular company |
| FDA MDDS guidance (September 2022) | software "solely intended to transfer, store, convert formats, or display medical device data and results ... are not devices"; functions "intended for active patient monitoring" are outside that, with "a device used to actively monitor diabetes for time-sensitive intervention" as an example | https://www.fda.gov/regulatory-information/search-fda-guidance-documents/medical-device-data-systems-medical-image-storage-devices-and-medical-image-communications-devices ; https://www.fda.gov/media/88572/download | how the carve-out applies to any display or alarm feature |
| 21 CFR 862.1350 | now "Continuous glucose monitor secondary alarm system"; special controls include "measures to protect against unauthorized access to data"; required warning "Dosing decisions should not be made based on this device"; Dexcom Share was DEN140038, "continuous glucose monitor secondary display", granted 2015-01-23 | https://www.ecfr.gov/current/title-21/section-862.1350 ; https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/denovo.cfm?id=DEN140038 | regulatory: which features of a follower app fall under this classification |
| 21 CFR 862.1355 iCGM | "designed to reliably and securely transmit glucose measurement data to digitally connected devices"; no "clinically significant gaps in sensor data availability"; a "strategy to ensure secure and reliable means of iCGM data transmission" | https://www.ecfr.gov/current/title-21/section-862.1355 | — |
| 21 CFR 862.1356 iAGC | "validated interface specifications for digitally connected devices", including "Secure authentication (pairing)", "Sharing of necessary state information" and "A detailed process and procedures for sharing the controller's interface specification with connected devices and for validating the correct implementation"; a "record of critical events"; inputs only from 862.1355 devices and commands only to 880.5730 pumps unless FDA determines otherwise | https://www.ecfr.gov/current/title-21/section-862.1356 | whether the "sharing" controls imply any publication to parties other than the manufacturer's partners (the text does not say) |
| 21 CFR 880.5730 ACE pump | "designed to reliably and securely communicate with external devices"; the same interface-specification list, including "sharing the pump interface specification with digitally connected devices"; safe fallback on loss of communication; critical-events record | https://www.ecfr.gov/current/title-21/section-880.5730 | as above |

First classifications (accessdata.fda.gov, read 2026-09-30): DEN170088 Dexcom G6 iCGM,
2018-03-27; DEN180058 t:slim X2 ACE pump, 2019-02-14; DEN190034 Control-IQ iAGC,
2019-12-13. These rules are about device-to-device interfaces, not cloud data export; they
are the regulated route by which interoperability between manufacturers is specified.

## 3. Wearables and other data sources

### 3.1 In the ecosystem code

Search over the clones for Oura, WHOOP, Garmin, Fitbit, Strava, MyFitnessPal, Cronometer,
Nutritionix, Google Fit, Polar, Withings, Health Connect and HealthKit types, read
2026-09-30.

| source | integration found | where |
|---|---|---|
| Android Health Connect | xDrip+ reads and writes glucose, heart rate, steps, exercise, sleep and nutrition records (`healthconnect/HealthGamut.java`, connect-client 1.1.0-alpha06); Juggluco writes glucose only (`BloodGlucoseRecord`, connect-client 1.1.0-rc03) | NightscoutFoundation/xDrip, j-kaltes/Juggluco |
| Apple HealthKit | blood glucose, insulin delivery and carbohydrates, in Loop/LoopKit, Trio, iAPS, xdripswift, LoopFollow, LoopCaregiver, nightguard, DiaBLE, TidepoolService | those repositories |
| Oura | Tidepool platform partner integration with webhooks, raw-data ingestion and a consent flow (`oura/`, commits `a1c71d35`, `772b47b6`, 2026-05-16); Nocturne lists Oura only as a sleep-data source label (`SleepEnums.cs`) | tidepool-org/platform; nightscout/nocturne |
| Garmin | watch-face and watch-app links, not the Garmin cloud: AndroidAPS, Trio, iAPS, Juggluco | those repositories |
| Fitbit | sulkaharo/nsfitbit is a Fitbit watch face that reads Nightscout; Nocturne lists Fitbit as a sleep source label | sulkaharo/nsfitbit; nightscout/nocturne |
| MyFitnessPal | Nocturne connector for food diary entries "for meal matching" (`src/Connectors/Nocturne.Connectors.MyFitnessPal`, 45 test cases) | nightscout/nocturne |
| Glooko heart rate and body weight | imported by Nocturne's Glooko connector (mapper tests) | nightscout/nocturne |
| WHOOP, Strava, Cronometer, Google Fit | no integration found (one Strava string in a Tidepool uploader test) | — |

### 3.2 What the vendors offer (read 2026-09-30)

| vendor | offering, short quotes | source |
|---|---|---|
| Oura | API v2 with OAuth 2.0 only; "personal access tokens were deprecated in December 2025"; access lapses when "The user's Oura membership has expired"; sleep, activity, readiness, heart rate, workouts; webhooks | https://cloud.ouraring.com/v2/docs |
| WHOOP | OAuth 2.0; "Every new app starts on the Sandbox tier, which allows up to 10 WHOOP members to connect"; higher tiers on request | https://developer.whoop.com/docs/developing/app-approval/ ; https://developer.whoop.com/docs/developing/getting-started |
| Garmin | Health, Activity and other APIs; "no licensing or maintenance fees ... but it is only for business use"; applications reviewed "within two business days" | https://developer.garmin.com/gc-developer-program/program-faq/ |
| Fitbit / Google Health API | "Support for the legacy Fitbit Web API ends on September 30, 2026" and it will be "turned off" on 2026-10-30; the Google Health API includes "blood-glucose" but "we are not onboarding new projects at this time" | https://dev.fitbit.com/build/reference/web-api/ ; https://developers.google.com/health ; https://developers.google.com/health/data-types |
| Strava | terms effective 2026-06-01: a user's data "can only be displayed or disclosed in your Developer Application to that user"; policy §5.3 bars use "in connection with the development, training, evaluation, or operation of any AI Application"; new apps start in "single-player mode"; "A Strava subscription is a prerequisite for creating an app" (counsel: verify how §5.3 applies to a self-hosted tool) | https://www.strava.com/legal/api ; https://www.strava.com/legal/api_policy ; https://developers.strava.com/docs/getting-started/ |
| MyFitnessPal | "We are not accepting requests for API access at this time." | https://www.myfitnesspal.com/api |
| Nutritionix | API for "registered partners"; site "temporarily offline while we roll out major upgrades" | https://www.nutritionix.com/business/api |
| Cronometer | no public developer page found; CSV export and Health Connect / Apple Health sync mentioned (**snippet only**) | https://cronometer.com/developer/ (empty shell) |

Two dates fall inside the next month: the Fitbit Web API support ends on the read date and the
API is turned off on 2026-10-30, and Google Fit support ends at the end of 2026. No corpus
repository calls either, so neither reaches the ecosystem code directly; both push data toward
the on-device hubs. Health Connect has no insulin record type, so on Android insulin data
still has no shared on-device home.

## 4. What quality control at the cloud layer would need

### 4.1 What exists today

- **Synthetic or mocked vendor responses in unit tests** in every active connector:
  nightscout-connect (258 cases), tconnectsync (463, including parsers tested on captured
  pump-log data), Nocturne (about 880 connector cases including the shared core, HTTP mocked in code), xDrip+ and
  xdripswift (CareLink, Dexcom Share), nightscout-librelink-up (10 cases on five JSON
  response files), Tidepool platform (466 cases in `dexcom/`).
- **One lab that runs a connector against real Nightscout storage in CI**:
  nightscout-connect's LibreLinkUp job (`.github/workflows/test.yml`), with a synthetic vendor
  transport.
- **Opt-in live probes** that refuse to contact the vendor without an explicit flag
  (nightscout-connect Glooko and LibreLinkUp regional lab), and a credential and record scan
  of connector logs (`test/privacy-canary.test.js` there; `tools/lab/connector-soak/canary.py`,
  `7264d184`, in this repository, for Nightscout-to-Nightscout).
- **No shared fixture format, no shared contract description per vendor, and no scheduled
  check that notices a vendor change before users do.** Each project's fixtures describe the
  vendor as that project last saw it, in its own language and shape; none of them are shared.

### 4.2 The pieces

Effort figures are **estimates** in person-weeks for one experienced engineer, assuming:
volunteers with their own accounts consent to record their own sessions and to de-identify
them before anything is kept; six vendor clouds in the first round (LibreLinkUp, Dexcom
Share, CareLink, Tandem Source, Glooko, Dexcom developer API sandbox); five implementations
adopt the shared suites (nightscout-connect, Nocturne, tconnectsync, xDrip+, xdripswift); the
maintainers of those projects review and accept the adapters. They do not include counsel's
time on vendor terms (4.3).

| piece | what it is | initial effort (estimate) | ongoing (estimate) | holder's rights it supports |
|---|---|---|---|---|
| Vendor contract notes | per vendor cloud: the data it returns, the fields each implementation reads, regions, refusal and lockout cases, and the dated history of changes (the §1.3 table, kept current). Mechanism level only; no request recipes | 0.5-1 per vendor, 3-6 | 0.25 per vendor change | access, export: the holder can see what data the route carries and what it drops |
| Shared recorded-fixture suites | de-identified, synthetic-where-possible response sets per vendor and region, in one language-neutral format (for example a HAR-like JSON with a manifest of what each case covers), plus the refusal cases (bad password, terms prompt, lockout, WAF block, rate limit) | format and replay harness 3-5; 2-4 per vendor, 12-24 | 0.5-1 per vendor change, to add the new shape | access, export; delegate: the helper tool's behaviour on refusal is tested, so a stalled account is reported rather than silent |
| Adapters per implementation | replay the shared fixtures through each project's own test runner (node:test, xUnit, pytest, XCTest, JUnit) | 1-2 per implementation, 5-10 | small, with each fixture addition | share: every server and follower the holder chooses behaves the same on the same input |
| Change canary | scheduled, read-only, low-frequency probes with consenting test accounts, per region where an account exists, that compare response shape and login outcome with the contract and alert the maintainers of every implementation at once | 4-8 | 0.1-0.2 FTE to triage alerts and keep accounts and regions alive | access: the gap between a vendor change and a fix shrinks; audit: a dated record of when each change was seen |
| Per-release connector report | a generated page per implementation release: which vendor contracts and fixture versions passed, which live probes last passed and when, what is untested (regions without an account) | 2-4, plus 1 per implementation | near zero once generated in CI | audit: the holder or their helper can see what was tested before trusting a release with their data |
| Shared connector lab | containers for the supported Nightscout versions and Nocturne, a fixture-replay vendor stand-in, and the credential and record log scan, generalising nightscout-connect's LibreLinkUp lab and this repository's connector-soak lab | 6-10 | 0.1-0.2 FTE | delegate, audit: credentials a holder gives a connector are shown not to reach logs; export: end-to-end fidelity from vendor shape to stored record |

Sum of the initial ranges: about 40-72 person-weeks for the first round, then about
0.3-0.5 FTE ongoing plus 1-2 person-weeks per vendor change event. At the §1.3 rate
(LibreLinkUp alone about two events a year, CareLink similar, Tandem and others less often)
that is roughly 6-15 vendor change events a year across the six clouds. These are estimates
from the sizes of the existing suites and labs, not from a measured project, and the
reviewer should check them against the maintainers' own experience.

### 4.3 Constraints to carry into any design

- **Fixtures are health data until shown otherwise.** Recorded sessions carry glucose,
  treatments, device serials and account identifiers. The suites need a consent and
  de-identification step before anything is committed, and synthetic generation wherever a
  synthetic response exercises the same code. The public repositories must never hold a
  captured credential, token, account identifier or real trace.
- **Probes against unofficial routes raise vendor-terms questions.** Whether scheduled probes
  with volunteer accounts are consistent with each vendor's terms of use is for counsel, not
  for this note. The official routes in §2 (Dexcom developer API sandbox, documented export
  files, Tidepool's published API, HealthKit and Health Connect) can be probed and replayed
  without that question.
- **A shared suite is a description of vendor behaviour, not a way around vendor
  protections.** It should describe mechanisms at the level of this note and stay out of
  anything that would help defeat a vendor's access controls.
- **Region coverage is limited by volunteer accounts.** LibreLinkUp lists 13 regions; a
  canary covers only the regions where someone has consented to run an account, and the
  report must say which ones are uncovered.

### 4.4 How the pieces relate to data sovereignty

The five rights in `docs/state-of-diabetes-2026.md` Part III (access, export, share,
delegate, audit) depend at the cloud layer on the connector working on the day the holder
needs it. For most holders in the corpus the connector is the route by which their own data
leaves the vendor cloud in a form they can compute on. The routes the vendors document
(§2) are narrower: the Dexcom developer API has one client in the corpus, and the export
files are periodic rather than real-time. Until more of the data is reachable through
documented routes, shared tests and an early-warning canary are what keep the holder's
chosen tools and helpers working across every implementation at once.

## 5. Summary

1. Fourteen code bases in the corpus log in to vendor clouds; Nocturne alone has fourteen connectors, up from eight in the January mapping.
2. Dexcom Share has six independent clients in four languages; LibreLinkUp five (six with xDrip+ WebFollow); CareLink four current plus one deprecated; Tandem Source one plus a derived port.
3. Only one corpus project, Tidepool platform, uses the Dexcom developer API. Most Nightscout-side real-time data goes through unofficial follower routes. tconnectsync says it uses "undocumented APIs"; Nocturne calls its twiist connector "reverse-engineered", and says the same of the Tandem API it took from tconnectsync.
4. Commit subjects show 18-19 LibreLinkUp change events across five clients, 7 CareLink events in xDrip+, and 5 Tandem events in tconnectsync, 2023-09 to 2026-09 (e.g. `420b340`, `2baa087d`, `afbc990`).
5. Each client absorbs the same change on its own schedule: one LibreLinkUp change was fixed on 2025-10-21 and released on 2026-09-24; the account-id change landed four months apart in two clients.
6. Tests are mostly synthetic or mocked per project. Only tconnectsync tests on captured vendor data, and only nightscout-connect runs a connector against real Nightscout storage in CI. No fixture format is shared and no canary exists.
7. The documented routes exist but are narrower: Dexcom API (delay of one to three hours, five-user Limited Access), CSV exports (LibreView, Tandem Source, Glooko; CareLink Personal not confirmed), Tidepool API, HealthKit, and Health Connect (no insulin type).
8. For counsel: the texts on GDPR Arts. 15 and 20, the Data Act (applies 2025-09-12; the design duty from 2026-09-12; the FAQ names medical devices), HIPAA access and information blocking (device makers are named only as certified-IT developers), and the FDA rules (MDDS, 862.1350/1355/1356, 880.5730).
9. Wearables: the ecosystem uses Health Connect (xDrip+, Juggluco) and HealthKit widely, Oura only through Tidepool, and MyFitnessPal only through Nocturne. The Fitbit Web API shuts off on 2026-10-30 and Google Fit support ends in 2026.
10. A shared cloud-layer QC set (contract notes, fixture suites, adapters, change canary, release reports, lab) is estimated at 40-72 person-weeks, then 0.3-0.5 FTE. It supports all five holder rights, subject to consent, de-identification and counsel's view of vendor terms.
