# Device layer: drivers, simulators, protocol work, and V&V

*Contributor-facing. Annex to the [stack census record of 2026-09-30](../stack-census-2026-09-30.md); a snapshot, not rewritten as the world moves. Prepared by research agents from the clones and pages named in it, and checked by the session that wrote the record.*

Measured 2026-09-30 from fresh clones under `externals/stack/<owner>__<repo>`. The manifest is `tools/programme/stack-census/repos.tsv` (layers `device` and `controller`). For four repositories a second checkout of the `dev` branch sits under `externals/stack/.dev/`. Where the `dev` branch is the active line, the figures below use it and name it.

Scope: the BLE and radio drivers for CGMs and insulin pumps, the simulators, the protocol reverse-engineering, and the cryptography. Disclosure level: this file names mechanisms and protocol families only. It contains no keys, key-derivation constants, command sequences or bypass steps.

## 0. How the numbers were made

- **Test files.** Source files (`.swift .kt .java .go .py .js .c/.cpp`) under a test directory, or named with a test convention (`*Tests/`, `/test/`, `jvmTest`, `androidTest`, `*_test.go`, `test_*.py`, `*Test.kt`, and so on). Vendored code is excluded.
- **Test declarations.** The number of lines matching `@Test`, `func test…(`, `func Test…(` (Go), `def test_` and `it(`/`test(` (JS). This is a lower bound for data-driven tests and for Python doctests. For those two cases the count was made separately and is noted where it applies.
- **Activity.** Commit and author figures are not repeated here; the census table (`tools/programme/stack-census/results/census-2026-09-30.md`) is the one place for them.
- **Licence.** Taken from the top-level `LICENSE*` or `COPYING*` file, or from `package.json`. "none found" means there is no such file in the checked-out tree.
- **Shared vectors.** Every hex string literal of 16 or more hex digits in each project's tests was extracted and normalised. For Dana and Medtrum the tests use byte arrays, so byte-array literals of 8 or more elements were extracted instead. The resulting sets were then intersected between projects. A shared literal means the same bytes appear in both test suites. Usually this means the tests were copied or ported.

## 1. Per-project inventory

### 1.1 iOS kits (Swift): loopandlearn

| Repo @ sha | Devices / protocol | Crypto family (as named in code) | Tests: files / decl. | What the tests exercise | Simulator | CI | Licence |
|---|---|---|---|---|---|---|---|
| loopandlearn/OmnipodKit, `dev` @ 929dc47 (2026-09-28); `main` @ 4e923d7 | Omnipod Eros (over RileyLink), Omnipod DASH (BLE), Omnipod 5 ("O5" pod type in `OmnipodKit/OmnipodCommon/PodType.swift`). Replaces OmniKit and OmniBLE (README). | DASH: EAP-AKA with Milenage, X25519 key agreement, AES-CCM, AES-CMAC. O5: P-256 key agreement, P-256 ECDSA message signing with a certificate store (`Bluetooth/Pair/O5CertificateStore.swift`), App Attest service (`Services/O5AppAttestService.swift`) | 37 / 189 | Message and packet encode/decode with hex vectors (`OmniTests/…/MessageTests.swift`, `PacketTests.swift`), CRC8 and CRC16, basal, bolus and temp-basal tables, pod state, `PodCommsSessionTests` (mock transport), DASH key exchange (1 test, fixed vectors), en/decrypt, O5 BLE framing fixtures, O5 message signing (6 tests) | none in repo; `loopandlearn/pod` (DASH) | none | none found |
| loopandlearn/DanaKit @ 79f492f (2026-09-26) | Dana-i and Dana RS pumps over BLE (README says it is ported from `bastiaanv/danars-js`) | Vendor-specific encryption modes. No standard primitive is named in the code. | 6 / 87 | Command encoding and encryption (`DanaKitTests/Encryption/EncryptTests.swift`, 14 tests), decryption, packet generation, CRC | `loopandlearn/dana-simulator` | none | MIT |
| loopandlearn/dana-simulator @ 92c79e4 (2024-10-01) | Dana-i / Dana RS v3 pump side, as a BLE peripheral on a Raspberry Pi (Go), with a React web client (`client/`) | Pump-side encryption (`server/encryption.go`) | 0 / 0 | none | is the simulator. README: it cannot reproduce the iOS pairing-PIN prompt. | none | none found |
| loopandlearn/MedtrumKit @ ef866fa (2026-09-26); the same HEAD as jbr7rr/MedtrumKit | Medtrum TouchCare Nano patch pump, 200 U (MD0201, MD8201) and 300 U (MD8301) | Vendor-specific key derivation and encryption. No standard primitive is named. | 20 / 49 | One test file per packet (authorize, bolus, temp basal, basal profile, prime, activate, synchronize and others) plus `CryptoTests` (2) | none | none | MIT |
| bastiaanv/EversenseKit @ e6ee8d0 (2026-09-28); the fork is loopandlearn/EversenseKit | Eversense E3 (90 and 180 day) and Eversense 365 | P-256 key agreement, P-256 ECDSA, AES-CCM, AES-CBC, HMAC-SHA256 (`EversenseKit/…/CryptoUtil.swift`) | 6 / 34 | `CryptoUtilTests` (6: session generation, signature, public-key decrypt, salt), chunk reassembly, packet-length guard, notification header | none | none | none found |
| loopandlearn/AccuChekKit @ 8105375 (2026-09-28); first commit 2026-02-01 | Accu-Chek SmartGuide CGM. README: only EU/NL sensors confirmed; "advanced security" variants are not yet compatible. | P-256 ECDH key exchange with HMAC-SHA256 confirmation (`KeyExchangeEcdConfirmationPacket.swift`, `AcsAdapter+Crypto.swift`) | 6 / 19 | CGM packet encode/decode (calibrate, calibration read, measurement, start time, status, session time zone). No crypto tests. | none | none | none found |
| loopandlearn/LibreCRKit @ c562170 (2026-08-31); first commit 2026-05-27 | FreeStyle Libre 3: NFC activation, BLE pairing and authorisation, data-plane decode. It is a Swift package described as "clean-room", with an iOS harness app `Apps/LibreCR` and `protocol.md`. | ECDH on P-256, AES-CCM, AES-CMAC, SHA-256 | 15 / 160 | AES-CCM against the RFC 3610 packet vector, plus a tamper test (`Tests/LibreCRKitTests/AESCCMTests.swift`); key schedule, session key, BLE framing, NFC activation command, data-plane decode, sensor-state loader | none (the live-device harness app is not a simulator) | none (README: `swift test`) | MIT |
| loopandlearn/LibreLoop @ 415b799 (2026-09-13); first commit 2026-05-12 | Libre 3 CGMManager for Loop, built on LibreCRKit | through LibreCRKit | 1 / 8 | CGM manager state | none | none | MIT |
| loopandlearn/pod @ ec13f46 (2025-12-05) | Omnipod DASH **pod side**, as a BLE peripheral on a Raspberry Pi (Go) | EAP-AKA/Milenage (vendored `wmnsk/milenage`), X25519, AES-CCM, AES-CMAC | 2 / 2 (`pkg/eap/eap_test.go`, `pkg/message/message_test.go`) | EAP message parse, message parse | is the simulator: dynamic reservoir level, total delivery, alerts and faults; an optional 3-minute disconnect; WebSocket API for a separate front end | none | GPL-3.0 |

