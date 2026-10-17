# Device simulators and app-level test rigs, measured — 2026-10-17

*Contributor-facing. **Record** (a snapshot; not rewritten as the world moves). Measured 2026-10-17
at LoopKit/g7sim `7c039de5` (2026-10-12), LoopKit/pod `a491a5ea` (2026-10-12),
jwoglom/trio-test-harness `c3c1bfe7` (2026-10-17) and jwoglom/faketandem `34c94019` (2026-10-17),
written against this repository at `d9167f59`. It brings the device-simulator part of the
[stack census of 2026-09-30](stack-census-2026-09-30.md) up to date; the census figures for these
repositories and their neighbours were re-run the same day
(`tools/programme/stack-census/results/census-2026-10-17-simulators.md`). The proposal that uses
both records is [QUALITY-SYSTEM](../../00-overview/QUALITY-SYSTEM.md). Cryptography is named by
family only.*

Per-repository detail:
[g7sim](../../10-domain/g7sim-deep-dive.md) ·
[LoopKit/pod](../../10-domain/omnipod-pod-simulator-deep-dive.md) ·
[trio-test-harness](../../10-domain/trio-test-harness-deep-dive.md).

## 1. What this measures

The question: which parts of an end-to-end virtual test of an AID app now exist, with no person's
data and no hardware, from a simulated sensor and pump through a real app build to the records it
uploads to Nightscout? Which parts already work together, and where are the gaps between them?

## 2. The pieces

