# Omnipod DASH Pod Simulator (LoopKit/pod) Deep Dive

*Contributor-facing. Measured 2026-10-17 at LoopKit/pod `a491a5ea` (2026-10-12; 183 commits; GPL-3.0; GitHub lists it
as a fork of randallknutson/pod). Other repositories cited: loopandlearn/pod `ec13f460` (2025-12-05),
randallknutson/pod `main` `12c54c2` (2022-12-06), jwoglom/faketandem `34c9401` (2026-10-17), loopandlearn/OmnipodKit
`main` `4e923d7` (2026-09-19), `dev` `928bb79` (2026-10-13) and `next-dev` `c21a077` (2026-10-14), LoopKit/OmniBLE
`29358d5` (2026-05-29), nightscout/AndroidAPS `dev` `7e1d537d49` (2026-09-23) and `master` `598e2eb39c`
(2026-08-02), LoopKit/LoopWorkspace `f841285` (2026-09-19) with NightscoutService `fe075ef` (2026-09-17),
nightscout/Trio `e41c9db37` (dev, 2026-09-22), LoopKit/g7sim `7c039de` (2026-10-12), jwoglom/trio-test-harness
`c3c1bfe` (2026-10-17); this repository at `d9167f59` (2026-10-16).*

> **Repository**: [LoopKit/pod](https://github.com/LoopKit/pod)
> **Language**: Go (module path `github.com/avereha/pod`, `go 1.15` in `go.mod`, dependencies vendored)
> **Purpose**: the pod side of Omnipod DASH: a program that a Loop or Trio phone (or an app in the iOS Simulator) pairs
> with, primes and runs as if it were a pod
> **Source**: `externals/pod/`

---

## 1. Summary

- `pod` plays the **pod** in the Omnipod DASH protocol. It pairs, runs the session cryptography, decodes the
  controller's commands, keeps pod state (reservoir, delivered insulin, pod progress, delivery flags, alerts, fault,
  age) and builds status responses from that state.
