# The ecosystem stack, measured — 2026-09-30

*Contributor-facing. **Record** (a snapshot; not rewritten as the world moves). Measured 2026-09-30
from fresh clones of 63 repositories listed in `tools/programme/stack-census/repos.tsv`, each at the
commit named in the census table; written against this repository at `df5e2ade`. The effort figures
in §6 are **estimates** with their assumptions stated, not measurements. The legal and regulatory
texts in the cloud annex are quoted for counsel and a regulatory professional to review; nothing
here is a legal or regulatory conclusion. The proposal that uses this record is
[QUALITY-SYSTEM](../../00-overview/QUALITY-SYSTEM.md).*

## 1. What this measures

The question: across the whole Nightscout ecosystem stack, from the radio link to a sensor or pump
up to the cloud services people use to get their data back, what validation and verification (V&V)
exists today, where the same work is done several times over, and how much work a shared
quality-control system would take.

The stack, bottom to top, as the census groups it:

| layer | what it holds | repositories in the census |
|---|---|---|
| device | BLE and radio drivers for CGMs and pumps, simulators, protocol decoding, pairing cryptography | 36 |
| controller | AID apps and algorithms (Loop, Trio, AndroidAPS, iAPS, oref0) | 7 |
| cloud | connectors that bring data out of vendor clouds, and uploaders to Tidepool | 9 |
| server | Nightscout-compatible servers and gateways | 3 |
| follower | remote-monitoring and caregiver apps, a watch face | 4 |
| reports | reporting and build-support scripts | 3 |

Three annexes hold the detail, each with file paths and commits:
[device layer](stack-census-2026-09-30/device-layer.md),
[cloud layer](stack-census-2026-09-30/cloud-layer.md), and
[histories, funders and consensus methods](stack-census-2026-09-30/histories.md) (sourced from the
web, every page read 2026-09-30).

**How to re-run.**

```
tools/programme/stack-census/fetch.sh
python3 tools/programme/stack-census/census.py --asof 2026-09-30
```

`fetch.sh` makes blobless clones under `externals/stack/` (history kept, contents fetched for the
measured branch). `census.py` measures the development branch: the default branch, unless `dev` or
`develop` had more commits in the trailing year. Its docstring defines every column. The full table
is [`results/census-2026-09-30.md`](../../../tools/programme/stack-census/results/census-2026-09-30.md);
this record quotes it and does not restate it.

## 2. Activity and test surface, by layer

From the census table. A fork kept level with upstream (MedtrumKit, two listings at one commit) is
counted once. "Authors" are distinct human names across the layer, after `.mailmap`; one person
active in several repositories counts once, and one person under two spellings counts twice.
Automation accounts (GitHub Actions, Dependabot, translation and build bots) and coding agents are
counted separately and are not authors.

| layer | repositories | active in the last 12 months | commits, 12 months | of which automation | of which coding agent | human authors, 12 months | CI runs tests | test declarations |
|---|---|---|---|---|---|---|---|---|
| device | 36 | 32 | 4,123 | 10 | 287 | 67 | 7 | 4,622 |
| controller | 7 | 7 | 5,153 | 412 | 124 | 90 | 2 | 14,225 |
| cloud | 9 | 9 | 579 | 2 | 12 | 24 | 2 | 2,017 |
| server | 3 | 2 | 4,141 | 222 | 8 | 60 | 2 | 14,391 |
| follower | 4 | 3 | 583 | 166 | 0 | 21 | 1 | 240 |
| reports | 3 | 3 | 53 | 0 | 0 | 6 | 0 | 0 |
| **all** | **62** | **56** | **14,632** | **812** | **431** | **219** | **14** | **35,495** |

What the table shows:

- **The stack is active at every layer.** 56 of 62 repositories had commits in the last year. The six
  without are historical or finished tools (decocare, the RileyLink firmware, openomni, dana-simulator,
  the nsfitbit watch face, the roles gateway).
- **Test declarations are concentrated.** Three repositories hold 26,320 of the 35,495 declarations:
  Nocturne (12,116), AndroidAPS `dev` (11,936) and cgm-remote-monitor `dev` (2,268). A declaration is
  a written test, not a passing one, and patterns undercount data-driven tests (census docstring).
- **CI runs tests in 14 of 62 repositories.** In the device layer, CI runs driver tests for
  AndroidAPS, xDrip+, pumpX2, controlX2, faketandem, JavaSake, JavaPumpConnector and xdrip-js. The
  Swift driver kits have test suites that no CI found in the clones runs: Trio's test workflow and the
  LoopWorkspace build do not include the kits' test targets (device annex §1.1–1.2).
- **Most repositories have a small number of regular authors.** In 25 of the 56 repositories with human commits in the year, one
  author made 80% or more of the human-authored commits of the year; the per-repository figures are
  in the census table for every repository alike. This describes where the knowledge sits, not the
  quality of the work.

## 3. Device layer