Trio (`nightscout/Trio` @ c0160aeaf) pulls all of the kits above except `pod` and `dana-simulator` as git submodules from `loopandlearn/*` (`.gitmodules`). Its `unit_tests.yml` runs on PRs and pushes to `dev`. It runs the "Trio Tests" scheme and `swift test` on `AlgorithmPackage`. No kit test target is referenced in Trio's project files, so the kits' own tests are not run by any CI found in the clones.

### 1.2 iOS kits (Swift): LoopKit

The LoopKit kits all show commits dated 2026-09-26, which look like a shared maintenance sweep.

| Repo @ sha | Devices / protocol | Crypto family | Tests: files / decl. | What the tests exercise | CI | Licence |
|---|---|---|---|---|---|---|
| LoopKit/OmniBLE @ 29358d5 (2026-05-29) | Omnipod DASH | EAP-AKA with Milenage (`OmniBLE/Bluetooth/Session/Milenage.swift`), X25519, AES-CCM, AES-CMAC | 21 / 115 | Message encode/decode hex vectors, payload split/join, string-length-prefix encoding, `KeyExchangeTests` (1, fixed vectors), `EnDecryptTests`. No Milenage known-answer test. | none | MIT |
| LoopKit/OmniKit @ 2b4253b (2026-05-12) | Omnipod Eros over RileyLink (433 MHz) | none (Eros uses a nonce scheme and CRC) | 13 / 109 | Packet and message hex vectors, CRC8 and CRC16, basal, bolus and temp-basal, pod state, `PodCommsSessionTests` | none | none found |
| LoopKit/RileyLinkKit @ 049f0d5 (2026-09-26) | RileyLink BLE-to-sub-GHz bridge (host side) | none | 4 / 3 | Response buffer, radio firmware version, RF packet | `.travis.yml` only | MIT |
| LoopKit/MinimedKit @ a7b2685 (2026-09-26) | Medtronic 5xx/7xx (x12–x54) over RileyLink, MySentry | none | 58 / 164 | Message bodies (read settings, temp basal, battery, remaining insulin and others), history and glucose page decode, timestamped events, CRC8 and CRC16; `MockRileyLinkDevice` / `MockRileyLinkProvider` test doubles | none | none found |
| LoopKit/CGMBLEKit @ 242a09d (2026-09-26) | Dexcom G5 and G6 transmitters | AES-based challenge–response (`CGMBLEKit/AESCrypt.m`, CommonCrypto) | 10 / 35 | Rx message decode (glucose, backfill, calibration, session start and stop, time, version), transmitter ID, "Anubis" detection | `.travis.yml` only | MIT |
| LoopKit/G7SensorKit @ 0574a74 (2026-09-26) | Dexcom G7 / ONE+. README: "Requires use of official G7 app", so this kit listens alongside the vendor app and does not authenticate itself. | none in the kit | 4 / 28 | G7 glucose message decode (with calibration, lifecycle, negative rate), extended version, CGM manager | none | MIT |
| LoopKit/LibreTransmitter @ 4110512 (2026-09-26) | Libre 1 (US and international), EU Libre 2 through MiaoMiao/Bubble bridges and direct over BLE, NFC | Vendor-specific Libre 2 payload decryption; no standard primitive is named | 1 / 2 | minimal | `.travis.yml` only | MIT |

The `.travis.yml` files and README badges point at travis-ci.org. No GitHub Actions workflow exists in these repositories.

### 1.3 Android and JVM