- Two transports: a BLE peripheral on a Linux Bluetooth adapter (a Raspberry Pi in the README), and, since 2026-10-12,
  **an iOS Simulator transport** over [ImpossiBLE](https://github.com/mickeyl/ImpossiBLE)'s Unix socket, so an app in
  the iOS Simulator on a Mac talks to it with no radio.
- A **control panel** and JSON API on port 8080 (`GET /status`, `POST /command`) set the reservoir and pod age, raise
  alert slots, set or clear a pod fault code, and crash the process on the next state-changing command, before or after
  it is applied.
- The pod advertises a fault or a firing alert the way a real pod does (2nd service UUID `C00A` / `C005`, plus
  manufacturer data), hangs up after 3 minutes without a command, and since 2026-10-12 hangs up, rather than exiting,
  on a message it cannot use.
- **Tests:** 7 test functions in 5 files at `a491a5e`, all passing (§7). A GitHub Actions workflow runs `go test ./...`
  on pushes and PRs since 2026-05-23.
- **Lineage:** randallknutson/pod → LoopKit/pod → loopandlearn/pod. LoopKit/pod is where PRs merge. loopandlearn/pod's
  `main` is an older LoopKit/pod commit with no commits of its own (§2).
- **Not modelled:** basal and temp-basal insulin draw from the reservoir, the delivery rates themselves, alert timers,
  pod-side rejection of commands, battery, transport-level faults, a controllable clock (§4).
- jwoglom/faketandem shares this repository's root commit. The mechanisms compare in §8.
- `pod`'s own hex literals and test hex appear almost nowhere in the DASH driver test suites (§9).
- The iOS Simulator path needs OmnipodKit's ImpossiBLE detection, which is on OmnipodKit `next-dev` and not in the
  `4e923d7` that LoopWorkspace and Trio pin (§10).

## 2. Lineage and which repository is canonical

| Repository | GitHub `fork` / parent | Created | Last push | `main` head |
|---|---|---|---|---|
| randallknutson/pod | not a fork (root) | 2021-12-01 | 2025-05-19 | `12c54c2` (2022-12-06) |
| LoopKit/pod | fork of randallknutson/pod | 2022-02-10 | 2026-10-12 | `a491a5e` (2026-10-12) |
| loopandlearn/pod | fork of LoopKit/pod (source randallknutson/pod) | 2023-12-21 | 2026-01-28 | `ec13f46` (2025-12-05) |

Source: `gh api repos/<owner>/pod`, 2026-10-17. The README notes that the project began as a fork of a "0pen-dash"
repository that its owner later removed. The first commit, `715833c` (2021-02-08), is also the first commit of
jwoglom/faketandem.

History comparison (a scratch clone of LoopKit/pod with the other two added as remotes):

- **loopandlearn/pod `main` is an ancestor of LoopKit/pod `main`.** `git merge-base` is `ec13f46` itself, and
  `git log LoopKit/main..loopandlearn/main` is empty. The fork has no commits that LoopKit/pod lacks, on any branch
  fetched from GitHub.
- **randallknutson/pod `main` (`12c54c2`) is contained in LoopKit/pod.** LoopKit/pod is 35 commits ahead of it.
  randallknutson/pod also has a `five` branch with 29 commits not in LoopKit/pod (last 2025-05-19). LoopKit/pod PR #17,
  "O5 pod simulator support", was closed unmerged on 2026-05-24.
- **LoopKit/pod commits dated on or before 2026-09-30 that are not in loopandlearn/pod** (9 commits, 4 of them
  non-merge):

| Commit | Date | Change |
|---|---|---|
| `1d34e9b` | 2026-05-23 | Add a GitHub Actions workflow that runs `go test ./...` |
| `c797a81` | 2026-05-23 | Fix `go vet` errors and the message test so CI passes |
| `e352d81` | 2026-05-24 | Merge PR #16 |
| `f1f6138` | 2026-08-25 | Re-establish the session when the phone reconnects (#18) |
| `9c6ac56` | 2026-09-07 | Raise fault `0x1C` automatically once the pod is 80 hours old |
| `e113d70` | 2026-09-07 | Merge PR #19 |

  (`git log --format='%h %cI %s' ec13f46..e113d70`; the commits after 2026-09-30 are `3f82784`, `1ace0cf` and
  `a491a5e`, all 2026-10-12.)

So on 2026-09-30 LoopKit/pod already had CI, a passing test run and four changes that loopandlearn/pod lacked. LoopKit/pod
is also the repository that the README, LoopKit/g7sim's README and g7sim's `impossible-mux` refer to, and the only one
of the three with PRs merged in 2026.

## 3. Changes since December 2025

| PR / commit | Date | Change |
|---|---|---|
| #15 (`d6c2aab`, `e2df7ea`, `2eadb44`) | 2025-12-03 to 05 | Report delivery suspended when a pod fault is set; regroup the type-2 status response; move pod progress to "running, below 50 U" when the reservoir reaches 50 U |
| #16 (`1d34e9b`, `c797a81`) | 2026-05-23 | CI workflow; `go vet` format-verb fixes in `main.go`, `bluetooth.go`, `pod.go`; the message test drops an input that was a response rather than a command |
| #18 (`f1f6138`) | 2026-08-25 | When the phone reconnects, start over and renegotiate the session over the new connection |
| #19 (`9c6ac56`) | 2026-09-07 | Fault `0x1C` (pod life exceeded) when minutes active ≥ 80 × 60 and no fault is set |
| #21 (`3f82784`) | 2026-10-12 | Control panel and JSON API (`pkg/api/web.go`, `server.go`); `Status` snapshot (`pkg/pod/status.go`); a `Radio` interface with the Linux GATT implementation split out (`gatt_linux.go`, `gatt_other.go`) and an **ImpossiBLE transport** (`impossible.go`); first transport tests |
| #22 (`1ace0cf`) | 2026-10-12 | Advertise the fault and alert state; give each connection its own input channels so a reader left over from an earlier connection does not consume the new one's packets; ignore a connect signal latched during the connection being set up |
| #23 (`a491a5e`) | 2026-10-12 | On a message that fails to parse, decrypt or unmarshal, hang up and wait for the phone to set up a new session, instead of exiting the process; first `pkg/pod` test |

`git diff --shortstat e113d70 a491a5e -- . ':!vendor'`: 15 files changed, 1,952 insertions, 295 deletions. PR #20
("Drop queued packets from a previous connection on reconnect", 2026-10-02) was closed unmerged. Its subject matter is
covered by #22.

## 4. What pod state it models

State lives in `PODState` (`pkg/pod/state.go`) and is saved to a TOML file (`-state`, default `state.toml`) after every
command, so a restarted process resumes the same pod. `-fresh` starts an unpaired pod with 150 U (3,000 pulses of
0.05 U).

| Aspect | Modelled as |
|---|---|
| Pod progress | Advanced by the commands seen during setup (version request, set unique id, the prime, basal-programming and cannula-insertion insulin programs), then by elapsed time for the prime and cannula boluses, then to "below 50 U" when the reservoir reaches 1,000 pulses (`handleCommand`) |
| Reservoir | Decremented by each **bolus** program, all at once when the bolus is programmed. Reported as the "above 50 U" value until it is 50 U or below, as a real pod reports it (`generalstatusresponse.go`) |
| Delivered | Incremented by each bolus program only |
| Bolus in progress | `BolusEnd` = now + 2 s per pulse (1 s per pulse during setup). `BolusRemaining` is derived from it. A bolus cancel reports the remaining pulses, then clears `BolusEnd` |
| Temp basal | Active until now + duration (half-hour units). The rate is decoded but not stored |
| Scheduled basal | An on/off flag set by programming basal table 0 and cleared by a stop-basal command |
| Extended bolus | A flag that commands only clear. No command sets it |
| Alerts | An 8-slot mask with a trigger time per slot. Set only from the control panel. Silence-alerts and program-alerts clear the named slots |
| Fault | A fault code and the pod minute it was set. Set from the control panel (any 0–255), or `0x1C` automatically at 80 hours. With a fault set, status requests of type 0 and 7, and the response to every other command, are the detailed status instead of the general one, with progress "fault" and delivery suspended (`detailedstatusresponse.go`) |
| Pod age | `ActivationTime`, from which minutes active is computed on the wall clock. The control panel's `setActiveTime` moves it |
| Status types | General status; detailed status (type 2); types 1, 3 and 5 from state; types 0x46, 0x50, 0x51 hard-coded |
| Message handling | A retry with the same message sequence number is ignored. The response carries the command's sequence and request id. A missing ACK ends the session. Deactivation exits the process on the next loop |

**What it does not model** (from the code at `a491a5e`):

- Basal and temp-basal insulin are not drawn from the reservoir or added to delivered insulin. Rates and basal schedules
  are not stored.
- The pod never refuses a command. There is no nonce or program-sequence check, no "bolus already in progress", and
  commands sent while faulted are still applied (a bolus still decrements the reservoir). `Reservoir -= Pulses` is an
  unsigned 16-bit subtraction with no lower bound check.
- No alert timers. Program-alerts only clears slots, so expiry and low-reservoir alerts fire only when raised from the
  control panel.
- No battery, no occlusion detection or other physical behaviour except through `setFault`. A fault does not stop the
  bolus timer or the temp-basal end time in state.
- No controllable clock (§8). Timers run on `time.Now()`.
- The 80-hour fault is evaluated when a response is built, so `/status` keeps showing no fault after 80 hours until
  the next command arrives (run: `setActiveTime` 4800 → `/status` `fault: 0, minutesActive: 4800`). The control panel
  says the same: "At 80 hours the pod faults with 0x1C at the next command."
- Eros and Omnipod 5 are not covered. The commands recognised are the DASH set in `pkg/command/command.go`. Any other
  opcode gets a fixed NACK-type response.

## 5. Control panel and JSON API

`-api` (default `:8080`) serves:

| Endpoint | Behaviour |
|---|---|
| `GET /` | An HTML control panel (`pkg/api/web.go`): pod id, paired/connected, progress, reservoir, delivered, age, alerts, fault, delivery flags, sequence counters; controls for each command below; a list of 120 named fault codes |
| `GET /status` | JSON `Status` (`pkg/pod/status.go`) as of the last completed command or control change. Fields include `progress`, `progressName`, `reservoir` and `delivered` in units, `minutesActive`, `alerts`, `fault`, `faultMinutes`, the basal/temp/bolus flags, `bolusRemaining`, `crashNext`, and the message, command, nonce, session and program sequence numbers |
| `POST /command` | `{"command": ..., "value": ...}`, answered with the new `Status`, or HTTP 400 with a reason |
| `/ws` | The WebSocket API used by the separate [ps2/pod_simulator_frontend](https://github.com/ps2/pod_simulator_frontend). It pushes the raw state after each acknowledged command and accepts the same command JSON |

| Command | Value | Effect |
|---|---|---|
| `changeReservoir` | units, 0–200 | Sets the reservoir |
| `setActiveTime` | minutes, 0–6000 | Sets pod age by moving the activation time |
| `setAlerts` | slot mask, 0–255 | Replaces the active alert slots and stamps their trigger times |
| `setFault` | fault code, 0–255 (0 clears) | Sets the fault code and fault time |
| `crashNextCommand` | `"beforeProcessing": true\|false` | Exits the process (`log.Fatalf`) on the next state-changing command, either before it is applied or after it is applied and saved, so the phone never gets the response. `run.sh` restarts the process in a loop |

Run on 2026-10-17 (`-transport impossible -api 127.0.0.1:18080`, scratch state file): each command returned the updated
`Status`, `changeReservoir` 250 returned `400 reservoir 250: want 0 to 200`, an unknown command returned
`400 unknown command "bogus"`, and `GET /command` returned 405.

State-changing commands, for `crashNextCommand`, are those whose `DoesMutatePodState()` is true: set unique id,
silence alerts, program alerts, program insulin, program beeps, stop delivery and deactivate. The crash flags are
process globals, so a crash clears them.

## 6. Transports and connection behaviour

| | `-transport ble` (default) | `-transport impossible` |
|---|---|---|
| Peer | A phone, over a Linux HCI adapter (paypal/gatt, vendored). Needs `cap_net_raw,cap_net_admin` | An app in the iOS Simulator with ImpossiBLE's library injected, over a Unix socket (`-socket`, default `/tmp/impossible.sock`) carrying newline-delimited JSON (`hello`, `scan`, `connect`, `discoverServices`, `discoverCharacteristics`, writes, notifications, `didDiscover` with the advertisement) |
| Builds on | Linux only (`gatt_linux.go`). On other platforms `NewGattRadio` returns an error naming the other transport | Any platform. The protocol tests run on Linux |
| Peripheral id | – | A stable UUID saved in state (`peripheral_id`) |

Both build from the same tree: `go build` succeeds for linux/amd64, linux/arm and darwin/arm64 at `a491a5e`.

Behaviour common to both (`pkg/bluetooth/bluetooth.go`, `pkg/pod/pod.go`):

- **3-minute hang-up.** The command loop waits 3 minutes (`ReadMessageWithTimeout(3 * time.Minute)`) for the next
  command, and for an ACK after each response. On timeout the pod disconnects and waits for a new connection. The
  README describes this as mimicking DASH pods that disconnect every 3 minutes, which can drive Loop as a heartbeat when
  no BLE CGM is available (PR #10, 2023-03-15, set the 3-minute value).
- **Reconnect.** A new connection during setup or the command loop abandons the current exchange and renegotiates the
  session (#18). Each connection gets its own input channels (#22).
- **Messages the pod cannot use.** A setup or session message that fails to parse, a command that fails to decrypt or
  unmarshal, or a bad ACK, makes the pod hang up and wait for a new session (#23). Failures while building or
  encrypting its own response still exit the process.
- **Start delay.** On the ImpossiBLE transport, a connect that carries a start delay (`kCBConnectOptionStartDelay`) is
  held for that delay, as iOS does.
- **Advertised state.** For a paired pod, the 2nd advertised service UUID is `C001`, `C005` when an alert slot is
  active, and `C00A` when a fault is set. The manufacturer data carries the fault code and alert slots. An unpaired pod
  advertises `2470` there. Run on 2026-10-17 over the socket with a hand-made paired state: `C001` → `setAlerts 4` →
  `C005` → `setFault 20` → `C00A`. The README notes that Loop treats a pod fault as final, so after clearing a fault in
  the simulator Loop must be relaunched before testing another one.

Cryptography is named here by family only: pairing uses X25519 key agreement and AES-CMAC, sessions use EAP-AKA with
Milenage (vendored `wmnsk/milenage`), and messages use AES-CCM.

**Operational facts for contributors.** The control API listens on all interfaces by default, has no authentication,
and the WebSocket upgrader accepts any origin. The state file holds the simulated pod's pairing and session keys and is
written with mode `0777`. The info-level log prints those keys. These are keys of a simulated pod, but logs and state
files from a run should be handled as such.

## 7. Tests and CI

### 7.1 What exists

| Package | Test functions | What they check |
|---|---|---|
| `pkg/bluetooth` | 4 (`bluetooth_test.go` 2, `impossible_test.go` 2) | A read follows a new connection; a new connection reads only its own packets; the ImpossiBLE radio advertises an unpaired pod, connects, discovers both characteristics and carries both; a connect with a start delay is held for it |
| `pkg/eap` | 1 (4 subtests) | EAP-AKA message marshal/unmarshal round trip on zero-filled attributes |
| `pkg/message` | 1 | Unmarshals one captured message. It asserts only that decoding returns no error, then prints the result |
| `pkg/pod` | 1 | A garbled session message makes the pod hang up (#23) |

7 functions in 5 files (`git grep -h -E '^func Test' a491a5e -- ':!vendor' | wc -l`). History of the count:
2 functions at `ec13f46` and at `e113d70`, 4 at `3f82784`, 6 at `1ace0cf`, 7 at `a491a5e`. No test covers command
decoding, response encoding, pod-state transitions, the control API, or the session cryptography against known
answers.

### 7.2 Run on 2026-10-17

Go 1.23.0 linux/amd64, a copy of `externals/pod` at `a491a5e`, `GOTOOLCHAIN=local`. `go build ./...` and `go vet ./...`
are clean without build tags. `go test -count=1 -v ./...`, with and without `-mod=vendor`:

```
=== RUN   TestReadCmdFollowsANewConnection
--- PASS: TestReadCmdFollowsANewConnection (0.05s)
=== RUN   TestANewConnectionReadsOnlyItsOwnPackets
--- PASS: TestANewConnectionReadsOnlyItsOwnPackets (0.10s)
=== RUN   TestSimRadioPairsAndCarriesBothCharacteristics
--- PASS: TestSimRadioPairsAndCarriesBothCharacteristics (0.00s)
=== RUN   TestSimRadioHoldsAConnectForItsStartDelay
--- PASS: TestSimRadioHoldsAConnectForItsStartDelay (0.70s)
ok  	github.com/avereha/pod/pkg/bluetooth	0.858s
--- PASS: TestEapAka_MarshalUnmarshal (0.00s)
ok  	github.com/avereha/pod/pkg/eap	0.002s
--- PASS: Test_PrintfromByteArray (0.00s)
ok  	github.com/avereha/pod/pkg/message	0.001s
--- PASS: TestAGarbledSessionMessageHangsUp (0.00s)
ok  	github.com/avereha/pod/pkg/pod	0.002s
```

`go test -count=5 -race ./pkg/...` also passes.

The same command at loopandlearn/pod's head `ec13f46` fails under Go 1.23: the vet check that `go test` runs reports
format errors in `main.go`, so `github.com/avereha/pod`, `pkg/bluetooth` and `pkg/pod` fail to build ("build failed"),
`pkg/eap` passes, and `Test_PrintfromByteArray` fails ("magic pattern not found"). At `e113d70` (LoopKit/pod on
2026-09-30) both tests pass. These are the failures that `c797a81` fixed.

### 7.3 Ablation: does `TestAGarbledSessionMessageHangsUp` fail when the hang-up is removed?

In a scratch copy, the EAP-AKA challenge-parse failure branch in `EapAka()` (`pkg/pod/pod.go`) was changed from
`p.startOver(...)` (log, disconnect, wait for a new session) to logging and returning without disconnecting:

```
-		p.startOver("error parsing the EAP-AKA challenge: %s", err)
+		log.Errorf("ABLATION: swallowed EAP-AKA challenge parse error: %s", err)
 		return
```

Result:

```
level=error msg="ABLATION: swallowed EAP-AKA challenge parse error: error parsing eap message: invalid eap code: 43 …"
    pod_test.go:83: the pod did not hang up
--- FAIL: TestAGarbledSessionMessageHangsUp (2.00s)
```

The log line shows the garbled message reached the branch that was changed, and the failure is the test's own
assertion (`t.Fatal("the pod did not hang up")` after a 2-second wait for the radio's `Disconnect`). The unchanged copy
passes in 0.00 s and logs `error parsing the EAP-AKA challenge: … ; hanging up`. The test exercises that branch and
fails when it is removed.

### 7.4 CI

`.github/workflows/ci.yml` (added 2026-05-23): on pushes to `master`/`main` and on all PRs, `actions/setup-go@v5` with
Go 1.21, then `go test ./...`. No vet, race, lint or cross-build step. `gh run list -R LoopKit/pod`: every run listed,
from 2026-05-26 to 2026-10-12, concluded `success`, including the push runs for `e113d70`, `3f82784`, `1ace0cf` and
`a491a5e`. loopandlearn/pod has no workflow. CI runs `pod`'s own unit tests. No driver (OmnipodKit, OmniBLE or AAPS) is
run against `pod` in any workflow found.

## 8. Fault injection and harness mechanisms compared with faketandem

jwoglom/faketandem's README describes it as "based on the 'pod' OmniPod simulator". The two histories share the first
commit `715833c`.

| Mechanism | LoopKit/pod `a491a5e` | jwoglom/faketandem `34c9401` |
|---|---|---|
| Radio transport | BLE peripheral on Linux (paypal/gatt) | BLE peripheral on Linux |
| Virtual transport | Yes: ImpossiBLE's Unix-socket JSON protocol (`-transport impossible`), whose client is CoreBluetooth in an iOS Simulator app with ImpossiBLE injected | Yes: TCP/JSON virtual GATT (`-transport virtual`), with a configurable ATT MTU and an option for Linux/gatt write-ACK ordering |
| Clock control | None. Wall clock. `setActiveTime` moves the pod's activation time (age) only | `/api/clock`: real or manual mode, set and step (`/api/clock/advance`), pump clock skew, pump time zone |
| Request log | None structured. Text log with each command's opcode and bytes; WebSocket state push after each acknowledged command; sequence counters in `/status` | `/api/log`: a pump-side request log (`pkg/reqlog`) |
| Device-state controls | Reservoir, pod age, alert slots, fault code (sticky until cleared) | `/api/state` and pump-initiated actions (`/api/state/…`) |
| Fault injection: where | Pod state (fault code, alerts), and process exit on the next state-changing command, before or after applying it | A registry (`pkg/faults`) that the response path and the transport consult |
| Fault injection: scope | The next state-changing command, whatever it is | Per opcode, message name or characteristic, for the next *n* matches or every match |
| Fault injection: kinds | Pod fault code (0–255), alert slots, crash before/after processing | Drop response (state still applied), delay response, error response (state not applied), disconnect after the request or after *n* response fragments, drop fragment (by index or every *n*th), reject quick-pair, radio off/on |
| Built-in link behaviour | Hang-up after 3 minutes idle; hang-up on an undecodable message; start-delay hold | (not measured here) |
| CI | `go test ./...` (Go 1.21), 7 functions | `go vet`; tests with `-race` and coverage; an integration job that builds pumpX2's cliparser and runs `go test ./...` with it; golangci-lint; an ARM cross-build. 939 `func Test` declarations in 345 test files (`git grep -h -E '^func Test' -- ':!vendor' \| wc -l`) |
| Driver exercised in CI | None | pumpX2's cliparser (the client library's codec) |

## 9. Shared test vectors

Method, the same as the 2026-09-30 census (`device-layer.md` §0): every quoted hex string of 16 or more hex digits,
normalised to lower case with spaces removed, collected per project and intersected. Script:
`hexvec.py <root> tests|all <exts>` in this measurement's scratch area (the regex is `"((?:[0-9A-Fa-f]{2}[ ]?){8,})"`).
The vectors themselves are not reproduced here.

| Set | Unique literals |
|---|---|
| LoopKit/OmniBLE tests (`29358d5`) | 191 |
| loopandlearn/OmnipodKit tests (`4e923d7`) | 207 |
| AAPS `pump/omnipod/dash` (`dev` `7e1d537d49`; same on `master` `598e2eb39c`) | 65 |
| AAPS `pump/omnipod/` (common, dash, eros; `dev`) | 130 |
| `pod` test files (`a491a5e`) | 0 as quoted literals; `message_test.go` holds 1 comma-separated message |
| `pod` non-test Go source (`pkg/`, not `vendor/`) | 11 (10 in `pkg/response/*.go` default and hard-coded responses, 1 in `pkg/eap`) |

| Intersection | Count |
|---|---|
| OmniBLE ∩ OmnipodKit | 191 (reproduces the census) |
| OmniBLE ∩ AAPS `pump/omnipod/dash` | 14 |
| OmniBLE ∩ AAPS `pump/omnipod/` (all three directories) | 58 (reproduces the census figure) |
| `pod` tests ∩ OmniBLE / OmnipodKit / AAPS | 0 / 0 / 0 (the comma-separated message, normalised, also matches none) |
| `pod` source ∩ OmniBLE / OmnipodKit / AAPS `dash` | 0 / 0 / 1 (`generalstatusresponse.go`'s default response, also in AAPS `DefaultStatusResponseTest.kt`) |
| `pod` source ∩ AAPS `pump/omnipod/` | 2 |

**Option.** `pod` builds DASH response bodies from state (`pkg/response/*.go`). A small program that sets states
through the same code and writes out (state, request, plaintext response) triples could serve as a language-neutral
DASH response corpus that OmnipodKit, OmniBLE and AAPS load in their decoder tests. Facts that bear on it:

- The response encoders were written to satisfy the controllers (code comments cite captured pod messages and Loop's
  behaviour), so a corpus from them would not be independent of the drivers. This is the same relationship the census
  records for faketandem and pumpX2.
- It would cover the plaintext message layer only. The session-cryptography layer is out of its scope.
- Today the overlap is 0 test literals and 1–2 source literals, so a corpus from `pod` would add vectors, not
  consolidate existing ones.

## 10. How controllers connect to it

| Path | What is needed | State on 2026-10-17 |
|---|---|---|
| Phone ↔ Raspberry Pi over BLE | Loop or Trio with OmnipodKit (or older OmniBLE) on a phone; `pod` on a Pi with a BLE adapter (README: Pi 3B or 4) | Works with any OmnipodKit, as the phone sees a BLE peripheral |
| App in the iOS Simulator on a Mac | An app built with ImpossiBLE injected (g7sim's `simulator/build-impossible.sh` builds the library), `pod -transport impossible`, and an OmnipodKit that uses the bridge instead of its Simulator mocks | OmnipodKit's detection (`mocksPod`: mock unless Eros, or unless `NSClassFromString("CBSPeripheral")` finds the bridge) arrived in `e60e0ab` (2026-10-12, "Talk to a simulated pod when the Simulator has Bluetooth"). It is on OmnipodKit `next-dev` (`c21a077`) and the `simulator-bluetooth` branch, not on `dev` (`928bb79`) or `main` (`4e923d7`). LoopWorkspace `f841285` and Trio dev `e41c9db37` both pin OmnipodKit `4e923d7`, whose Simulator code paths always mock pod commands |
| `pod` alongside g7sim for one app | Separate sockets, joined by g7sim's `impossible-mux` (`-suspend` lets an advertisement wake the suspended app) | Documented in both READMEs |
| AndroidAPS DASH driver | A phone with BLE and `pod` on a Pi | Not documented in `pod` and not tested here. The BLE path does not depend on the controller platform, so it may work (inference) |

**trio-test-harness** (`c3c1bfe`) uses only the apps' built-in fake devices: "Glucose Simulator + Pump Simulator" for
Trio, "CGM Simulator + Pump Simulator" for Loop (README, `harness/flows/loop.py`). It has no reference to `pod`,
ImpossiBLE or OmnipodKit.

## 11. Nightscout relevance

`pod` does not talk to Nightscout. A controller paired with it uploads what it would upload for a real pod. From
NightscoutService `fe075ef` and OmnipodKit `4e923d7`, for Loop:

| `pod` event or state | What Loop records (code path) | Nightscout upload |
|---|---|---|
| Bolus program | Bolus `DoseEntry` | `treatments` bolus (`BolusNightscoutTreatment`, `Extensions/DoseEntry.swift`) |
| Temp basal program / cancel | Temp-basal `DoseEntry` | `treatments` temp basal (`TempBasalNightscoutTreatment`) |
| Suspend (stop delivery) / resume | Suspend / resume `DoseEntry` | `treatments`: a suspend is uploaded as a zero-rate temp basal with `reason: "suspend"` and the suspend's duration; a resume `DoseEntry` maps to no treatment (`case .resume: return nil`) |
| New pod paired | `NewPumpEvent` "Pod Change", `.replaceComponent(.pump)` (`OmniPumpManager.swift`) | `treatments` `Site Change` (`Extensions/PersistedPumpEvent.swift`) |
| Fault or pod life exceeded | A pump-manager alert and a status highlight ("Pod Error", "Pod Expired", "No Insulin" in `OmniPumpManager.swift`) | `devicestatus.pump.reservoir_display_override` and `reservoir_level_override` (NightscoutKit `PumpStatus`). OmnipodKit emits no `.alarm` pump event, so no `Note` treatment is created from a pod fault in this path |
| Reservoir ≤ 50 U | `didReadReservoirValue` (only for a real level, not the "above 50 U" value) | `devicestatus.pump.reservoir`, when read within the last 15 minutes |
| Delivery state | `basalDeliveryState`, `bolusState` | `devicestatus.pump.suspended`, `bolusing` |

Trio uses the same OmnipodKit, so the pump-side events are the same. Trio's own upload mapping was not read for this
document. A `pod`-driven run can therefore produce real-shaped treatments and devicestatus in a test Nightscout,
including the fault and expiry status paths that are hard to reach with a real pod. Because the pod does not draw basal
from the reservoir (§4), reservoir figures in such a run reflect boluses only.

## 12. Fit with the census and the quality-system proposal

- The 2026-09-30 census row for `pod` (`repos.tsv`, `census-2026-09-30.jsonl`, `device-layer.md` §2) measured
  loopandlearn/pod. At `ec13f46` that row is accurate: 0 commits in 6 months, 0 workflows, 2 test files. At that date
  LoopKit/pod, the upstream, had 4 non-merge commits in the same 6 months, a workflow that runs the tests, and passing
  tests (§2, §7.2).
- Since 2026-10-12 `pod` has a virtual transport, a control API with pod-state fault injection, and 7 tests. That moves
  it from "Raspberry Pi BLE rig" towards the faketandem pattern the proposal describes. It still has no transport-level
  fault injection, clock control, request log or driver-in-CI job (§8).
- The census's 58 OmniBLE ∩ AAPS figure counts all of AAPS `pump/omnipod/`. The DASH directory alone shares 14 (§9).

## 13. Open questions

1. Should the census and the proposal name LoopKit/pod as the `pod` repository, and keep loopandlearn/pod only as a
   fork row?
2. Does OmnipodKit intend to merge the ImpossiBLE detection (`e60e0ab`) from `next-dev` into `dev`, so that LoopWorkspace
   and Trio pins pick it up?
3. Would the `pod` maintainers accept a CI job that drives a DASH driver over the ImpossiBLE socket, or a transport-level
   fault registry like faketandem's?
4. Is a state → response corpus from `pod` (§9) useful to the OmnipodKit and AAPS maintainers, given that it is not
   independent of the drivers?
5. Should basal and temp-basal draw on the reservoir, so that reservoir and IOB figures in a test Nightscout follow
   delivery?

## 14. Reproduce

```bash
P=externals/pod                       # LoopKit/pod a491a5ea
gh api repos/LoopKit/pod --jq '[.fork,.parent.full_name,.created_at,.pushed_at]'
gh api repos/loopandlearn/pod --jq '[.fork,.parent.full_name,.source.full_name]'

# lineage, in a scratch clone (never add remotes to externals/)
git clone -q "$P" /tmp/pod-lineage && cd /tmp/pod-lineage
git remote add lal ../externals/stack/loopandlearn__pod   # or https://github.com/loopandlearn/pod
git remote add rk https://github.com/randallknutson/pod && git fetch -q --all
git merge-base origin/main lal/main                     # ec13f46...
git log --format='%h %cI %s' lal/main..origin/main      # LoopKit-only commits
git log --format='%h %cI %s' origin/main..lal/main      # empty

# tests
cp -r "$P" /tmp/pod-work && cd /tmp/pod-work
GOTOOLCHAIN=local go build ./... && go vet ./... && go test -count=1 -v ./...
git -C "$P" grep -h -E '^func Test' a491a5e -- ':!vendor' | wc -l          # 7

# control API and advertisement (record the PID; stop it with kill <PID>)
go build -o /tmp/podbin . && /tmp/podbin -q -fresh -transport impossible \
  -socket /tmp/podsim.sock -state /tmp/pod-state.toml -api 127.0.0.1:18080 & echo $!
curl -s 127.0.0.1:18080/status
curl -s -X POST 127.0.0.1:18080/command -d '{"command":"setFault","value":20}'
```