Detail: [device annex](stack-census-2026-09-30/device-layer.md). Cryptography is named by protocol
family only; this public record holds no keys, constants, command sequences or bypass steps.

**The same protocols are implemented many times.** 14 device protocols have two or more independent
implementations, 41 implementations in all (a port counts once and is marked):

| protocol | implementations | shared test vectors between them |
|---|---|---|
| Dexcom G5/G6 | 5 (CGMBLEKit, xDrip+, xDrip4iOS, xdrip-js, DiaBLE) | at most 1 literal between any pair |
| Libre 2 | 5 (LibreTransmitter, xDrip+, xDrip4iOS, Juggluco, DiaBLE) | none |
| Dexcom G7 / ONE+ pairing (EC-JPAKE family) | 4 that authenticate (xDrip+, xdrip-js port, xDrip4iOS, Juggluco) | none |
| Libre 3 | 3 (LibreCRKit, Juggluco, DiaBLE) | none; LibreCRKit tests AES-CCM against the RFC 3610 vector |
| Omnipod Eros | 3 drivers and a decoder (OmniKit, OmnipodKit, AndroidAPS; openomni) | 165 and 46, from copied tests |
| Omnipod DASH | 3 (OmniBLE, OmnipodKit, AndroidAPS) | 191 and 58, from copied tests |
| Medtronic 5xx/7xx | 3 (MinimedKit, AndroidAPS, decocare) | none |
| Medtronic 7xxG pairing | 2 (PythonSake, JavaSake) | 6, from a deliberate cross-check, plus NIST and RFC vectors |
| Dana, Medtrum pump, Medtrum CGM, Eversense, Accu-Chek SmartGuide, RileyLink host | 2 each | Medtrum pump 7; the others none |

So for 10 of the 14 protocols, no two implementations test against the same bytes. The one
deliberate cross-implementation check is OpenMinimed's: JavaSake replays PythonSake's recorded
handshake and runs known-answer tests from NIST SP 800-38A and RFC 4493.

**Known-answer tests against public standards are rare.** Besides JavaSake and LibreCRKit, there are
AndroidAPS's DASH `MilenageTest` and AndroidAPS `dev`'s `CryptoPrimitivesVectorsTest`, which runs one
vector set against both its JVM and iOS crypto "so that the two cannot quietly drift apart". None was
found for X25519, P-256 key agreement or signatures, HKDF, or EC-JPAKE.

**Simulators.** faketandem (Tandem, Go) is the most complete: a virtual transport that runs in CI, a
controllable clock, a pump-side request log, fault injection, and an integration job against pumpX2.
It was built from the `pod` simulator (its README: "based on the 'pod' OmniPod simulator"). `pod`
(Omnipod DASH) and dana-simulator (Dana, no commits since 2024-10-01) are Raspberry Pi BLE rigs with
2 and 0 tests. No simulator exists for any Dexcom, Libre or Medtronic-over-RileyLink device.

**Not found anywhere in the device layer:** fuzzing harnesses, automated hardware-in-the-loop rigs,
and per-release test reports.

**Newer work in the census:** loopandlearn's kits (OmnipodKit, including an Omnipod 5 pod type;
DanaKit, MedtrumKit, EversenseKit, AccuChekKit from 2026-02, LibreCRKit and LibreLoop from 2026-05),
OpenMinimed's Medtronic 7xxG connectors (from 2025-12), faketandem (124 commits since 2026-06-30),
and a CareLevo pump driver in AndroidAPS `dev` (from 2026-04-21, 2,127 test declarations).

## 4. Cloud layer

Detail: [cloud annex](stack-census-2026-09-30/cloud-layer.md). It describes mechanisms only; it holds
no credentials, account identifiers or request recipes.

**Fourteen code bases log in to vendor clouds**, and the same cloud is reached many times:

| vendor cloud | implementations in the corpus |
|---|---|
| Dexcom Share | 6, in four languages (5 once share2nightscout-bridge is archived) |
| LibreLinkUp | 5 (a sixth, xDrip+ WebFollow, is set by a downloaded template) |
| Medtronic CareLink | 4 current, plus one deprecated |
| Tandem Source | 1, plus a port that follows it |
| Glooko | 2 in the census, 4 more elsewhere in the workspace |
| Dexcom developer API (the documented, OAuth route) | 1 (Tidepool platform) |

**Vendor changes, counted from commit subjects, 2023-09-30 to 2026-09-30:** 18–19 LibreLinkUp events
across five clients, 7 CareLink events in xDrip+ alone, and 5 Tandem events in tconnectsync. Each
client meets the same change on its own schedule: one LibreLinkUp change was fixed in a
nightscout-connect branch on 2025-10-21 and reached a release on 2026-09-24; the account-id change
reached two clients four months apart. No shared notice channel between the clients appears in the
repositories. These are read from commit subjects, not reproduced against the vendors.