| piece | role | transports | control surface | tests (run 2026-10-17) | CI | licence |
|---|---|---|---|---|---|---|
| [LoopKit/g7sim](https://github.com/LoopKit/g7sim) | Dexcom G7 / ONE+ / Stelo **sensor side**: advertising schedule and lockout, display slots, readings with warm-up, expiry, a 24-hour backfill store and a calibration offset, an identity certificate chain from a dummy CA, EC-JPAKE pairing on P-256 and an AES challenge; models the iOS wake, suspend and relaunch behaviour that decides whether a backgrounded app gets a reading | BLE peripheral on Linux (vendored `paypal/gatt`); `impossible`: an app in the iOS Simulator through [ImpossiBLE](https://github.com/mickeyl/ImpossiBLE)'s socket | HTTP API and web page: new sensor, glucose mode (sine, fixed, walk), sensor state | 33 `func Test`, 33 pass, clean under `-race` and `go vet` | none | MIT |
| [LoopKit/pod](https://github.com/LoopKit/pod) | Omnipod DASH **pod side**: pairing and session crypto (EAP-AKA/Milenage, X25519, AES-CCM, AES-CMAC), command decoding, pod state (reservoir, delivered insulin, pod progress, alerts, faults, the 80 h fault), responses built from that state | BLE peripheral on a Raspberry Pi; `impossible` (since #21, 2026-10-12) | control panel and JSON API: set reservoir and pod age, raise alerts, set or clear a fault, crash on the next command | 7 functions in 5 files, all pass; `-race -count=5` clean | `go test ./...` since `1d34e9b` (2026-05-23) | GPL-3.0 |
| [jwoglom/faketandem](https://github.com/jwoglom/faketandem) | Tandem t:slim X2 / Mobi **pump side**, built from the `pod` code base (shared root commit `715833c`) | BLE on Linux; a virtual TCP/JSON GATT transport for Mac and CI | integration-harness HTTP API: controllable clock, pump-side request log, pump-initiated actions, fault injection armed per message | 933 test declarations in 345 files (census counter; 929 by an independent count); the message-library parity suite passes in about 2 s | `go vet`, unit tests with `-race`, a job that runs the parity cases against pumpX2's jar, lint, ARM cross-build | GPL-3.0 |
| [jwoglom/trio-test-harness](https://github.com/jwoglom/trio-test-harness) | builds Trio (or Loop with `--app loop`) from any branch, PR or submodule PR; installs and launches it with onboarding pre-seeded; adds the app's **built-in** CGM and pump simulators; drives the UI; writes an HTML report or a PR comment; a coding agent does the PR-specific testing and a second pass reviews the screenshots | iOS Simulator (`simctl` + WebDriverAgent, idb fallback); jailbroken iPhone (VNC + OCR); any iPhone through iPhone Mirroring (pairing not completed) | `th` CLI, 37 commands and 56 subcommands, incl. `th db` (read and change the app's database on the Simulator) | none in the repository | one `workflow_dispatch` workflow on a self-hosted macOS runner, which runs an app smoke test, not tests of the harness | **none** (no LICENSE file); public; read and link only |

**What runs where.** The three Go simulators build and test on Linux with no radio, Mac or
network. On a Mac, g7sim and pod each serve an app in the iOS Simulator with no radio.
trio-test-harness needs a Mac with Xcode.

## 3. How they join today

```
                  iOS Simulator (Mac)                            Linux, CI or Mac
 ┌──────────────────────────────────────────────┐
 │ Loop (LoopWorkspace next-dev)                 │
 │   G7SensorKit next-dev ─┐                     │
 │   OmnipodKit next-dev ──┤ CoreBluetooth       │
 │                         ▼                     │
 │                 ImpossiBLE ── unix socket ────┼──▶ impossible-mux ──▶ g7sim   (G7 sensor side)
 └──────────────────────────────────────────────┘                    └─▶ pod     (DASH pod side)

 TandemKit / pumpX2 client ── virtual TCP/JSON GATT ──▶ faketandem (Tandem pump side)

 trio-test-harness ── drives Trio or Loop ── built-in Glucose/Pump Simulator only; Nightscout skipped
```

- **One join works now: Loop with a simulated G7 and a simulated DASH pod together.**
  `impossible-mux` (in g7sim, `cmd/impossible-mux`) takes the single socket ImpossiBLE gives the
  app and fans it out to g7sim and pod, each of which sees the app as its only client. With
  `-suspend` the mux stops and wakes the app as iOS would. g7sim's README states that Loop pairs,
  reads and reconnects in the Simulator. This record did not reproduce that (no Mac); it did run
  g7sim's and pod's `impossible` transports on Linux against scratch clients.
- **The app side of that join exists only on `next-dev` branches.** G7SensorKit's direct
  connection is on `next-dev` (`e17129d`), merged there as `7da3b69` (#67, 2026-09-20). OmnipodKit's
  ImpossiBLE detection (`e60e0ab`) is on `next-dev` and `simulator-bluetooth`. LoopWorkspace
  `next-dev` (`1561bff0`) pins both. LoopWorkspace `dev` and `main` and Trio `dev` and `main` pin
  G7SensorKit `dd91f46` (passive) and OmnipodKit `4e923d7` (pod commands mocked in the Simulator).
- **trio-test-harness does not attach any of the external simulators.** It uses only the apps'
  built-in simulators, `simctl launch` passes no environment, and there is no reference to g7sim,
  pod or ImpossiBLE. A faketandem stress lane was added in `dd69a8d` and moved out of the
  repository seven minutes later in `83729b5` (both 2026-10-01). Its build hooks remain in
  `build.py` but have no CLI flags.
- **faketandem no longer needs pumpX2 to run.** `d60279c` (2026-10-14) ports pumpX2's message
  library and its EC-JPAKE to Go and makes them the default. The port is held to pumpX2's jar by
  recorded answers: **4,819 parse and 3,142 encode cases in 282 files**. Every `go test` checks
  them against the recorded answers, and CI checks them live against the jar. Pairing is checked
  both ways: pumpX2's client against the Go pump side, and a Go client against pumpX2's server.
  In this record, editing one recorded answer failed exactly that class's test and named the edited
  case; restoring it passed. The port is derived from pumpX2, so it is a second implementation held
  to the first, not an independent design.

## 4. What reaches Nightscout

**No harness run uploads anything today.** trio-test-harness's pre-seeding skips Nightscout setup,
and its onboarding walk taps "Skip Nightscout Setup". Trio keeps the URL and secret in the
Keychain, and no `th` command writes them. Nothing is checked on the server side.

**What an app driven by these simulators would upload**, read from the code and not run:

| source | records (inferred from code) |
|---|---|
| Loop + g7sim | `entries` (sgv), one per reading including backfilled ones, with a `device` string that marks the sensor as simulated ("g7sim (Simulator)"), so test uploads can be told apart from real-sensor data; a Sensor Start treatment; "CGM: <state>" Note treatments driven by the sensor's algorithm state. How the backfill flag and received time serialise was not checked |
| Loop + pod | `treatments`: bolus, temp basal, a suspend as a zero-rate temp basal with `reason: "suspend"` (a resume uploads no treatment), a Site Change for a new pod. `devicestatus.pump`: reservoir (at or below 50 U), suspended, bolusing, and a display override for a pod fault or expiry; a pod fault creates no Note treatment. pod's basal and temp basal do not draw down its reservoir (only boluses do), so the reservoir in such a run follows boluses only |
| Trio (any source) | `entries`, `treatments`, `devicestatus` and `profile` (`NightscoutManager.swift`, Trio `e41c9db37`) |

This repository already has the receiving end, running on synthetic data:
[`tools/lab/rc-soak`](../../../tools/lab/rc-soak/README.md) (two Nightscout arms under the same
synthetic traffic, including Loop and Trio shapes written by its own `traffic.js`),
`tools/mock_nightscout.py`, the per-client mappings in `mapping/`, and the schemas and quirks in
`specs/`. An app run against a lab Nightscout would produce **real client upload shapes from no
person's data**, which is the evidence that `traffic.js` and the mappings do not yet have.

## 5. The census picture, updated

| census 2026-09-30 statement | 2026-10-17 | kind | evidence |
|---|---|---|---|
| "No simulator exists for any Dexcom … device" | g7sim (G7, ONE+, Stelo sensor side). Still none for Libre or Medtronic over RileyLink. | new since | g7sim first commit `045b94f` (2026-10-09) |
| `pod`: the census row is loopandlearn/pod, 0 commits in 6 months, 0 workflows, no CI covers it | the upstream is LoopKit/pod; loopandlearn/pod `ec13f46` is an ancestor with no commits of its own. On 2026-09-30 LoopKit/pod was 9 commits ahead (4 non-merge) and had run `go test ./...` in CI since 2026-05-23 | **wrong on the day** (the fork was measured) | `git log ec13f46..e113d70`; `1d34e9b`, `f1f6138` (#18), `9c6ac56` (#19) |
| `pod`: 2 tests | 7 functions in 5 files, all pass. At the fork's head `ec13f46`, `go test ./...` fails under Go 1.23 (three packages fail vet; `Test_PrintfromByteArray` fails) | new since; the 09-30 count was not a run | §5 of the pod deep dive |
| `pod` is a Raspberry Pi BLE rig with no virtual transport | an `impossible` transport for the iOS Simulator, a control panel and JSON API, and fault and alert advertising | new since | #21–#23 (2026-10-12) |
| G7SensorKit is passive and needs the vendor app | true of `main` (`dd91f46`), which the census read. `next-dev` authenticates directly (EC-JPAKE on P-256, AES challenge): **5 implementations of G7 authentication, 4 of them on default branches** | branch scope | `7da3b69` (#67, 2026-09-20); `git merge-base --is-ancestor 7da3b69 0574a74` exits 1 |
| no authentication vectors are shared across G7 implementations | g7sim and G7SensorKit `next-dev` share 8 test literals: G7SensorKit's 2 AES-challenge known-answer cases and 2 captured version replies. OpenSSL reproduces both AES cases | new since | g7sim `g7/jpake_test.go`; G7SensorKit `G7AuthCryptoTests.swift` |
| no EC-JPAKE known-answer test | still none. g7sim's and G7SensorKit's EC-JPAKE tests check agreement against a client in the same repository. In g7sim that client reuses g7sim's own hashing, so breaking that hashing passes all 33 tests (checked in this record's ablation) | holds | g7sim deep dive §5.3 |
| faketandem uses pumpX2's codec for parsing, so the two are not independent | faketandem carries a Go port held to pumpX2 by 7,961 recorded cases, with pumpX2 optional. The two now **check each other**, though the port is derived from pumpX2 | new since | `d60279c`, `9a12b49` (2026-10-14); §3 |
| no automated hardware-in-the-loop rigs; no per-release test reports | both still hold. trio-test-harness is a **simulator-in-the-loop** and on-device UI rig with the apps' software simulators; no radio or driver transport is in its loop. It reports per PR, on demand, not per release | holds | trio-test-harness deep dive §13 |

**What the census counter does not see in these repositories.** `sim_paths` counts paths named like
simulators *inside* a repository, so a repository that is itself a simulator reads 0 (pod) or 1
(g7sim). `ci_runs_tests` reads True for trio-test-harness because `test` appears in its workflow's
name; the workflow tests the app, not the harness. faketandem's figure includes four lowercase Go
helpers (`testBridge` ×2, `testHarness`, `testCapture`) that the Swift test pattern matches. Agent
commits for trio-test-harness are 7 by author and 49 of 71 by `Co-Authored-By` trailer; the census
counts authors only. The counter was not changed, so the 09-30 comparisons hold.

**Census figure corrected.** The census credits AndroidAPS `omnipod/dash` with 58 vectors shared
with OmniBLE. Re-run at the census commits (AndroidAPS `dev` `550605ee36`, OmniBLE `29358d5`), `dash`
shares 14. 58 is the count over all of AndroidAPS `pump/omnipod/`: 44 in `eros` tests, 14 in `dash`,
none in `common`. The figures are the same on `master` `598e2eb39c` and on `dev` `7e1d537d`. The same
method (`tools/programme/stack-census/hexvec.py`) reproduces OmniBLE∩OmnipodKit 191,
OmniKit∩AndroidAPS 46, OmniKit∩OmnipodKit 165 and G7SensorKit∩xdripswift 2; adding one OmniBLE
literal to a scratch copy of an AndroidAPS `dash` test raises the count to 15. The census snapshot is
corrected in place.

## 6. The joins that are missing

Each item names the project whose maintainers decide it.

| gap | whose decision | what it would enable |
|---|---|---|
| G7SensorKit direct connection and OmnipodKit's ImpossiBLE detection exist only on `next-dev` | LoopKit and loopandlearn maintainers; Trio maintainers for Trio's pins | the `impossible-mux` setup from LoopWorkspace `dev` and from Trio |
| trio-test-harness attaches only built-in simulators | the harness owner | the same PR run with g7sim, pod or faketandem in the loop, so driver code is exercised, not mocked |
| no harness run configures a Nightscout; nothing checks what arrives | the harness owner for the setting; this repository for the receiving lab | app-produced upload shapes checked against `specs/` and `mapping/`, and a corpus to replace the hand-written Loop and Trio shapes in rc-soak's `traffic.js` |
| g7sim has no CI, though its suite needs no radio, Mac or network | LoopKit | its 33 tests on every change |
| no shared EC-JPAKE transcript for G7 (G7SensorKit, g7sim, xDrip `libkeks`, xdrip-js, xdripswift, Juggluco) | each project | a fixed-randomness transcript every G7 implementation runs, as JavaSake and PythonSake do for SAKE |
| g7sim and pod have no frame-level faults and no controllable clock; faketandem has both | LoopKit (g7sim, pod) | the anomaly cases (dropped, duplicated and corrupted frames, disconnect mid-command, clock skew) for G7 and DASH |
| g7sim records but does not enforce the client's EC-JPAKE proofs or display signature; a client that broke a constraint the real sensor checks would pair with g7sim | LoopKit | the emulator rejecting what a real sensor rejects |
| trio-test-harness has no licence | the harness owner | reuse of its run-record shape, sandbox settings or flows elsewhere |
| run records (`run.json`, `highlights.json`) have no schema, and `passed` from the smoke stage stands if the agent step does not finish | the harness owner | a record that fits QUALITY-SYSTEM §4.1 (identity, inputs, procedure, outputs, known gaps, status) |

## 7. Reproduce

```bash
# clones and the lockfile entries
python3 tools/bootstrap.py status | grep -E 'g7sim|pod|trio-test-harness'
# census figures for the seven repositories (filtered manifest, unchanged census.py)
python3 -I tools/programme/stack-census/census.py --asof 2026-10-17 --out <dir>   # see results/census-2026-10-17-simulators.md
# simulator suites (offline)
(cd externals/g7sim && GOPROXY=off GOFLAGS=-mod=mod go test -count=1 ./...)
(cd externals/pod && go test -mod=vendor -count=1 ./...)
# faketandem parity cases and suite
cd externals/stack/jwoglom__faketandem
find pkg -path '*/testdata/*.jsonl' | xargs cat | grep -c '"parse"'    # 4819
find pkg -path '*/testdata/*.jsonl' | xargs cat | grep -c '"encode"'   # 3142
go test -mod=vendor -count=1 ./pkg/pumpx2/messages/...
```