| Repo @ sha | Devices / protocol | Crypto family | Tests: files / decl. | What the tests exercise | Simulator | CI | Licence |
|---|---|---|---|---|---|---|---|
| nightscout/AndroidAPS, `dev` @ 550605ee36 (2026-09-30); `master` @ 598e2eb39c (2026-08-02) | In-tree **pump** drivers, listed below. In-tree **CGM** sources are all app-to-app broadcast or intent receivers (`plugins/source`: Dexcom via a companion app, xDrip, Glimp, Poctech, Tomato, MM640g, Aidex, Syai, Glunovo, Intelligo, Instara, patched Sibionics/Sinocare apps, NotificationReader, NSClient, Random BG). No BLE CGM driver is in the tree. | Per driver, listed below | pumps total on `dev`: 678 / 5,810 (`@Test` lines); `plugins/source` 35 / 209 | Per driver, listed below | `pump/virtual` (virtual pump, 3 / 14) | CircleCI runs unit tests plus jacoco (`.circleci/config.yml`). GitHub Actions `pr-ci.yml` builds APKs. `dev` adds `unit-tests.yml`. | AGPL-3.0 |
| NightscoutFoundation/xDrip @ 9898cb8e0 (2026-09-25) | Dexcom G5/G6 (Ob1 collector, `g5model`), G7 / ONE / ONE+ (`libkeks`), Libre via NFC and bridges (Blukon, MiaoMiao, Bubble, LimiTTer, Wixel variants), Medtrum A6 CGM (`cgm/medtrum`), CareSens and other BLE glucose meters (`glucosemeter/`), Aidex receiver, Eversense and CareSens Air through companion apps (README), UI-based collector | Dexcom G5/G6: AES-based challenge–response. G7 / ONE+: EC-JPAKE on P-256 (`libkeks/src/main/java/…/keks/Calc.java`). Medtrum: vendor-specific (`CryptTest`). | 194 / 884 overall; **device-driver tests: 12 / 39** (`g5model/FastCRC16Test`, `RawScalingTest`, `LibreCrcTest`, `LibreUtilsTest`, `NFCReaderXTest`, `cgm/medtrum/CryptTest`, `InboundStreamTest`, caresens `TimeTxTest`/`ContextRxTest`, `BluetoothGlucoseMeterStartTest`, LibreWifi) | CRC, raw scaling, Libre CRC, Medtrum decrypt and inbound stream, meter message decode. The remaining ~180 files cover followers, uploaders and UI. `libkeks` has no tests. | none | `unit_test.yml` runs `testProdReleaseUnitTest` | GPL-3.0 |
| jwoglom/pumpX2 @ f13ccf96 (2026-09-28) | Tandem t:slim X2 and Mobi: BLE protocol library (Java core plus Android library, and `cliparser`) | EC-JPAKE pairing, HMAC-SHA256, HKDF | 418 / 968 | Per-message request and response encode/decode against captured hex (for example `messages/src/test/…/currentStatus/*Test.java` through `MessageTester.test(hex, …)`): currentStatus 132 files, historyLog 123, control 114, authentication 14 (the J-PAKE 1a/1b/2/3/4 request and response tests), `SimulatedJpakeAuthBuilderIntegrationTest`, `JpakeShortScalarTest`, with a `SecureRandomMock` for deterministic handshakes | `jwoglom/faketandem` consumes pumpX2 | `android.yml` runs `testDebugUnitTest` and `:messages:test`; `code-coverage.yml` runs jacoco | MIT |
| jwoglom/controlX2, `dev` @ ad2b637d (2026-09-19); `main` @ 45e3795b | Android phone and Wear OS controller app for Tandem pumps, over pumpX2 | through pumpX2 | 39 / 402 | Mostly the database layer (Nightscout and xDrip sync), view models, Wear snapshots. Protocol tests live in pumpX2. | uses faketandem for integration (faketandem `GAP_ANALYSIS.md`) | `android.yml` runs `testDebugUnitTest` | none found |
| j-kaltes/Juggluco @ db70dc1 (2026-09-30) | Direct-to-phone reader. README lists Libre 2/2+/3/3+, Sibionics GS1, Dexcom G7 / ONE+, Accu-Chek SmartGuide, CareSens Air, Aidex X; there is also `Common/src/main/cpp/EverSense.cpp`. NovoPen NFC. Wear OS app. | Dexcom G7: EC-JPAKE (`Common/src/main/cpp/dexcom/ecJPake.cpp`). Libre 3: ECDH and AES-family (`cpp/libre3/`). Vendored OpenSSL/BoringSSL headers. | 2 source files; there is no unit-test framework. `cpp/air/tests/` is a replay harness with recorded runs (`testdata/`, `Makefile`), and there is `cpp/abbotttest.cpp`. | CareSens Air decode replay against recorded data | none | none | GPL-3.0 |

AndroidAPS in-tree pump drivers on `dev` @ 550605ee36 (`pump/`). "Shared" is the number of test-vector literals that also appear in the iOS counterpart (method in §0).

| Driver dir | Device(s) (from `PumpType.*` and plugin names) | Crypto family named in code | Test files / `@Test` | Notes |
|---|---|---|---|---|
| `omnipod/eros` | Omnipod Eros over RileyLink | none | 29 / 102 (on master) | shares 46 hex vectors with OmniKit |
| `omnipod/dash` | Omnipod DASH | EAP-AKA/Milenage, X25519, AES-CCM, AES-CMAC | 28 / 57 (on master) | `MilenageTest` (4, fixed vectors), `EapMessageTest`, `KeyExchangeTest`, `EnDecryptTest`, command and response encode tests; shares 58 hex vectors with OmniBLE |
| `omnipod/common` | shared | – | 4 / 60 (on master) | Figures for all of `omnipod` on dev: 70 / 283 |
| `rileylink` | RileyLink bridge (host) | none | 19 / 315 | CRC8-heavy radio-packet tests |
| `medtronic` | Medtronic 512/712 … 554/754 (Veo) | none | 14 / 158 | shares 0 vectors with MinimedKit |
| `dana` (`danar`, `danars`, `common`) | Dana R / R v2 / R Korean, Dana RS, Dana-i | vendor-specific (`BleEncryptionTest`) | 134 / 396 | ~45 per-packet `DanaRsPacket*Test`; shares 0 byte vectors with DanaKit |
| `medtrum` | Medtrum Nano and 300U | vendor-specific | 32 / 114 | per-packet tests plus `CryptTest`; shares 7 byte vectors with MedtrumKit |
| `combov2` (`comboctl`) | Accu-Chek Combo | Twofish-based cipher (`comboctl/…/CipherTest.kt`), CRC16 | 24 / 122 | frame, transport layer, display frame, nonce, CRC, cipher, PumpIO |
| `insight` | Accu-Chek Insight | HMAC (named in code) | 20 / 140 | |
| `diaconn` | Diaconn G8 | none named | 110 / 681 | |
| `eopatch` | EOFlow EOPatch2 | ECDH on secp256r1 | 62 / 668 | |
| `equil` | Equil | AES (a utility class; `AESUtilTest`), AES-GCM, SHA-256, CRC | 52 / 694 | |
| `carelevo` | CareMedi CareLevo patch pump (first commit 2026-04-21) | none named | 131 / 2,127 | ble/commands 25 files, use-cases 24, patch-flow UI 8 |
| `virtual` | Virtual pump | – | 3 / 14 | |

