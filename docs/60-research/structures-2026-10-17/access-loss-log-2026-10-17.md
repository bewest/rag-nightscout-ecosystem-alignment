# Access-loss log: when open diabetes software lost, or never had, access

*For the Nightscout Foundation board, the maintainers of the ecosystem projects, and the community.
**Research note, snapshot of 2026-10-17.** Dated events in which open-source diabetes software lost,
or never got, access to a device or a vendor cloud, and when access came back. Every row cites a
commit, issue, pull request or URL. Used by [why organise §3](../../00-overview/WHY-ORGANISE.md#3-access-already-lost-or-delayed).
A shared intake ([partner readiness §6](../../00-overview/PARTNER-READINESS.md#6-complaint-incident-and-support-handling))
would carry this forward with counts of the people each event reached, which no source here
records.*

All rows read 2026-10-17 unless marked otherwise. "Lag" is measured from the vendor's first launch
or clearance named in the row to the first public open-software commit or release named in the row.
Mechanism level only: no header values, endpoints, keys or request formats are recorded here.

Abbreviations: NS = Nightscout; LLU = Abbott LibreLinkUp (follower app and its cloud);
nsc = nightscout/nightscout-connect; nslu = timoschlueter/nightscout-librelink-up;
mmc = nightscout/minimed-connect-to-nightscout; s2nb = nightscout/share2nightscout-bridge;
tcs = jwoglom/tconnectsync.

## 1. Events

### 1a. Devices

| date | device or cloud | what was lost (or never available) | open-software consequence | when/whether restored | source | confidence |
|---|---|---|---|---|---|---|
| 2012-10-22 to 2016 | Medtronic Paradigm x12–x54 (5xx/7xx) | Nothing lost: the pumps could be read and commanded over their radio protocol | decocare (2012), RileyLink (2015), then OpenAPS, Loop and AAPS drove these pumps | n/a | bewest/decoding-carelink created 2012-10-22; ps2/rileylink created 2015-05-06; openaps/decocare created 2016-06-17 (gh api) | confirmed (repo dates); model and firmware limits per maintainer's account, not sourced here |
| 2013-09-27 | Medtronic MiniMed 530G (US) | Next pump generation not openly commandable | No open control driver for 530G, 630G, 640G, 670G, 770G or 780G was found in the sources read | not restored for control (see 780G row) | [Medtronic news 2013-09-27](https://news.medtronic.com/2013-09-27-Medtronic-Gains-Approval-of-First-Artificial-Pancreas-Device-System-with-Threshold-Suspend-Automation) | partly: launch date confirmed; "no open control" is an absence in the sources read |
| 2015 (EU 640G) / 2016-09-28 (US 670G) | Medtronic 600 series | Read only via the vendor USB meter link, or via CareLink; no open control | 600SeriesAndroidUploader read data to NS from 2016-05-10; control never available | read-only path arrived; control never | pazaan/600SeriesAndroidUploader created 2016-05-10, last push 2022-05-14; 670G PMA P160017 approved 2016-09-28 ([FDA SSED](https://www.accessdata.fda.gov/cdrh_docs/pdf16/P160017S091B.pdf)) | confirmed for 670G date and uploader; 640G launch date not verified |
| 2019-06-27 | Medtronic MiniMed 508 and Paradigm pumps | FDA safety communication: cybersecurity weakness in the radio link; replacement with newer models recommended, as the pumps cannot be patched | The openly commandable pump family was the subject of the recall; Medtronic pointed US patients to the 670G, which open apps cannot command | n/a | FDA safety communication 2019-06-27 (press coverage, e.g. [RAPS](https://www.raps.org/resource/fda-warns-of-cyber-risk-with-medtronic-insulin-pum.html)); FDA page itself not opened | partly |
| 2020-08-31 (770G BLE); 2023-04-21 (US 780G) | Medtronic 770G/780G (BLE) | Pump data reaches only the vendor phone app and CareLink | NS only through CareLink connectors (see cloud rows); OpenMinimed proof-of-concept BLE work from 2026-01-28, stated "do not rely on it for therapy" | not restored; proof of concept only | FDA supplement P160017 (770G BLE, 2020-08-31; 780G notice 2023-04-21) [FDA](https://www.accessdata.fda.gov/cdrh_docs/pdf16/P160017S125B.pdf); OpenMinimed org repos created 2026-01-28 (PythonPumpConnector @ b57615e0, Documentation @ 73a7811d) | confirmed; 780G EU launch date not verified |
| 2018 (EU, CE date not verified) | Abbott FreeStyle Libre 2 | Sensor data encrypted on the radio link | xDrip+ first read Libre 2 through a patched copy of the vendor app (2019-07-14), then native Bluetooth "in production" 2020-10-07; xdripswift Libre 2 support 2020-05-20 | restored by open reimplementation | xDrip @ 1ed760048: b92845d7d (2019-07-14), fcbb90b5a (2020-10-07); xdripswift @ c268542e: d14061a0 (2020-05-20) | confirmed for commits; launch date not verified |
| 2019-11-08 | Abbott Libre 2 patched app | DMCA takedown of "Libre2-patched-App" on GitHub; a second notice 2019-11-12 for a project that downloaded the vendor app | The route xDrip+ users had used for Libre 2 was removed from GitHub | native route arrived 2020-10-07 (row above) | github/dmca 2019/11/2019-11-08-abbott.md, 2019/11/2019-11-12-abbott.md | confirmed |
| 2021-08-17; 2023-01-03; 2023-08-02 | Abbott LibreLink derivatives | Further DMCA notices: a third-party Libre app (2021) and two "FreeStyle-Libre-3-patch" projects (2023) | Patched-app routes for Libre 3 removed from GitHub | n/a | github/dmca 2021/08/2021-08-17-abbott.md, 2023/01/2023-01-03-abbott.md, 2023/08/2023-08-02-freestyle-libre.md | confirmed |
| 2020 (CE, Sept/Oct, sources disagree); 2022 (US) | Abbott FreeStyle Libre 3 | No open direct read at launch | Juggluco's first public commit (2023-01-29) already contains a Libre 3 module; earlier Juggluco releases not checked; iOS: DiaBLE research commits from 2023-09-15 | arrived on Android by 2023-01-29 at latest | j-kaltes/Juggluco cc7d74c7 (2023-01-29, `Common/src/libre3`); DiaBLE @ e6a909c: c1d9a05, 3529ede (2023-09-15); CE coverage [MobiHealthNews](https://mobihealthnews.com/node/148848) | partly (launch month and first Juggluco Libre 3 release not verified) |
| 2022-10-04 (UK/IE/DE/AT/HK); 2022-12-08 FDA | Dexcom G7 | Sensor requires authentication; at launch only the vendor app could pair | Passive ("companion") modes that listen while the vendor app is connected: xDrip+ 2022-10-13, Loop G7SensorKit 2022-11-11, xdripswift 2024-02-13. Direct authentication: xDrip+ added its native library 2023-03-15; Juggluco Dexcom module first appears 2024-11-26 (9.0.0b); xdrip-js G7 crypto on its `dev` branch from 2025-12-24; xdripswift native G7 2026-08-30 (in 7.1.0); G7SensorKit direct connection merged to `next-dev` 2026-09-20 (PR #67) | Loop: direct auth on `next-dev` only; LoopWorkspace `dev` and `main` and Trio `dev`/`main` still pin the passive line (repo doc g7sim-deep-dive.md, read 2026-10-17) | [Dexcom 2022-10-04](https://businesswire.com/news/home/20221004005386/en/); [Dexcom 2022-12-08](https://investors.dexcom.com/news/news-details/2022/Dexcom-G7-Receives-FDA-Clearance-The-Most-Accurate-Continuous-Glucose-Monitoring-System-Cleared-in-the-U.S/default.aspx); xDrip 7c7d6fd26, 7ee34733c; LoopKit/G7SensorKit fdcfb208, 764e0026, PR #67, next-dev @ e17129d0; j-kaltes/Juggluco 4a3efe66; xdrip-js eab0a64 (remotes/origin/dev); xdripswift f631d54b, ecbb493d | confirmed; US commercial launch day not verified |
| 2018-06-04 FDA; full US launch early 2019 | Insulet Omnipod DASH | Bluetooth pod; the Eros radio driver did not apply | AAPS DASH module started 2021-02-09, released in AAPS 3.0.0 (tag 2022-01-31); OmniBLE initial commit 2021-09-07, Loop 3.0.0 tag 2023-01-14 | restored by open driver | [Insulet 2018-06-04](https://www.businesswire.com/news/home/20180604005355/en); AndroidAPS 43409eb864, tag 3.0.0; LoopKit/OmniBLE 7b299878 (via randallknutson/OmniBLE parent); LoopKit/LoopWorkspace tag v3.0.0 | confirmed |
| 2022-01-28 FDA | Insulet Omnipod 5 | Pod checks a controller certificate; DASH drivers could not drive it | No open Omnipod 5 driver in the sources read until loopandlearn/OmnipodKit "Initial Omnipod 5 integration" 2026-02-22 (on `dev`; README now lists Omnipod 5, DASH and Eros) | arrived 2026-02-22 in OmnipodKit `dev`; AAPS status not checked | [Insulet 2022-01-28](https://s201.q4cdn.com/452214269/files/doc_news/2022/01/28/Insulet-Announces-FDA-Clearance-of-its-Omnipod®-5-Automated-Insulin-Delivery-System-First-Tubeless-System-with-Smartphone-Control.pdf); loopandlearn/OmnipodKit 92d4207d (dev @ 928bb795) | confirmed for dates; whether this is the first public O5 code anywhere is not verified |

### 1b. Vendor clouds

| date | device or cloud | what was lost (or never available) | open-software consequence | when/whether restored | source | confidence |
|---|---|---|---|---|---|---|
| 2020-04-02 | Dexcom Share | Share server change | s2nb could not connect | fixed by 2020-05-19 (#38 closed) | s2nb #38, #39 | partly (nature of change not read) |
| 2020-12-13 | Medtronic CareLink (EU) | Token refresh rejected; login flow changed | mmc stopped fetching | fixed 2020-12 (#15, #17–#20) | mmc #15, #20 | confirmed |
| 2021-03-17 / 2022-03-17 | Tandem t:connect | Login changes on Tandem's side | tcs could not connect | 2022-03-17 same day (v0.7.0) | tcs #2, #38, release v0.7.0 | confirmed |
| 2021-11 (from 2021-11-04 warning) | Dexcom data to Sugarmate | Dexcom closed the "legacy channel" Sugarmate used | Sugarmate lost CGM data in the US; its NS bridge support was removed | Dexcom data back 2021-12-09 (US) and 2022-05-12 (EU/UK/CA) via Dexcom's partner API; NS bridge never restored | [Sugarmate version history](https://help.sugarmate.io/en/articles/5965236-sugarmate-by-tandem-version-history) (2.7.1, 2.8.0); [Loop and Learn FAQ 2021-11-02](https://www.loopandlearn.org/wp-content/uploads/2021/11/FAQs-Sugarmate-11.2.21.pdf) | confirmed |
| 2021-11-30 | Dexcom Share (EU) | Trend field changed type | s2nb trend mapping broke | fixed 2021-12-01/02 (#51, #53) | s2nb #51, #52, #53 | confirmed |
| 2022-08-31 / 2023-09-28 | Medtronic CareLink (EU) | Login required MFA (Norway), then reCAPTCHA | mmc login failed for affected accounts | never fixed in mmc (#34, #47 open); mmc deprecated 2026-02-27 (#49), archive date 2026-03-31 in its README | mmc #34, #47, #49 (b7ba2c6f) | confirmed |
| 2023-06-15 | LLU | App minimum version raised (old versions stopped 2023-06-21) | Connectors had to raise their version header | 2023-06-15 same day | nslu #99, 87c4f45c | confirmed |
| 2023-05-23 / 2023-06-07 | CareLink care-partner login | Error 400 for care-partner logins | mmc failed for care partners | 2023-06-07 (#42) | mmc #39, #42 | confirmed |
| 2023-01-06 | Tandem t:connect | Requests blocked ("Web Page Blocked") | tcs failed | 2023-01-07 (v0.8.8–0.8.10) | tcs #74 | confirmed |
| 2024-03-28 | LLU | Requests from servers blocked by bot protection | nslu stopped fetching | 2024-04-02 (#131, 8d173e8f) | nslu #128 (39 comments) | confirmed |
| 2024-05-29 | LLU | Host-based blocking reported (some server addresses refused) | nslu failed on some hosts; users moved hosts | partial, per comments; no single fix | nslu #143 | partly |
| 2024-09-05 | Tandem t:connect | Authentication system changed | tcs ≤0.9 failed | 2024-09-08 (v1.0.0) | tcs #97, release v1.0.0 | confirmed |
| 2024 (date not verified) | Tandem t:connect → Tandem Source | t:connect discontinued | tcs needed a new client | v2.1.5, 2024-10-08 | tcs release v2.1.5 | partly (shutdown date not read) |
| 2024-11-15 | LLU | Minimum version raised and a new required header | nslu failed | 2024-11-15 same day (2.7.2, e406ae4a) | nslu #167 | confirmed |
| 2025-01-01 / 2025-01-31 | Sugarmate (Tandem) | Alexa skill and macOS app sunset | Not open software; a follower surface removed | not restored | [Sugarmate sunset notice](https://help.sugarmate.io/en/articles/10249780-mac-app-and-alexa-skill-sunset) | confirmed |
| 2025-07-01 | Glooko | Requests rejected by a request-rule check; by 2025-09 the v2 API returned 422 and v3 rejected v2 parameters | nsc Glooko source broken | nsc `dev` 2026-09-21 (#71), released 0.1.0 2026-09-24 | nsc #49, #51, #59, #71 | confirmed |
| 2025-10-01 (deadline 2025-10-08) | LLU | Vendor emailed users: old app versions stop on 2025-10-08; new terms of use | nslu raised its version 2025-10-02; nsc failed with 403 until its fix | nslu 2025-10-02 (#202); nsc PR 2025-10-22 (#53), landed on `dev` 2026-09-22 (#73, f52d929a), released 0.1.0 2026-09-24 | nslu #201, #202; nsc #53, #73 | confirmed |
| 2026-02-05 to 2026-02-18 | LLU | Session expiry, 429 "locked" lockouts, 30-minute gaps | nslu gaps; nsc added lockout recovery 2026-09-22 | partly mitigated (backoff); #218, #223 still open | nslu #212, #218, #223; nsc 9e17949a | partly |
| 2026-03-04 | Medtronic CareLink | CareLink moved to a new identity provider; direct credential login blocked by CAPTCHA from servers | nsc CareLink source broken | not restored in nsc: PR #54 open as of 2026-10-17 | nsc #54 | confirmed (PR text); vendor change date not verified |
| 2026-03-21 | LLU | Login can stop at a terms-acceptance step that connectors cannot complete | User must accept in the vendor app | open (#227) | nslu #227 | partly |
| 2026-04-21 (iOS), by 2026-05-16 (Android) | LLU app 5.0.0 | New API with encrypted response payloads | Connectors cannot use the 5.x API; the nslu project says it will stay on 4.x for as long as the vendor keeps it running; no 4.x shutdown date announced in the sources read | 4.x still working as of the last nslu/nsc commits read; issue #230 (2026-07-19) asks the same question | nslu discussion #228, issue #230 | confirmed that 5.0.0 encrypts and 4.x still works; a 4.x cut-off is not verified |
| 2026-06-29 | Dexcom Share | Response shape change; auth failures silent, notably for G7 accounts | nsc Dexcom source reported running while storing nothing | nsc fixes landed via 0.1.0 line (#55 closed 2026-09-22); s2nb PR #63 open | nsc #55; s2nb #63 | partly |
| 2026-06-30 | Tandem Source | Backwards-incompatible internal API change, "overnight with no warning" | tcs returned HTTP 404 | 2026-07-01 (v3.0.0) | tcs #146, release v3.0.0 | confirmed |
| 2026-10-01 | Tandem Source | A query parameter renamed | tcs returned HTTP 400 | 2026-10-01 (v3.0.3) | tcs #163, release v3.0.3 | confirmed |
| 2026-10-17 | LLU | New report "failing to launch after running for months" | not yet diagnosed | open | nslu #234 | not verified as a vendor change |

## 2. Gaps

- Medtronic Paradigm model/firmware limits for open control, 640G and 780G EU launch dates: not sourced here (maintainer's account).
- Dexcom G7 US commercial launch day (early 2023): not found in a primary source; only the 2022-12-08 clearance.
- Libre 2 CE date, Libre 3 CE month (sources say September or October 2020), Libre 3 FDA month, and Juggluco's first Libre 3 release before its public repo (2023-01-29).
- Omnipod 5: whether AAPS or any other project had public Omnipod 5 code before 2026-02-22; OmnipodKit commit 37765301 (2025-03-20) mentions an "O5 selection option" and was not examined further.
- Tandem t:connect shutdown date; Sugarmate: no shutdown of the app itself found (still releasing, 4.2.0 on 2026-03-02).
- Dexcom ONE/ONE+/Stelo, Libre 2 US vs EU firmware, Dexcom G6 "Firefly" transmitter changes (xDrip+ commits from 2021-05-16 only), Roche Accu-Chek SmartGuide pairing: not dated or sourced in this pass.
- The FDA 2019 safety communication was read through press coverage, not the FDA page.
- Maintainer's belief that LLU added or is about to add measures that break connectors: the encrypted 5.x API (April 2026) is confirmed; a date for 4.x being switched off is not.

## 3. Counts

37 rows (12 device, 25 cloud). Excluding the Paradigm baseline row, the Sugarmate Alexa/macOS sunset
and the undiagnosed 2026-10-17 report, 34 events remain: 11 device, 23 cloud.

Device (11). Generation not openly accessible for control: 3 (530G; 600 series, read-only;
770G/780G, proof of concept only). Access removed: 3 (2019 Paradigm/508 recall; 2019 and
2021/2023 Abbott DMCA notices). Access arrived late: 5, with lag in months from first launch or
clearance: Libre 2 native read about 24 (CE date unverified); Libre 3 at most about 27; Dexcom G7
passive 0.3 (xDrip+), 1.2 (Loop), 16.3 (xdripswift), direct 5.4 (xDrip+), 25.7 (Juggluco), 38.7
(xdrip-js `dev`), 46.9 (xdripswift), 47.5 (Loop `next-dev`, not on `dev` or `main`); Omnipod DASH
from the 2018-06-04 clearance 32.2 (AAPS start), 43.9 (AAPS 3.0.0), 39.1 (OmniBLE start), 55.3
(Loop 3.0.0); Omnipod 5 48.8 (OmnipodKit `dev`).

Cloud (23): LibreLinkUp 8, Tandem 6, CareLink 4, Dexcom Share 3, Dexcom-to-Sugarmate 1, Glooko 1.
Time to a fix in at least one connector: 7 days or less for 11 (including LibreLinkUp
October 2025, fixed in nightscout-librelink-up before the deadline but only 11 months later in
nightscout-connect); 15 days for 1 (CareLink care partner); about 5 weeks for 1 (Sugarmate, US);
about 7 weeks for 1 (Share 2020); 2.8 months for 1 (Share 2026 in nightscout-connect); 14.7 months for 1
(Glooko in nightscout-connect); not dated for 1 (t:connect to Tandem Source). Not fixed or only
partly mitigated as of 2026-10-17: 5 (CareLink MFA/CAPTCHA in minimed-connect; CareLink 2026 in
nightscout-connect; LibreLinkUp host blocking, lockouts and terms step). Not yet a loss: 1 (LibreLinkUp 5.x encrypted API;
the 4.x API was still working in the sources read).
