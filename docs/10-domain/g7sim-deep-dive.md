# g7sim Deep Dive

*Contributor-facing. Measured 2026-10-17 at LoopKit/g7sim `7c039de5` (2026-10-12; the GitHub default branch `main` had the same head on 2026-10-17). Other repositories cited: LoopKit/G7SensorKit `next-dev` `e17129d` (2026-10-15) and `main` `dd91f46` (2026-10-03); LoopKit/LoopWorkspace `next-dev` `1561bff0` (2026-10-15), `dev` `c1f55970` and `main` `548b3324` (read through the GitHub API); LoopKit/NightscoutService `ace20b0f` (2026-10-14, the LoopWorkspace `next-dev` pin); nightscout/Trio `dev` and `main` (G7SensorKit pointer read through the GitHub API on 2026-10-17); LoopKit/pod `a491a5e` (2026-10-12); jwoglom/trio-test-harness `c3c1bfe` (2026-10-17); mickeyl/ImpossiBLE `58fe38d` (the pin in g7sim's build script); JohanDegraeve/xdripswift `c268542e`; NightscoutFoundation/xDrip `9898cb8e0`; xdrip-js/xdrip-js `dev` `e301273`; j-kaltes/Juggluco `db70dc1`. Disclosure level: cryptography is named by family only. This page contains no keys, constants, test vectors or handshake byte sequences.*

g7sim is a Go program that plays the sensor side of a Dexcom G7, ONE+ or Stelo for CGM software under development. The client it was built against is LoopKit/G7SensorKit's direct-connection code, which is on G7SensorKit's `next-dev` branch and not on its `main`. g7sim has two transports. The first is a real Bluetooth LE peripheral on Linux, built on a vendored `paypal/gatt` HCI stack. The second, `impossible`, serves an app running in the iOS Simulator over ImpossiBLE's JSON-over-Unix-socket CoreBluetooth replacement, so no radio is needed. It models the sensor's advertising schedule, display slots, lockout, readings (warm-up, expiry, a 24-hour backfill store, calibration offset), the identity certificate chain, and the iOS behaviours that decide whether a backgrounded app wakes for a reading. The project describes itself as "for development use only — not a Dexcom product", unaffiliated with Dexcom, Inc., emitting "only simulated, made-up data".

| Item | Value | How it was measured |
|---|---|---|
| Repository | LoopKit/g7sim, MIT, Go | `gh api repos/LoopKit/g7sim` |
| History | 17 commits, 2026-10-09 to 2026-10-12; GitHub repository created 2026-10-10 | `git log` at `7c039de5` |
| Size | 5,407 lines of Go outside `third_party/` (26 files) | `wc -l $(git ls-files '*.go' \| grep -v third_party)` |
| Packages | `main` (transports, HTTP API, web UI), `g7` (sensor model, protocol handler, crypto), `suspend`, `cmd/impossible-mux` | tree |
| Tests | 33 `func Test` in 8 files, no `t.Run` subtests; 4 functions loop over 11 table cases | `go test -v ./...` (§5) |
| Test result | 4 packages `ok`, 33 PASS, 0 FAIL; also clean under `-race` and `go vet` | Go 1.23.0, linux/amd64, offline |
| CI | none: no `.github/` in the tree, and `gh api repos/LoopKit/g7sim/actions/workflows` returns `total_count` 0 | 2026-10-17 |
| Builds | linux/amd64, linux/arm (GOARM=6, Pi Zero class) and darwin/arm64 cross-builds succeed | `GOOS=… go build` |
| Client it targets | G7SensorKit direct connection (`next-dev`); Loop built from LoopWorkspace `next-dev` | §6, §7 |

---

## 1. What g7sim emulates

### 1.1 Sensor identity and models

A sensor is created with `-fresh`, or from the web UI or `POST /new`, and is persisted in a JSON state file (`g7state.json` by default). The state holds the serial, the 4-digit pairing code, the model, the activation time, the session parameters, the display slots and their keys, the identity certificate, the calibration and the stored readings (`g7/state.go`).

- **Models.** `g7`, `oneplus` and `stelo` differ only in the advertised name prefix, which is the only thing G7SensorKit uses to tell them apart (`g7/state.go:34-36`).
- **Presets.** The 10- and 15-day presets carry the session length, warm-up, algorithm version and maximum lifetime that a real sensor reports in its extended-version reply. The values come from captured replies (`g7/state.go:43-57`). `-lifetime` and `-warmup` override the preset lengths. A 12-hour grace period is added after the rated lifetime (`GracePeriod`).
- **Address and peripheral identity.** The BLE transport advertises from a random static address derived from the serial. The Simulator transport derives a stable peripheral UUID from the serial (`impossible.go`, `peripheralID`). Each new sensor is therefore a new peripheral to iOS, and a restarted g7sim is the same one.
- **Identity certificate.** A real G7 streams an X.509 P-256 certificate chain during pairing and signs the display's key-challenge nonce with its leaf key (ECDSA P-256). g7sim mirrors this with its own fixed dummy CA. The CA's signing key is in the source by design: a marker that the data is simulated, not a secret (`g7/identity.go:16-24`). G7SensorKit `next-dev` pins that dummy CA as a second trust anchor and classifies a sensor as genuine, simulated or unverified (§6.3).

### 1.2 Advertising schedule

The timing model is `g7.MeasuredTiming()` (`g7/sensor.go:43`). The README attributes it to sniffer and scanner measurements of a real G7, recorded in LoopKit/Loop `docs/G7_MUTE_INVESTIGATION_2026-09.md` at `b930fe17`. That file exists at that commit (checked through the GitHub API, 2026-10-17). In outline:

- A reading every 300 s from activation, and a burst of adverts shortly after each one.
- The burst ends early once every held display has collected the reading. It runs longer while a held display is missing. A short "bare" advert that admits only the phone is repeated at four minute marks while the phone's slot is held and it missed the reading.
- A display slot stays held for 15 minutes after it was last seen. Held slots set bits in a types-in-use byte in the manufacturer data.
- A client that has collected the current reading is refused for the rest of that window: by address when its link comes up, and by display type at its challenge.
- Four rejections in a row stop all advertising for 10 minutes.
- A sensor that no phone has paired with advertises continuously, so a phone can find it at any time (`g7/sensor.go:210`).

A difference the README states itself: a real sensor refuses a served client at the link layer, whereas g7sim lets the link come up and closes it within milliseconds. iOS reports that as a connect followed by a disconnect.

### 1.3 GATT layout and protocol handler

Both transports serve the same table: the CGM service with control, authentication, backfill and certificate characteristics plus one notify-only characteristic, and a second vendor service with two characteristics, under a 16-bit advertised service UUID (`ble.go`, `impossible.go:122-139`). Writes to characteristics with no protocol role are logged and acknowledged.

`g7/handler.go` runs one goroutine per link and reads the exchange as a straight-line sequence. The README says this mirrors G7SensorKit's `G7Authenticator.run()`. The first write on the authentication characteristic selects the path:

- **Fresh pairing.** A three-round EC-JPAKE exchange on P-256 over the 4-digit code. Then an AES-128 challenge in each direction under the derived key, the certificate phase (the identity chain from §1.1), a key-challenge step in which the sensor signs the display's nonce and checks the display's signature, and a finalize/bond exchange.
- **Reconnect.** Straight to the AES challenge with the key stored for that display type. A wrong answer is a rejection that counts toward the lockout. With no stored key (the slot was forgotten), the sensor answers with random bytes, so the client's own check fails and it re-pairs with the code.

After authentication the session answers the control requests: current glucose, backfill over a time range, two version replies, and calibration (set and bounds). It hangs up after 6 s without a request (`sessionIdle`, `g7/handler.go:20`).

Where the emulated sensor is more permissive than the client's own model of a real sensor:

- The sensor does not act on its verification of the client's J-PAKE round proofs. `SetClientRound` returns a verdict, and `keyExchange` discards it (`g7/handler.go:153,155`). A wrong code still surfaces at the AES challenge, as it does with a real sensor.
- G7SensorKit's tests record a constraint that the real sensor places on the client's third round (`G7JPAKETests.swift`, `testRound3UsesTheFixedRandomizer`). g7sim does not check it. A client that broke that constraint would pair with g7sim and fail against a real sensor.
- The display-signature check in the key-challenge step is logged and not enforced: "Advisory for now (logged, not enforced) so a verification quirk cannot block pairing" (`g7/handler.go:295`).

### 1.4 Readings model

`g7/glucose.go` and `g7/sensor.go`:

| Aspect | Behaviour |
|---|---|
| Cadence | One reading per 300 s since activation. Missed readings are generated on the next tick, so the store has no gaps. |
| Glucose modes | `sine` (default: 120 mg/dL ± 50, 240-minute period), `fixed`, and `walk` (a mean-reverting random walk with Gaussian noise). Output is clamped to 40–400 mg/dL and rounded. |
| Trend | The difference from the previous reading per minute, rounded to 0.1. It is present only when the previous reading exists and had glucose. |
| Warm-up and expiry | Algorithm state "warm-up" before the warm-up time and "expired" after the session length (rated lifetime plus 12 h). Neither carries glucose. |
| Forced states | `algorithmState` in the glucose mode replaces the computed state, for example a temporary sensor issue or a failed sensor. Any state other than OK carries no glucose. |
| Backfill store | The last 24 × 12 = 288 readings (`keptReadings`, `g7/state.go:32`). |
| Calibration | Calibration shifts later readings by the difference between the entered value and the stored reading nearest the calibration time (`Calibrate`). Bounds are reported back to the client. |

### 1.5 iOS behaviours modelled for the Simulator

These run only with `-transport impossible` (`impossible.go`, `suspend/suspend.go`):

- **Discovery and connect follow the advertising schedule.** The app sees the sensor only while it advertises, and a pending connect waits for the next advert. A connect is also held for the `kCBConnectOptionStartDelay` the app passes, "as iOS does" (`7c039de5`).
- **Wake-path check.** When a reading starts advertising and the app has no pending connect, no scan and no live link, g7sim logs `NO WAKE PATH` with a running count. On a phone, the backgrounded app would sleep through that reading.
- **Suspension (`-suspend`).** g7sim follows runningboard's suspend and resume verdicts from the simulator's log (`xcrun simctl spawn … log stream`) and stops the app process with SIGSTOP while it is suspended. Every message g7sim then sends the app resumes it for 10 s (SIGCONT), as bluetoothd's wake assertion does.
- **Termination and relaunch (`-relaunch`).** When the app's socket closes with a connect or scan lodged, g7sim holds those requests, as bluetoothd does. At the next reading it relaunches the app through `simctl launch` with ImpossiBLE injected, and hands the requests back as a state restoration at the app's first call. `POST /force-quit` makes the app's end a user force-quit instead, which drops the held requests. The README lists four ways this differs from iOS: foreground relaunch, the order of the restore callback, a restored peripheral that is still connecting, and live links being closed rather than kept.

---

## 2. Transports

| | `-transport ble` (default) | `-transport impossible` |
|---|---|---|
| Host | Linux, raw HCI socket on `hci0` (needs `cap_net_raw,cap_net_admin` or root) | any OS the Go toolchain targets. The app side needs a Mac with the iOS Simulator. |
| Stack | vendored `paypal/gatt` in `third_party/gatt` (`go.mod` `replace`) | g7sim is the provider on ImpossiBLE's socket (default `/tmp/impossible.sock`) |
| Client | a phone over the air | an app in the iOS Simulator with `libImpossiBLE.dylib` injected through `DYLD_INSERT_LIBRARIES` |
| System bond | none. The stack has no Security Manager, so iOS connects unencrypted and the sensor does not appear under Settings → Bluetooth (README). | not applicable |
| Coexistence | takes `hci0`, so it cannot share an adapter with the pod simulator. `bluetoothd` must not hold the adapter on newer Pi OS releases (README). | one app per provider. `impossible-mux` lets several providers share one app. |

**Vendored `paypal/gatt` changes.** A diff against the copy LoopKit/pod vendors (`pod/vendor/github.com/paypal/gatt`) shows g7sim's changes in `linux/hci.go`, `linux/l2cap.go` and `linux/device.go`. They do three things: keep the advertiser off when its owner turned it off, count controller buffers per connection and return them on disconnect, and serialise the fragments of one PDU. The darwin files are removed and a `go.mod` is added. The README says the fixes are "noted in the README's library-changes notes". No such notes exist in the tree. The fixes are described in code comments only.

**`impossible-mux`** (`cmd/impossible-mux`) holds the app's single ImpossiBLE socket and connects it to several providers, for example g7sim and LoopKit/pod. Session-wide messages (hello, scans) go to every provider. Each peripheral's requests go to the provider that owns it. A connect to an unknown peripheral goes to all of them, and the one that holds it takes ownership. When suspension is wanted, the mux runs `-suspend` instead of g7sim, so that a message from any provider wakes the app (`43ff5eb`).

**ImpossiBLE build and patches.** `simulator/build-impossible.sh` clones mickeyl/ImpossiBLE, checks out `58fe38d` ("Library 3.1.0, the protocol impossible.go speaks"), applies `simulator/impossible-patches/0001…0006`, and builds an `arm64-apple-ios15.0-simulator` dylib, so the script as written targets Apple-silicon Macs. The six patches are as follows:

- 0001 and 0002 deliver the initial state callback on the central's own queue. G7SensorKit asserts its queue, so without them Loop crashed at launch.
- 0003 matches 16-bit and 128-bit forms of a service UUID.
- 0004 ends subscriptions on a disconnect.
- 0005 makes `retrievePeripheralsWithIdentifiers:` return peripherals seen before a relaunch.
- 0006 forgets services on a disconnect, because OmnipodKit rebuilds its session only when it rediscovers them.

The matching upstream pull requests mickeyl/ImpossiBLE #2–#6 were all open on 2026-10-17 (`gh api repos/mickeyl/ImpossiBLE/pulls?state=all`). The README still names `simulator/impossible-delegate-queue.patch`, which `6d3527c` (2026-10-12) deleted when it moved to the numbered patch series.

---

## 3. Control surface

**Command line** (`main.go:94-110`): `-state`, `-fresh`, `-code`, `-serial`, `-age`, `-model`, `-days`, `-lifetime`, `-warmup`, `-max-connections`, `-api` (default `:8080`), `-transport`, `-socket`, `-simulator`, `-relaunch`, `-suspend`, `-dylib`.

**HTTP API** (`api.go`), which also serves a self-contained web control panel at `/`:

| Endpoint | Effect |
|---|---|
| `GET /status` | sensor, slots, current window, latest reading |
| `POST /glucose` | sets the glucose mode (`kind`, `value`, `amplitude`, `periodMinutes`, optional `algorithmState`) |
| `POST /forget` | drops every display's key, so the next connection must re-pair |
| `POST /force-quit` | Simulator transport only: the app's end counts as a user force-quit |
| `POST /new` | replaces the sensor (`model`, `days`, `code`, `serial`, `ageMinutes`, `lifetimeHours`, `warmupMinutes`), saves it over the state file and re-executes the process |

**Reproduced run (Linux, 2026-10-17, built from `7c039de5`).** g7sim ran with `-transport impossible` on a socket in a scratch directory, with `-fresh -code 1234 -serial 123456789012 -age 1h59m50s`. A short Python client then spoke ImpossiBLE's JSON protocol: hello, scan, connect, discover, subscribe. Observed:

- `didDiscover` arrived immediately after the scan, with name prefix `DXCM`, local name, connectable flag, service UUIDs and manufacturer data. An unpaired sensor advertises continuously, so this is expected.
- `didConnect` followed. Then 2 services and 7 characteristics, with property sets matching `simServices`.
- `GET /status` returned reading index 24 at sensor time 7200 s, 120 mg/dL, state OK. This matches the sine default at a 2-hour age.
- When the client's socket closed with its scan still lodged, the log read "ended with a scan lodged; holding it as iOS would for a terminated app".
- `POST /glucose` with a fixed value and a forced algorithm state was accepted and echoed. An empty mode returned 400, and `GET /glucose` returned 405.
- `POST /new` (Stelo, age 0, 36 h lifetime, 5 min warm-up) returned the new name, code and serial. The process re-executed under the same PID. `/status` then showed the `DX01` prefix, a 15-day preset with a 36 h lifetime and 5 min warm-up, and reading 0 in the warm-up state.

The run went no further than discovery and connection. Authentication was not attempted, because that would need a G7 client (§5.3). A `-socket` given as an absolute path longer than the platform's Unix-socket path limit fails at bind and the process exits. A relative path works.

---

## 4. README status table checked against the code

| README row (quoted) | Check | Verdict |
|---|---|---|
| Advertising schedule (bursts, tails, minute calls, lockout): "done, unit tested, runs on the Pi" | 9 schedule tests in `g7/sensor_test.go` (`TestEmptyBurst` … `TestRejectionsLockTheSensor`) pass | unit tests confirmed. "Runs on the Pi" not checked (no hardware). |
| Display slots, served-client refusal, types-in-use byte: "done, unit tested" | `TestServedClientIsDroppedForTheRestOfTheWindow`, `TestTypesInUse` pass | confirmed |
| Readings: warmup, expiry, sine/fixed/walk glucose, calibration offset, 24 h backfill store: "done, unit tested" | `TestReadingsAndBackfill`, `TestWarmup`, `TestModelNamesAndSessionLength` pass. No test calls `Calibrate`, and none exercises `walk` or expiry. | partly: calibration offset, walk mode and expiry have no direct test |
| Reply encoders (4e, backfill record, 52, 4a, 32): "done" | the extended-version reply is checked against two captures (`TestExtendedVersionMatchesCaptures`). Glucose, backfill and version replies are exercised by the handler test. | consistent. The table claims no tests here. |
| Key-exchange and challenge crypto: "done, tested against a port of the app's client and the app's AES vectors" | the "port" reuses g7sim's own proof and hash primitives (§5.3). The AES vectors are G7SensorKit's `G7AuthCryptoTests` vectors, which G7SensorKit states were generated with `openssl enc -aes-128-ecb -nopad`. They are reproduced by OpenSSL 3.0.13 here (§6.2). | AES: confirmed, and independent of both implementations. J-PAKE: the agreement test does not detect a change to a shared primitive (§5.3). |
| GATT layout, random static address, HTTP API: "done, runs on the Pi" | HTTP API exercised in §3. GATT layout seen over the Simulator transport. | API and Simulator-side GATT reproduced. Pi not checked. |
| Per-connection protocol handler: "done, reconnect + session integration-tested; fresh pairing untested against real hardware" | `TestReconnectHandshakeAndSession`, `TestReconnectWithForgottenSlot` pass. No Go test drives the fresh-pairing path through the handler. | confirmed. The README's "Testing it" section (from `045b94f`) still says fresh pairing "has not yet been run end to end against the app". The Simulator row (`7321535`) and G7SensorKit `1a87aad` ("Pair for real in the Simulator when a Bluetooth bridge is injected") describe Loop pairing with g7sim in the Simulator. The two README statements disagree. The later one was not reproduced here (no Mac). |
| iOS Simulator transport: "done; Loop pairs, reads and reconnects in the Simulator" | 4 tests in `impossible_test.go` pass. Discovery and connect reproduced with a scratch client. | transport confirmed. Loop pairing not reproduced (no Mac). |
| Wake-path check, suspension, termination relaunch + state restoration: "done, unit tested; run against Loop" | `TestSimRadioCountsReadingsNothingWouldWake`, `TestSimRadioHoldsATerminatedAppsRequests`, `TestSuspenderFollowsRunningboardAndWakesForBluetooth` pass. Termination hold reproduced (§3). | unit tests confirmed. "Run against Loop" not reproduced. |

Two more README statements do not match the tree: the deleted `impossible-delegate-queue.patch` (§2) and the missing "library-changes notes" (§2). The README says "Go 1.15 (what the Pi has) is enough", and `go.mod` declares `go 1.15`. Only Go 1.23.0 was available here. A search for post-1.15 standard-library APIs (`os.ReadFile`, `strings.Cut`, generics, `any`) found none.

---

## 5. Tests

### 5.1 Inventory

| File | `func Test` | Covers |
|---|---|---|
| `g7/sensor_test.go` | 14 | serial checksum, advertising windows, slots, lockout, readings and backfill, warm-up, model names, extended-version captures |
| `g7/identity_test.go` | 5 | dummy CA, leaf chain, challenge signature, identity round trip, display-signature check |
| `g7/jpake_test.go` | 3 | J-PAKE agreement against the Go client port, wrong code, AES challenge known answers |
| `g7/handler_test.go` | 2 | reconnect handshake and session over an in-memory link, forgotten slot |
| `impossible_test.go` | 4 | Simulator radio: serving the sensor, connect start delay, wake-path count, termination hold |
| `main_test.go` | 3 | new-sensor defaults, overrides, rejections |
| `cmd/impossible-mux/mux_test.go` | 1 | routing each peripheral to its provider |
| `suspend/suspend_test.go` | 1 | following runningboard and waking for Bluetooth |
| **Total** | **33** | 4 functions loop over 11 table cases: 3 pairing codes, 2 AES cases, 4 models, 2 captures |

### 5.2 Run

```text
$ GOPROXY=off GOFLAGS=-mod=mod go test -count=1 ./...        # Go 1.23.0 linux/amd64, at 7c039de5
ok  	github.com/loopkit/g7sim	1.919s
ok  	github.com/loopkit/g7sim/cmd/impossible-mux	0.306s
ok  	github.com/loopkit/g7sim/g7	0.013s
ok  	github.com/loopkit/g7sim/suspend	0.002s
```

`go test -v` gives 33 `=== RUN` and 33 `--- PASS`. `go test -race` and `go vet ./...` are clean. No network was needed. The only module dependency is the vendored `paypal/gatt` through a `replace`. The checkout was unchanged after the runs (`git status` empty).

### 5.3 Ablation: do the crypto tests fail for the right reason?

Each break was made in a scratch copy of `7c039de5`, and the full suite was run.

| Break (in `g7/jpake.go`) | Expected | Result |
|---|---|---|
| A. The challenge transform returns the wrong half of the AES output | the known-answer test fails | `TestEncryptChallengeMatchesApp` fails on both cases with `challenge …: got …, want …` (`jpake_test.go:90`). **No other test fails.** `TestReconnectHandshakeAndSession` computes its expected answers with the same `EncryptChallenge`, so it cannot catch this. |
| B. The sensor-side shared-key derivation hashes the wrong coordinate | agreement fails | `TestJPAKEAgreesWithClient` fails with `code 1234: sensor …, client …` (`jpake_test.go:60`) |
| C. The Schnorr-proof transcript hash omits the party identifier (a primitive shared by the sensor and the test's client port) | ideally a failure | **all 33 tests pass** |

For C, a check that the break changed anything: a scratch test kept an unbroken copy of the transcript hash and verified a round-1 proof from the broken sensor against it. The proof failed verification, so the break does change what goes on the wire. The same scratch test run on the unbroken copy failed its "ablation changed nothing" assertion, as it should. The J-PAKE agreement test is a self-consistency check. The test's client port (`jpake_test.go:12-29`) builds its rounds with g7sim's own `makeCert`, `generator` and transcript hash, so a fault in those primitives moves both sides together. Only the round-3 and key-derivation formulas are written independently. The AES known-answer test is the one crypto check here whose expected values come from outside both implementations.

---

## 6. Relationship to other G7 implementations

### 6.1 Which "app"

The "app" in g7sim's README and test comments is LoopKit/G7SensorKit, the Loop CGM plugin. The handler cites `G7Authenticator.swift`, `G7Sensor.swift` and the `Messages/` parsers. `jpake_test.go` says its client "mirrors G7SensorKit's G7JPAKE". The AES cases are "the known answers from G7SensorKit's G7AuthCryptoTests".

G7SensorKit has two lines on 2026-10-17:

| Branch @ sha | README | Direct connection | Crypto and tests |
|---|---|---|---|
| `main` @ `dd91f46` (2026-10-03) | "Requires use of official G7 app" | no: the kit listens alongside the vendor app | no `Crypto/` directory; 4 test files |
| `next-dev` @ `e17129d` (2026-10-15) | "The plugin connects to the sensor directly over Bluetooth … The Dexcom app is not needed" | yes | `G7SensorKit/Crypto/` (EC-JPAKE on P-256 with its own P-256 and big-integer code, AES-128 challenge, ECDSA P-256 challenge signing, identity verification); 17 test files, 173 `func test` |

Direct connection entered with `764e002` "Direct sensor connection: pairing, session management, calibration and lifecycle alerts" (2026-09-15). That commit added `G7JPAKE.swift`, `G7Authenticator.swift`, `G7AuthCryptoTests.swift`, `G7JPAKETests.swift` and `G7P256Tests.swift`. It reached `next-dev` through merge `7da3b69` (PR #67, 2026-09-20). Neither `main` nor the `0574a74` tip of 2026-09-26 contains it (`git merge-base --is-ancestor`). Later `next-dev` commits that touch g7sim directly:

- `2a8716c` (#86, 2026-10-10), "Identify genuine vs simulated G7 sensors from their identity certificate". It pins the vendor intermediate and g7sim's dummy CA as trust anchors, verifies the challenge signature, shows a "Simulated Sensor" warning in settings, and marks every reading's HealthKit device as manufacturer "g7sim (Simulator)" with no vendor UDI (`G7CGMManager.swift`, `device`).
- `1a87aad` / `8fa9c73` (#89, 2026-10-11), "Pair for real in the Simulator when a Bluetooth bridge is injected". When ImpossiBLE's classes are present, pairing takes the real path instead of the Simulator stand-in (`G7PairingService.swift`, `simulatorHasBluetooth`).
- `e995628` (#90, 2026-10-11) records G7 states without reliable glucose as `sensorIssue` CGM events, and `e240399` (#94, 2026-10-13) tags backfilled samples `isBackfill`.

The README credits Juggluco and xDrip for the knowledge of the authentication protocol.

### 6.2 Shared test vectors

**Method.** This follows the 2026-09-30 census (§0 of its device annex). Every hex literal of 16 or more hex digits was extracted, along with byte arrays of 8 or more `0x` elements. Literals made of one repeated digit were dropped, and each project's set was intersected with the others. Per project, both test files and all source files were scanned. Script and output: `hexlits.py` and `hex-intersections.json` in the session scratch directory. Vendored code (`third_party`, `vendor`) is excluded. A shared hex-alphabet string (`0123456789abcdef…`, a lookup table) is counted below as noise.

| Pair | Shared literals | What they are |
|---|---|---|
| g7sim tests ∩ G7SensorKit `next-dev` tests | 8 | the 2 AES-challenge known-answer cases (6 literals) and the 2 captured extended-version replies |
| g7sim all ∩ G7SensorKit `next-dev` all | 9 | the 8 above and 1 credential constant used by the display-authentication step |
| g7sim ∩ xdripswift | 2 (+1 noise) | the 2 captured extended-version replies (in `DexcomG7CalibrationTests.swift`) |
| g7sim ∩ Juggluco | 2 (+1 noise) | 2 credential constants in `cpp/dexcom/ecJPake.cpp` (source, not tests) |
| g7sim ∩ xDrip (`libkeks`, tests) | 0 (+1 noise) | – |
| g7sim ∩ xdrip-js `dev` (`lib/keks_plugin`, `test`) | 0 | – |
| G7SensorKit `next-dev` tests ∩ xdripswift tests | 2 | the same 2 version replies. This is the census's "G7SensorKit∩xdripswift 2". |
| G7SensorKit `next-dev` ∩ xdrip-js `dev` | 3 | the published P-256 curve parameters (G7SensorKit `G7P256.swift`; xdrip-js `test-keks-curve-test.js`) |
| G7SensorKit `next-dev` ∩ Juggluco | 2 | 1 J-PAKE constant and 1 credential constant (source) |

**Independent reproduction.** Both AES-challenge known answers that g7sim shares with G7SensorKit were recomputed with `openssl enc -aes-128-ecb -nopad` (OpenSSL 3.0.13): 2/2 match. A control with a one-nibble change to the key gave a different output in both cases.

**What remains unshared.** No EC-JPAKE transcript or proof vector appears in more than one project. g7sim's J-PAKE test and G7SensorKit's `G7JPAKETests` are both agreement tests against a mirror written in the same repository. G7SensorKit's mirror has its own transcript-hash helper and fixed-seed keys. Neither is a known-answer test against an external reference.

### 6.3 Executed cross-check: emulator identity

A scratch Go test parsed the emulator anchor certificate embedded in G7SensorKit `next-dev` (`G7SensorIdentity.swift`, `emulatorAnchor`). It checked that a leaf certificate freshly issued by g7sim (`NewSensorIdentity(…).CertChain()[1]`) verifies against it: pass. The control was a leaf with the same names signed by a different P-256 key. It was rejected with `x509: ECDSA verification failure`. An earlier control that corrupted the anchor's public key failed for an unrelated reason (the point would not parse) and was discarded. So g7sim's dummy CA and G7SensorKit's "simulated" anchor are the same key at these two shas.

---

## 7. Integration surface

### 7.1 Loop

- **Which Loop.** LoopWorkspace `next-dev` @ `1561bff0` (2026-10-15) pins G7SensorKit `e17129d`, which has the direct connection, the Simulator bridge path and the identity check. LoopWorkspace `dev` @ `c1f55970` (2026-10-17) and `main` @ `548b3324` (2026-10-05) pin G7SensorKit `dd91f46`, which listens passively (all read through `gh api repos/LoopKit/LoopWorkspace/contents/G7SensorKit?ref=…`). The local LoopWorkspace clone (`f841285`, 2026-09-19) pins `c2abb4f`, which predates both. Pairing with g7sim therefore needs a Loop built from LoopWorkspace `next-dev`. This is an inference from the pins. A passive-mode G7SensorKit does not authenticate, and g7sim delivers readings only after authentication.
- **How it pairs in the Simulator** (README). Start g7sim with `-transport impossible -fresh -code 4321 -serial 7810293746`. These are the stand-in applicator values G7SensorKit offers in the Simulator, so both "scan" and manual code entry find this sensor. Build the dylib with `simulator/build-impossible.sh`, then launch Loop with `SIMCTL_CHILD_DYLD_INSERT_LIBRARIES=<dylib> xcrun simctl launch <simulator> <bundle id>`. Loop's source is not changed. ImpossiBLE's own menu-bar app must be quit first, because g7sim refuses to start while another provider answers on the socket (`NewSimRadio`).

### 7.2 Trio

nightscout/Trio `dev` and `main` both pin `loopandlearn/G7SensorKit` at `dd91f465` (`gh api repos/nightscout/Trio/contents/G7SensorKit?ref=…`, 2026-10-17). That is the passive line. The `loopandlearn/G7SensorKit` fork has no `G7SensorKit/Crypto` directory at its head (API returns 404). No Trio build in these pins can pair with g7sim. This is an inference from the pins. No Trio run was attempted.

### 7.3 LoopKit/pod

LoopKit/pod and g7sim share an approach, not code. Each vendors its own copy of `paypal/gatt` at the same upstream version. g7sim's copy carries the fixes in §2. Each has its own `-transport impossible`. pod gained its Simulator transport, a web control panel and a JSON API in `3f82784` (#21, 2026-10-12), whose message names g7sim as the model. ImpossiBLE patches 0004 and 0006 were added for OmnipodKit's behaviour, and `impossible-mux` exists so that one Loop can run against g7sim and pod together. LoopKit/pod has had a GitHub Actions workflow running `go test ./...` since `1d34e9b` (2026-05-23). At `a491a5e` its suite passes offline: 4 packages `ok`, 7 `func Test` in 5 files. `loopandlearn/pod` @ `ec13f46` (2025-12-05), the clone the 2026-09-30 census read, is an ancestor of LoopKit/pod `a491a5e`.

### 7.4 trio-test-harness

jwoglom/trio-test-harness @ `c3c1bfe` drives Trio and Loop in the iOS Simulator with the apps' built-in fake devices only: Trio's Glucose Simulator, Loop's CGM Simulator and the Pump Simulator. A search for `g7sim`, `impossible` and `faketandem` outside `.git` finds only those built-in simulator names. Nothing in the harness injects ImpossiBLE. A separate trio-test-harness deep dive covers the harness in detail.

### 7.5 CI

g7sim has no workflow (summary table). Its whole suite runs without Bluetooth hardware, a Mac or network access, so a Linux CI job could run it. The Simulator transport also runs on Linux (§3). Only the app side needs macOS.

---

## 8. Relevance to Nightscout

With g7sim feeding a Loop built from LoopWorkspace `next-dev` in the Simulator, and Loop's Nightscout service configured, the following records would reach a Nightscout site. Each line is **inferred from code at the cited shas**. None of this was run end to end here.

| Record | Source in code | What g7sim controls |
|---|---|---|
| `entries`, type `sgv`: one per reading, including backfilled ones | NightscoutService `ace20b0f` `StoredGlucoseSample.swift`: glucose, date, `device`, trend, `changeRate`, `isCalibration`, `isBackfill`, `receivedTime` | the value and its shape (sine/fixed/walk), gaps and recovery (stop g7sim or the app, then backfill), warm-up and expiry, calibration offset |
| The `device` string on those entries | `"\(manufacturer) \(model) \(name)"`, with G7SensorKit `next-dev` setting manufacturer "g7sim (Simulator)" and model "<model> Simulator" for a simulated sensor | always marks the data as simulated, so test uploads are distinguishable from real-sensor data on the server |
| `treatments`, `eventType` "Sensor Start" | `PersistedCgmEvent.swift` `.sensorStart` | a new sensor (`-fresh`, `/new`) |
| `treatments`, `eventType` Note "CGM: <state>" | `PersistedCgmEvent.swift` `.sensorIssue` (at `ace20b0f`), fed by G7SensorKit `e995628` | `algorithmState` in `POST /glucose` |
| `devicestatus` (loop and pump status) | Loop's loop cycle | indirectly: Loop needs a pump as well (its Pump Simulator, or LoopKit/pod through `impossible-mux`). g7sim supplies only the CGM. |

How `isBackfill` and `receivedTime` serialise into the uploaded JSON depends on NightscoutKit and was not checked. Together with Loop's background wake and relaunch behaviour (§1.5), this setup could give server-side testing upload traffic that is realistic, controllable and labelled. That includes the timing gaps, catch-up batches and duplicate-prone backfill that real G7 users generate. This is an inference. It has not been measured against a Nightscout server.

---

## 9. What is not covered

- **Hardware.** Fresh pairing against a real phone over the air, the Pi "runs on" claims, and Loop in the Simulator were not reproduced here (no Pi, no Mac).
- **Fault injection.** There is no frame-level injection: no dropped, duplicated, reordered or corrupted notifications, and no disconnect mid-command. The fault surface is the sensor's own states (forced algorithm state, warm-up, expiry), forgetting keys, the lockout, provider restarts through the mux, app termination and force-quit, and `NO WAKE PATH` accounting.
- **Clock.** Readings are timed by wall-clock time. There is no controllable or skewable clock (README: a Pi without an RTC must be NTP-synced).
- **Device-side request log.** There is none apart from the process log. `/status` gives state, not a history of requests.
- **Fidelity gaps** the code states or shows: link-layer refusal (§1.2), unenforced client-proof and display-signature checks (§1.3), and the four relaunch differences from iOS (§1.5).
- **Protocols.** G7 family only (G7, ONE+, Stelo). No G6, Libre or other CGM.

---

## 10. Reproduce

```bash
cd externals/g7sim                                   # at 7c039de5
GOPROXY=off GOFLAGS=-mod=mod go test -count=1 -v ./... | grep -c '^--- PASS'     # 33
grep -h '^func Test' $(git ls-files '*_test.go') | wc -l                          # 33
GOPROXY=off GOFLAGS=-mod=mod go test -race -count=1 ./... && go vet ./...
git -C externals/stack/LoopKit__G7SensorKit fetch origin
git -C externals/stack/LoopKit__G7SensorKit merge-base --is-ancestor 7da3b69 origin/main    # exit 1
git -C externals/stack/LoopKit__G7SensorKit merge-base --is-ancestor 7da3b69 origin/next-dev # exit 0
gh api repos/LoopKit/LoopWorkspace/contents/G7SensorKit?ref=next-dev --jq .sha   # e17129d…
gh api repos/nightscout/Trio/contents/G7SensorKit?ref=dev --jq .sha              # dd91f465…
gh api 'repos/mickeyl/ImpossiBLE/pulls?state=all' --jq '.[] | "\(.number) \(.state)"'
```