AndroidAPS `dev` also contains `core/objects/src/commonTest/…/crypto/CryptoPrimitivesVectorsTest.kt`. It runs one set of fixed-string vectors (RFC 6070 PBKDF2 and the NIST GCM set) against both the JVM and the iOS crypto implementations, "so that the two cannot quietly drift apart". It covers export crypto rather than device protocols, and it is the only cross-platform known-answer arrangement found in the controller repositories. It is a direct precedent for §4.

### 1.4 iOS reader apps (Swift)

| Repo @ sha | Devices | Crypto family | Tests | CI | Licence |
|---|---|---|---|---|---|
| JohanDegraeve/xdripswift @ c268542e (2026-09-22) | Dexcom G5/G6, G7 / ONE+ / Stelo (`BluetoothTransmitter/CGM/Dexcom/G7`, with authentication in `Generic/DexcomG7AuthSession.swift`), Libre 2 direct, MiaoMiao, Bubble, Medtrum TouchCare Nano CGM. Libre 3 is used only as a BLE "heartbeat" (`BluetoothTransmitter/HeartBeat`). | G7: J-PAKE on P-256 through vendored micro-ecc (`Generic/DexcomG7ECC.c`) | 25 / 538 overall; device-related: `CGMG5SensorSessionDetectionTests` 18, `DexcomG6SensorLabelTests` 21, `DexcomG6BluetoothSlotTests` 8, `DexcomG7CalibrationTests` 40, `Libre2FrameAssemblerTests` 3, `BluetoothSignalStrengthTests` 17 (107 in total); `CareLinkTests` 107 (cloud). There is no test for the G7 authentication session. | `build_xdrip.yml` builds with fastlane and uploads to TestFlight. No test step was found in `fastlane/Fastfile`. | GPL-3.0 |
| gui-dos/DiaBLE @ e6a909c (2026-07-30) | Research app. `DiaBLE/Sensor.swift` lists Libre 1, US 14-day, Pro/H, Libre 2, 2 Gen2, 3, X, Lingo, Select, Instinct, Dexcom G6, ONE, G7, ONE+, Stelo. | Libre 3: ECDH on P-256, AES-CCM. Dexcom G7: the J-PAKE exchange is logged and marked `TODO` in `DiaBLE/DexcomG7.swift`, so it is not implemented. | 0 / 0 | none | MIT |

### 1.5 JavaScript and Go

| Repo @ sha | Devices | Crypto family | Tests | Simulator | CI | Licence |
|---|---|---|---|---|---|---|
| xdrip-js/xdrip-js, `dev` @ e301273 (2026-08-10); `master` @ 0cd1c55 (2022-04-30) | Dexcom G5/G6. G7 on `dev` through `lib/keks_plugin/`, a JavaScript port of xDrip's `libkeks` (stated in the file header). Used by OpenAPS rigs. | AES-based challenge–response (G5/G6); EC-JPAKE on P-256 (G7) | `dev`: 12 / 35 (mocha). Keks tests: curve-parameter checks against the published secp256r1 values, an Alice/Bob shared-key agreement check, a BLE packet round trip, and the plugin state machine. | none | `nodejs.yml` runs `npm test` on Node 8/10/12 | MIT (`package.json`) |
| jwoglom/faketandem @ 5afb93f (2026-09-29) | Tandem pump **simulator**, forked from the `pod` simulator (README) | pump-side EC-JPAKE through pumpX2's `cliparser` jar; HMAC-SHA256, HKDF | 43 / 245 (`func Test`) | Is the simulator. It has a BLE transport (Linux) or a **virtual TCP/JSON GATT transport** for Mac and CI (`docs/virtual-gatt-protocol.md`), and an integration-harness HTTP API: a controllable clock with manual step and skew, a pump-side request log, pump-initiated actions, and **fault injection** armed per message (`pkg/faults`, `pkg/harness`). There are J-PAKE stress and failure tests. `GAP_ANALYSIS.md` (dated 2026-04-03, so it predates later commits) counts about 40 of about 50 currentStatus requests and about 10 of about 50 control requests as handled. | `ci.yml`: `go vet`; unit tests with `-race` and coverage; an integration job that builds pumpX2's cliparser and runs `go test ./pkg/handler`; lint; an ARM cross-build | GPL-3.0 |

### 1.6 Medtronic 7xxG (OpenMinimed)

All OpenMinimed repositories address the MiniMed 700-series BLE pumps (for example the 780G) and the Guardian 4 transmitter.