**Tests are per project, mostly synthetic.** Only tconnectsync tests parsers against captured vendor
data; only nightscout-connect runs a connector against real Nightscout storage in CI. No fixture
format is shared between projects, and nothing checks on a schedule for a vendor change before
users notice it.

**Documented routes exist but are narrower** than the follower routes the connectors use: the Dexcom
developer API delivers data one hour late in the US and three hours elsewhere, with a five-user
"Limited Access" path for individuals; exports from LibreView, Tandem Source and Glooko are files on
demand; Health Connect has no insulin record type. Details and sources are in the annex, §2.1.

**Rules about getting data out** (quoted for counsel, annex §2.2): GDPR Articles 15 and 20; the EU
Data Act, which applies from 2025-09-12, with the design duty for products placed on the market after
2026-09-12, and a Commission FAQ that names medical devices among connected products; the EHDS; the
HIPAA right of access; the US information-blocking rule; and the FDA classifications for secondary
CGM displays (21 CFR 862.1350) and for interoperable CGMs, controllers and pumps (862.1355, 862.1356,
880.5730), whose special controls require validated interface specifications and a process for
sharing them with connected devices.

## 5. Wearables and health platforms

From a search of the clones (both annexes):

| source | in the ecosystem code |
|---|---|
| Apple HealthKit | Loop, LoopKit, Trio, iAPS, xDrip4iOS, LoopFollow, LoopCaregiver, nightguard, DiaBLE, TidepoolService |
| Android Health Connect | xDrip+ (glucose, heart rate, steps, exercise, sleep, nutrition); Juggluco (glucose) |
| Garmin | watch apps and data fields in AndroidAPS, Trio, iAPS, Juggluco; no Garmin cloud client |
| Wear OS, Apple Watch | AndroidAPS, xDrip+, Juggluco, controlX2; Loop, Trio, iAPS, xDrip4iOS, nightguard, LoopCaregiver, LoopFollow |
| Fitbit | the nsfitbit watch face |
| Oura | Tidepool platform (partner API); listed as coming soon in Nocturne |
| MyFitnessPal | a Nocturne connector |
| WHOOP, Strava | none found |

Vendor terms read the same day: Oura's API needs an active membership; WHOOP starts new apps in a
ten-member sandbox; Garmin's health APIs are "only for business use"; the Fitbit Web API is turned
off on 2026-10-30; Google Fit support ends at the end of 2026 (cloud annex §3.2).

## 6. What a shared quality-control system would take (estimates)

The two annexes each build an estimate from the counts above. **These are estimates, not
measurements.** They assume an engineer who knows the protocol and host language, no new reverse
engineering, vectors extracted from existing test literals where possible, de-identified captures
only, and they exclude maintainers' review time and counsel's time.

| layer | pieces | one-time, person-weeks | ongoing |
|---|---|---|---|
| device | a language-neutral vector corpus per protocol and a loader per language; adapters in each implementation; crypto known-answer tests from public standards; fixed-randomness handshake transcripts; `pod` and dana-simulator brought to faketandem's level; five new simulators; parser fuzzing in CI; CI for about 15 repositories without it; a hardware-in-the-loop rig; per-release records | 127–316 | 0.1–0.2 FTE, plus 0.5–1 day per driver release |
| cloud | per-vendor contract notes; shared recorded-fixture suites with refusal cases; adapters in five implementations; a read-only change canary with consenting accounts; per-release connector reports; a shared connector lab | 40–72 | 0.3–0.5 FTE, plus 1–2 person-weeks per vendor change (6–15 a year at the §4 rate) |
| **the two layers** | | **167–388 (about 3–7.5 person-years)** | **0.4–0.7 FTE, plus 6–30 person-weeks a year of vendor changes** |

Not estimated here: the server and shared-contract layer, where the
[sponsored-team proposal](../../00-overview/SPONSORED-TEAM-PROPOSAL.md) sizes the review and
compatibility work for cgm-remote-monitor; and controller validation on real AID rigs.

The widest range is new simulators (30–90 person-weeks). faketandem's own history, which has 362
commits since 2021 and a gap analysis that still listed about 40 unhandled control requests in
2026-04, shows that a full pump simulator takes months.

## 7. Limits of this record

- Counts are pattern-based. Test declarations undercount data-driven tests, Python doctests and
  self-tests; the device annex §0 gives its own counting rules.
- Author names are not de-duplicated across spellings, and one person may appear in several layers.
- The census picks the development branch by commit count; a project that develops elsewhere
  (a personal fork, a feature branch) reads as quieter than it is.
- CI detection reads workflow files for a test step. CI configured outside the repository (for
  example in a workspace that builds the kit) is counted only where the annexes found it.
- The vendor-change counts come from commit subjects, which can overstate or understate cause.
- The repositories chosen are a census of the stack as known to this repository on 2026-09-30,
  not the whole ecosystem; add rows to `repos.tsv` and re-run.