| Repo @ sha | Content | Crypto family | Tests | CI | Licence |
|---|---|---|---|---|---|
| OpenMinimed/Documentation @ 73a7811 (2026-09-17) | Protocol notes: GATT conventions and streaming; pump services (Certificate Management, CGM, History and Trace, Insulin Delivery (IDD), Network Operational State, Secure Session Establishment); `sake.md`; `key_databases.md` | SAKE: AES-128 with ECB, CTR and CMAC modes (per the docs) | – | none | none found |
| OpenMinimed/PythonSake @ 1ebbdb2 (2026-08-18) | Python implementation of the SAKE handshake (client, server, session, sequence crypto) | as above | 2 files. The self-tests run through `python -m pysake.session`, `pysake.server` and `pysake.client`, which replay a recorded handshake transcript held in `pysake/constants.py`. There is no test framework. | none | GPL-3.0 |
| OpenMinimed/JavaSake @ 64ae39d (2026-07-07); first commit 2026-05-11 | Java port that "mirrors the public surface of PythonSake"; published to Maven Central (`RELEASING.md`) | as above | 14 / 66. `AesEcbTest` and `AesCtrTest` use NIST SP 800-38A Appendix F vectors, `AesCmacTest` uses RFC 4493, and `SessionTest`, `SakeClientTest` and `SakeServerTest` replay the pysake transcript (6 vectors shared with pysake), with a deterministic `QueuedRngSource`. | `build.yml` runs `./gradlew build` (tests included); `release.yml` | GPL-3.0 |
| OpenMinimed/PythonPumpConnector @ 4ed3497 (2026-08-21) | Linux BLE client for the 700-series pump (`ble/`, `cgm/`, `history/`, `idd/`, `services/`). README warning: proof-of-concept for reverse engineering. | SAKE through PythonSake | 0 / 0 | none | GPL-3.0 |
| OpenMinimed/JavaPumpConnector @ 4bc456a (2026-06-26) | Skeleton Android app over JavaSake | SAKE | 2 / 2 (template example tests) | `build.yml`: assemble, lint, `testDebugUnitTest` | GPL-3.0 |
| OpenMinimed/NativeSakeTests @ 9ae1e49 (2026-02-11) | C harness that drives the vendor's native SAKE library for differential comparison (client, server, key DB, hook); README is TODO | SAKE | 8 source files, no assertions | none | none found |
| OpenMinimed/SakeLibraryRE @ d826bf4 (2026-08-09) | Reverse-engineering report of the vendor's SAKE native library (a Ghidra project). It records AES-128 CTR and CMAC, and an SRP-based passkey subsystem in a later library version. | AES-CTR, AES-CMAC, SRP | – | none | none found |
| OpenMinimed/FridaScripts @ b5be3e8 (2026-02-04) | Dynamic-instrumentation scripts for the vendor Android apps (15 files) | – | – | none | none found |
| OpenMinimed/JadxProjects @ 8ab27ad (2026-07-13) | jadx decompiler project files for the vendor apps and the uploader (the apps themselves are not included) | – | – | none | none found |

### 1.7 Historical and decoding

| Repo @ sha | Content | Tests | CI | Last commit | Licence |
|---|---|---|---|---|---|
| openaps/openomni @ 8eda783 | Omnipod Eros RF decoding: the RTL-SDR decoder (`rtlomni/`), the RFCat Python library (`rfcatomni/`), analysis files | 5 Python test files, 24 tests (packet, CRC16, nonce, commands, message); 2 hex vectors shared with OmniKit, OmniBLE, OmnipodKit and AAPS | none | 2026-05-31 (1 commit in 12 m) | MIT |
| openaps/decocare @ bb2aa1e | Medtronic CareLink USB stick protocol (Python 2) | 164 doctest examples in 8 modules | `.travis.yml` (Python 2.7), `circle.yml` | 2016-10-26 | GPL-2.0 or later (the text begins "GNU General Public License") |
| ps2/rileylink @ fed37bc | RileyLink hardware design and firmware (BLE113 plus CC1110) | none | none | 2019-12-18 | MIT |

Adjacent, cloud layer: tidepool-org/uploader @ 22f53325 (2026-09-22) carries USB/BLE read-only drivers for 18 vendor families (`lib/drivers/`: including medtronic, medtronic600, tandem, insulet, dexcom, abbott, roche). Its test tree has 12 driver-related files with 170 `it()` declarations, and CircleCI runs `yarn test`.

## 2. Device family × implementations

Column headings: iOS = Swift, Android = Kotlin/Java, JS, Py = Python, Go, C++. "Sim" means a simulator that exercises the device side exists in the clones. "Shared vectors" is the number of test-vector literals found in more than one project (§0).

| Device family | iOS | Android | JS | Py | Go | C++ | Sim? | Shared vectors across implementations |
|---|---|---|---|---|---|---|---|---|
| Omnipod Eros (RF over RileyLink) | OmniKit; OmnipodKit (Eros) | AAPS `omnipod/eros` | – | openomni (decode) | – | – | no | yes, by copying: OmniKit∩OmnipodKit 165, OmniKit∩AAPS 46, openomni∩each 2 |
| Omnipod DASH | OmniBLE; OmnipodKit | AAPS `omnipod/dash` | – | – | `pod` (pod side) | – | **yes** (`loopandlearn/pod`, Raspberry Pi BLE) | OmniBLE∩OmnipodKit 191 (all of OmniBLE's), OmniBLE∩AAPS 58; the Milenage known-answer test exists only in AAPS |
| Omnipod 5 | OmnipodKit (O5) | – | – | – | – | – | no | n/a (1 implementation) |
| Dexcom G5/G6 | CGMBLEKit; xdripswift; DiaBLE (reader) | xDrip | xdrip-js | – | – | – | no | effectively none: CGMBLEKit∩xdrip-js 1, CGMBLEKit∩xDrip 1, others 0 |
| Dexcom G7 / ONE+ / Stelo | G7SensorKit (passive, needs the vendor app); xdripswift (auth); DiaBLE (auth TODO) | xDrip (`libkeks`); Juggluco (Java plus C++) | xdrip-js `dev` (port of libkeks) | – | – | Juggluco `ecJPake.cpp` | no | G7SensorKit∩xdripswift 2; no authentication vectors are shared |
| Libre 1 / Libre 2 | LibreTransmitter; xdripswift; DiaBLE | xDrip; Juggluco | – | – | – | Juggluco | no | none found |
| Libre 3 | LibreCRKit (+ LibreLoop); DiaBLE; xdripswift (heartbeat only) | Juggluco | – | – | – | Juggluco | no | none. LibreCRKit uses the public RFC 3610 vector for AES-CCM. |
| Eversense E3 / 365 | EversenseKit | Juggluco (`EverSense.cpp`); xDrip through the companion app | – | – | – | Juggluco | no | none |
| Accu-Chek SmartGuide (CGM) | AccuChekKit | Juggluco (`cpp/accu`) | – | – | – | Juggluco | no | none |
| Medtronic 5xx/7xx (x12–x54) | MinimedKit (+ RileyLinkKit) | AAPS `medtronic` + `rileylink` | – | decocare (CareLink USB, historical) | – | – | no. MinimedKit has `MockRileyLinkDevice` test doubles only. | MinimedKit∩AAPS 0 |
| Medtronic 6xxG (640G/670G) | – | AAPS MM640g and xDrip read through companion apps or the cloud; Tidepool uploader `medtronic600` (read) | – | – | – | – | no | – |
| Medtronic 7xxG (780G, BLE, SAKE) | – | JavaPumpConnector + JavaSake | – | PythonPumpConnector + PythonSake | – | NativeSakeTests (harness around the vendor library) | partial. PythonSake and JavaSake both implement the SAKE **server** role, which their tests use. | **yes: JavaSake∩pysake 6** (a recorded transcript replayed in both), plus NIST and RFC vectors in JavaSake |
| Tandem t:slim X2 / Mobi | TandemKit (referenced in the faketandem README; not in the clones) | pumpX2 (+ controlX2) | – | – | faketandem | – | **yes** (`jwoglom/faketandem`, BLE or virtual transport, harness API, fault injection) | pumpX2∩faketandem 17. faketandem uses pumpX2's codec for parsing, so the two are not independent. |
| Dana R / RS / i | DanaKit | AAPS `dana` | (danars-js, not cloned) | – | dana-simulator | – | **yes** (`loopandlearn/dana-simulator`, Raspberry Pi BLE, inactive since 2024-10-01) | DanaKit∩AAPS 0 |
| Medtrum Nano / 300U (pump) | MedtrumKit | AAPS `medtrum` | – | – | – | – | no | MedtrumKit∩AAPS 7 byte vectors |
| Medtrum A6 / TouchCare Nano (CGM) | xdripswift | xDrip | – | – | – | – | no | none found |
| Accu-Chek Combo | – | AAPS `combov2` | – | – | – | – | no | n/a |
| Accu-Chek Insight | – | AAPS `insight` | – | – | – | – | no | n/a |
| Diaconn G8, EOPatch2, Equil, CareLevo | – | AAPS only | – | – | – | – | no | n/a |
| Sibionics GS1, Aidex X, CareSens Air | – | Juggluco (direct); xDrip and AAPS (app-to-app receivers) | – | – | – | Juggluco | no (Juggluco has a CareSens Air replay harness) | n/a |
| RileyLink bridge | RileyLinkKit | AAPS `rileylink` | – | – | – | firmware (ps2/rileylink) | no | none found |

## 3. Duplication: independent implementations per protocol

"Independent" here counts separate code bases that each encode or decode the device protocol. Forks and ports are counted, but they are marked, because a port inherits the original's interpretation.

| Protocol | Implementations (count) | Of which ports/forks | Shared vectors today | Where one reference would help |
|---|---|---|---|---|
| Dexcom G7 / ONE+ authentication (EC-JPAKE family) | **4** that authenticate: xDrip `libkeks` (Java), xdrip-js `keks_plugin` (JS port of libkeks), xdripswift (Swift plus micro-ecc C), Juggluco (C++). One passive (G7SensorKit) and one incomplete (DiaBLE). | 1 (xdrip-js) | 0 authentication vectors; the only crypto tests found are xdrip-js's self-agreement and curve-parameter checks | A shared handshake transcript with fixed randomness (the pumpX2 `SecureRandomMock` and JavaSake `QueuedRngSource` patterns) would let all four check the same exchange. The G7 glucose-message decode has 6 decoders and 2 shared literals. |
| Dexcom G5/G6 | **5**: CGMBLEKit, xDrip, xdripswift, xdrip-js, DiaBLE | – | ≤1 literal between any pair | A single decode corpus (glucose, backfill, calibration, session messages) |
| Libre 2 | **5**: LibreTransmitter, xDrip, xdripswift, Juggluco, DiaBLE | – | none | Payload decrypt and decode vectors |
| Libre 3 | **3**: LibreCRKit (+ LibreLoop), Juggluco, DiaBLE | – | none | NFC activation, handshake transcript, data-plane frames |
| Omnipod Eros | **3** drivers (OmniKit, OmnipodKit, AAPS) + 1 decoder (openomni) | OmnipodKit forks OmniKit | 165 and 46 (copied) | The corpus exists de facto in OmniKit's tests. Extracting it to one file would stop it drifting between copies. |
| Omnipod DASH | **3** (OmniBLE, OmnipodKit, AAPS) + a pod-side simulator | OmnipodKit forks OmniBLE; the AAPS tests share 58 vectors | 191 and 58 (copied) | The Milenage known-answer test exists only in AAPS. Its vectors, plus the public 3GPP Milenage test sets, could run in both Swift implementations. |
| Medtronic 5xx/7xx | **3**: MinimedKit, AAPS `medtronic`, decocare (USB path) | – | 0 | A history-page decode corpus (MinimedKit already holds 199 hex literals) |
| Medtronic 7xxG SAKE | **2**: PythonSake, JavaSake (+ a differential harness against the vendor library) | JavaSake ports PythonSake | 6 plus NIST/RFC | Already the best-structured case: public known-answer tests for the primitives plus a cross-implementation transcript |
| Tandem | **1** client in the clones (pumpX2) + a simulator (faketandem) + TandemKit outside the clones | – | 17 | The pumpX2 test hex (1,334 literals) is a de facto reference corpus. faketandem depends on pumpX2's codec, so a simulator decode path independent of pumpX2 would be needed before faketandem can catch pumpX2 decode errors. |
| Dana RS / i | **2** (DanaKit, AAPS) + a simulator + danars-js outside the clones | DanaKit is ported from danars-js | 0 | Packet and encryption vectors shared between the Swift and Kotlin suites; revive dana-simulator |
| Medtrum pump | **2** (MedtrumKit, AAPS) | the test names mirror each other | 7 | A shared per-packet corpus |
| Medtrum CGM (A6 / TouchCare Nano) | **2** (xDrip, xdripswift) | – | 0 | – |
| Eversense | **2** (EversenseKit, Juggluco) | – | 0 | – |
| Accu-Chek SmartGuide | **2** (AccuChekKit, Juggluco) | – | 0 | – |
| RileyLink host | **2** (RileyLinkKit, AAPS) | – | 0 | – |

Totals: 14 protocols have 2 or more implementations: Dexcom G7 authentication, Dexcom G5/G6, Libre 2, Libre 3, Omnipod Eros, Omnipod DASH, Medtronic 5xx/7xx, SAKE, Dana, Medtrum pump, Medtrum CGM, Eversense, Accu-Chek SmartGuide and RileyLink. Between them there are 41 implementations (counting a port as one, Omnipod Eros including openomni, and only the four authenticating G7 implementations). For 3 of the 14 the shared vectors come from copying tests (Omnipod Eros and DASH, Medtrum pump). For 1 they come from a deliberate cross-check (SAKE). For the other 10 no vectors are shared, or at most 2 literals are. Tandem has a single client in the clones; its 17 shared literals come from the simulator depending on the client library.

## 4. V&V gap for the device layer and the work to close it

### 4.1 What exists

- **Message encode/decode vectors** are the dominant test type. The largest suites are pumpX2 (968 declarations, 1,334 hex literals), the AAPS pump drivers (5,810 `@Test` lines on `dev`, 2,127 of them in CareLevo), LibreCRKit (160 tests, 744 literals), MinimedKit (164) and the Omnipod suites (109–189 per implementation).
- **Crypto known-answer tests (KATs) against external standards.** Five were found in the device layer: JavaSake (NIST SP 800-38A ECB and CTR, RFC 4493 CMAC), LibreCRKit (RFC 3610 AES-CCM vector 1, run as a round trip), AAPS DASH `MilenageTest` (fixed vectors; the source is not stated), and xdrip-js (curve parameters only). In the controller layer there is AAPS `CryptoPrimitivesVectorsTest` (RFC 6070 and NIST GCM). None was found for EAP-AKA/Milenage in Swift, X25519, P-256 ECDH/ECDSA, HKDF, HMAC, EC-JPAKE, or the vendor-specific Dana, Medtrum and Libre 2 schemes.
- **Deterministic handshake tests** use injected randomness in pumpX2 (`SecureRandomMock`), JavaSake (`QueuedRngSource`) and faketandem (J-PAKE integration and stress). The OmniBLE, OmnipodKit and AAPS key-exchange tests use one fixed-vector case each.
- **Simulators.** faketandem is the most complete: a virtual transport that runs in CI, a clock, a request log, fault injection, and an integration job against pumpX2. `pod` covers DASH on a Raspberry Pi, with state and faults but no virtual transport and 2 tests. dana-simulator covers Dana-i / RS v3 on a Raspberry Pi, with no tests and no commits since 2024-10-01. The PythonSake and JavaSake server roles act as a partial SAKE pump peer.
- **Test doubles** below the transport: `MockRileyLinkDevice` (MinimedKit), mock transports in the `PodCommsSessionTests` of OmniKit, OmniBLE and OmnipodKit, and log parsers (`OmniBLEParser`, `OmniKitPacketParser`, `OmniParser`).
- **Fuzzing:** none found. The matches for "fuzz" in xDrip, AAPS and Juggluco are timing and graph "fuzz" factors, not fuzz harnesses.
- **Hardware-in-the-loop:** there are no automated rigs in the clones. The Raspberry Pi simulators and the LibreCR harness app are manual rigs.
- **Records:** no per-release test report or verification record was found in any device repository. Coverage upload exists for pumpX2 and faketandem (codecov/jacoco) and for AAPS (`codecov.yml`).
- **CI that runs device tests:** AAPS (CircleCI), xDrip, pumpX2, controlX2, faketandem, JavaSake, JavaPumpConnector and xdrip-js. **No CI** covers OmnipodKit, DanaKit, MedtrumKit, EversenseKit, AccuChekKit, LibreCRKit, LibreLoop, OmniBLE, OmniKit, MinimedKit or G7SensorKit (RileyLinkKit, CGMBLEKit and LibreTransmitter have legacy `.travis.yml` only), and none covers PythonSake, PythonPumpConnector, Juggluco, DiaBLE, pod or dana-simulator. Trio's test workflow does not reference the kits' test targets.

### 4.2 What a quality-control system for this layer would need

1. One language-neutral **vector corpus per protocol**: frame, direction, characteristic, hex, and decoded fields, with de-identified serials and sensor IDs. Every implementation would load it from its own tests.
2. **Crypto KATs** from public standards for each standard primitive, in each implementation. Where a protocol composes primitives, a fixed-randomness **handshake transcript** shared by all implementations of that protocol.
3. **Simulators** with a virtual transport, following the faketandem model, so that driver integration tests run in CI without radios. They also need fault injection (dropped, duplicated, reordered and corrupted frames, disconnects mid-command, clock skew) and a device-side record of what was received.
4. **Parser fuzzing** of every inbound decoder, in CI.
5. **Hardware-in-the-loop** smoke runs against real devices before release, on a fixed rig.
6. **Records**: for each release of each driver, a test report tied to the sha, listing the vector-corpus version passed, the simulator scenarios run, the HIL runs, and any known gaps.

### 4.3 Work estimate (ESTIMATES, in person-weeks)

These ranges are derived from the counts above, not from measured effort.

**Assumptions:**
- An engineer is familiar with BLE and the host language.
- The vendor protocol is already understood from existing code. No new reverse engineering is included.
- Protocols in scope are the 14 with 2 or more implementations, plus Omnipod 5 and Tandem, which are single-implementation.
- Vectors are extracted from existing test literals where possible (the OmniKit, OmniBLE, pumpX2, MinimedKit, CGMBLEKit and LibreCRKit literals, about 2,700 in total).
- Captures used as vectors are de-identified.
- Maintainers' review time is not included.
- Swift kits need their parsers testable on Linux or macOS runners outside CoreBluetooth.

| Work item | Unit estimate | Scope assumed | Range (pw) |
|---|---|---|---|
| Vector-corpus format, tooling, loaders | 3–6 pw once | one schema and a loader per language (Swift, Kotlin/Java, JS, C++, Python, Go) | 3–6 |
| Seed corpus extraction and curation | 1–2 pw per protocol | 14 protocols | 14–28 |
| Adapters in each implementation | 0.5–1.5 pw per implementation | about 30 implementation × protocol pairs | 15–45 |
| Crypto KATs from public standards | 0.25–0.5 pw per primitive × implementation | about 25 pairs (Milenage ×3, X25519 ×3, AES-CCM ×5, AES-CMAC ×4, P-256 ECDH/ECDSA ×6, HKDF/HMAC ×2, EC-JPAKE ×2) | 6–13 |
| Fixed-randomness handshake transcripts | 1–2 pw per protocol | 7 authenticated protocols (DASH, O5, G7, Libre 3, Tandem, SAKE, Eversense) | 7–14 |
| Bring `pod` and `dana-simulator` to faketandem parity (virtual transport, harness API, faults, CI) | 4–8 pw each | 2 | 8–16 |
| New simulators | 6–18 pw each | 5 priority families (Dexcom G6, Dexcom G7, Libre 2, Libre 3, Medtronic over RileyLink) | 30–90 |
| Parser fuzzing harnesses in CI | 0.5–1 pw per decoder target, plus triage | about 30 decoder targets; triage 5–20 | 20–50 |
| CI for repos that have none | 0.5–1.5 pw per repo | about 15 repos (the iOS ones need macOS runners) | 8–22 |
| HIL rig: build, and integration per device family | 4–8 pw build + 1–2 pw per family | 10 families | 14–28 |
| Release records: template, automation, archive | 2–4 pw once | – | 2–4 |
| **Total one-time** | | | **≈127–316 pw** |
| Ongoing | 0.1–0.2 FTE for rig and corpus upkeep, plus 0.5–1 day per driver release | | |

Notes on the ranges:
- The spread is widest for new simulators. The faketandem history (362 commits since 2021, concentrated between 2025-12 and 2026-09, with a gap analysis still listing about 40 unhandled control requests as of 2026-04) indicates that a full-fidelity pump simulator is a multi-month effort. The low end assumes read and status paths only.
- CGM simulators that authenticate would have to implement the sensor side of the handshake. That places them under the same disclosure constraints as the drivers.
- Fuzzing triage is unbounded until it has been run. The range is a placeholder.

## 5. Wearables and health platforms: what is in the clones

This section is from a grep across all cloned repositories. Only code paths are reported.

| Integration | Repositories and paths |
|---|---|
| Garmin (Connect IQ) | AndroidAPS `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/garmin/` (13 files, plus `androidTest`); Juggluco `Common/src/mobile/java/tk/glucodata/nums/DirectGarminIQ.java`, `GarminIQCodec.java`, `GarminSdkContext.java`, `MyConnectIQListener.java`; iAPS (7 files, for example `FreeAPS/Sources/Assemblies/ServiceAssembly.swift`); Trio (15 files, for example `Model/Helper/CustomNotification.swift`); xDrip lists compatible apps in `utilitymodels/CompatibleApps.java` and serves a local web service with glucose, heart-rate and steps endpoints in `webservices/WebServiceSgv.java`, `WebServiceHeart.java` and `WebServiceSteps.java` |
| Fitbit | sulkaharo/nsfitbit (a Fitbit clock face with a companion: `companion/`, `app/`, `sdk4`, `sdk5`); xDrip `utilitymodels/CompatibleApps.java` and `res/xml/pref_advanced_settings.xml` |
| Wear OS | AndroidAPS `wear/` module; xDrip `wear/` module and `wearintegration/`; Juggluco Wear OS build (`Common/src/small/AndroidManifest.xml`); controlX2 `wear/` (a pump controller on the watch) |
| Apple Watch (WatchConnectivity / WatchKit) | Loop `Loop/Managers/WatchDataManager.swift`; Trio `Trio Watch App Extension/`; iAPS `FreeAPSWatch WatchKit Extension/`; xdripswift `xDrip Watch App/`; nightguard `nightguard/watch/`; LoopCaregiver `…/WatchConnectivityService.swift`; LoopFollow (2 files) |
| HealthKit | Loop, LoopKit (`LoopKitHostedTests/GlucoseStoreTests.swift`, among others), Trio, iAPS, xdripswift `xDrip/Managers/HealthKit/HealthKitManager.swift`, DiaBLE `DiaBLE/Health.swift`, nightguard `external/AppleHealthService.swift` |
| Health Connect | xDrip `app/src/main/java/com/eveningoutpost/dexdrip/healthconnect/` (5 files); Juggluco (`Common/build.gradle`, `Common/src/mobile/AndroidManifest.xml`) |
| Oura | tidepool-org/platform `oura/` (an API client and subscription service, with tests `oura_test.go` and `oura_suite_test.go`); nocturne lists Oura in `src/Web/packages/portal/src/lib/data/connectors.ts` as `comingSoon: true` |
| Whoop | none found |
| Other watches found | Pebble: xDrip (`webservices/WebServicePebble.java`), cgm-remote-monitor `tests/pebble.test.js`, oref0 `bin/oref0-pebble.js`, nsfitbit. Mi Band and Amazfit: xDrip `watch/miband/`, `wearintegration/`. Samsung Tizen: AndroidAPS `plugins/sync/…/tizen/`. LeFun: xDrip `watch/lefun/`. |
