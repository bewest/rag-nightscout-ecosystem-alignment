# trio-test-harness Deep Dive

*Contributor-facing. Measured 2026-10-17 at jwoglom/trio-test-harness `c3c1bfe7` (2026-10-17; first commit
2026-09-19; 73 commits, 71 of them non-merge). **No licence**: the repository has no LICENSE or COPYING file and no
licence statement in any file (§14). Other repositories cited: nightscout/Trio `e41c9db37` (dev, 2026-09-22),
LoopKit/LoopWorkspace `f841285` (2026-09-19), LoopKit/g7sim `7c039de` (2026-10-12), LoopKit/pod `a491a5e`
(2026-10-12), jwoglom/faketandem `34c9401` (2026-10-17), jwoglom/pumpX2 `f13ccf96` (2026-09-28); this repository at
`d9167f59` (2026-10-16).*

> **Repository**: [jwoglom/trio-test-harness](https://github.com/jwoglom/trio-test-harness)
> **Language**: Python (35 files, 9,986 lines), shell wrappers, Markdown prompts and Claude Code skills
> **Purpose**: build, install, drive and screenshot the Trio iOS app (and Loop with `--app loop`) from any branch,
> PR or submodule PR, on the iOS Simulator or an iPhone, and turn the run into an HTML report or a PR comment
> **Source**: `externals/trio-test-harness/`

---

## 1. Summary

- The harness takes a Trio or Loop PR, branch or submodule PR (for example a TandemKit PR), checks it out, builds it
  with `xcodebuild`, installs it, launches it past onboarding, adds the app's **built-in** CGM and pump simulators, and
  records every step as a screenshot plus a JSON line.
- A coding agent (Claude Code) then exercises what the PR description says, using only the harness CLI, and a second,
  separate agent pass picks the screenshots that show the change and gives a verdict (`works`, `broken`,
  `inconclusive`).
- Three targets: the iOS Simulator (`simctl` + WebDriverAgent), a jailbroken iPhone over VNC and SSH (`rooted-vnc`),
  and any iPhone through macOS iPhone Mirroring (`iphone-usb`). An Xcode-signed install path covers non-jailbroken
  phones (install only).
- CI is one manually dispatched GitHub Actions workflow on self-hosted macOS runners. A local web UI runs the same
  stages on the operator's Mac.
- External device emulators (g7sim, pod, faketandem) are **not** attached at this commit. A faketandem stress lane
  existed in this repository for seven minutes on 2026-10-01 and was moved to a separate repository; the build options
  it uses remain (§8).
- **Nightscout is never configured.** Onboarding pre-seeding skips it, the onboarding walk taps "Skip Nightscout
  Setup", and Trio keeps the Nightscout URL in the iOS Keychain, which no harness command writes. A harness run as
  shipped therefore produces no Nightscout uploads and checks nothing on a server (§9).
- The harness has **no tests of its own** at this commit (§10).

## 2. Stages and entry points

`./trio-test-e2e` (`harness/pipeline.py`) runs the deterministic stages; every stage is also a `th` command and a
Claude Code skill.

| stage | what it does | `th` command | skill |
|---|---|---|---|
| checkout | Trio (`nightscout/Trio`, base `dev`) or LoopWorkspace (`LoopKit/LoopWorkspace`, base `feat/tandem-closed-beta`); a submodule PR is located through `.gitmodules` of candidate branches; cherry-picks onto the app or a submodule; file mtimes reset from git blob hashes so unchanged files do not trigger recompiles (`stabilize_mtimes`) | `build --checkout-only` | `trio-checkout` |
| build | `xcodebuild` with an `-xcconfig` override file written under `build/`, never into the checkout; simulator ad hoc, phone fake-signed IPA (`codesign -s -`) or team-signed (`--xcode`) | `build` | `trio-build` |
| install | `simctl install`; phone via `pymobiledevice3` with AppSync Unified, or `xcrun devicectl` | `install` | `trio-install` |
| launch | onboarding pre-seeded (simulator: `Documents/onboardingCompleted.plist`; phone: the same flags over SSH, plus Crashlytics and telemetry sharing off) or walked through the UI | `launch --preseed-onboarding`, `flow onboarding-walk` | `trio-launch` |
| smoke | home screen detected; Glucose Simulator (Loop: CGM Simulator) and Pump Simulator added from the home header | `flow add-cgm-sim`, `flow add-pump-sim`, `test smoke` | `trio-fake-devices` |
| report | `run.json`, `steps.jsonl`, screenshots, `report.html`; crash reports collected | `run finish`, `report html` | `trio-report` |
| PR notes | `runs/<run>/pr.md`: PR title and body, commit, submodule and cherry-pick details, and a three-line test-plan stub | (written by `trio-test-e2e`) | `trio-pr-plan` |
| agent | PR-specific testing (§11) | all driving commands | `trio-test-e2e`, `trio-test`, `trio-ui-drive` |
| comment | PR comment or PR-description section via `gh` | `report pr`, `report markdown` | `trio-report` |

`trio-test-e2e` holds a per-target device lock (`harness/busy.py`, shown by `th busy`) for its run. From a plain
terminal it then `exec`s `claude` with a fixed prompt; inside Claude Code (`CLAUDECODE` set) it stops after the report.

## 3. The `th` command surface

`th` (`bin/th` → `trio-test-harness` → `python -m harness.cli`) has **37 top-level commands and 56 subcommands**,
counted by walking the argparse tree of `harness/cli.py` at `c3c1bfe7` (reproduce: §16).

| group | commands |
|---|---|
| environment | `doctor`, `busy`, `daemon {start, stop, status, restart}`, `webui` |
| source and app | `build`, `install`, `launch` |
| simulator | `sim {list, runtimes, boot, shutdown, erase, install-runtime, container, defaults, openurl}`, `wda {build, start, stop, status}`, `lock`, `unlock`, `locked` |
| phone | `device {list, wake, lock, unlock, mirror-status, diag, vnc-restart, apps, ssh, kill, vnc-check, serve-ipa}` |
| UI driving | `shot`, `tap`, `swipe`, `drag`, `scroll`, `type`, `key`, `home`, `tap-text`, `find`, `tree`, `wait-text`, `ocr` |
| app flows | `flow {onboarding-walk, add-cgm-sim, add-pump-sim, back-home, dismiss, settle, at-home}`, `test smoke` |
| app internals | `logs [trio\|tandem\|watch\|all]`, `oslog`, `crashes`, `files {ls, cat}`, `perf`, `db {stores, tables, schema, query, exec}` |
| documentation | `docs {search, toc, page}` (triodocs.org; LoopDocs with `--app loop`) |
| run records | `run {new, current, list, use, note, finish, steps}`, `report {html, pr, markdown}` |

The README's CLI overview omits `docs`, `busy`, `webui`, the top-level `lock`/`unlock`/`locked`, `device
lock`/`unlock`/`mirror-status` and `flow settle`; each is described elsewhere in the README or only in `--help`.

Global options: `--target sim|rooted-vnc|iphone-usb`, `--app trio|loop`, `--git-protocol ssh|https`. All coordinates
are screenshot pixels on every target, so an agent can tap what it sees in a PNG.

`th db` (simulator only) opens the app's Core Data SQLite store; `query` is read-only, `exec` terminates the app,
backs the store up into the run's `db/` once, runs the SQL in one transaction, logs a run step and relaunches.
`th files` reads `Documents/` (Trio's OpenAPS JSON state, for example `settings/profile.json`); it has no write
subcommand. `th sim defaults KEY VALUE` writes one UserDefaults key (the Glucose Simulator's settings are UserDefaults
keys).

## 4. Targets and how the UI is driven

| piece | `simulator` | `rooted-vnc` (jailbroken iPhone) | `iphone-usb` (any iPhone) |
|---|---|---|---|
| build | ad hoc, same flags as Trio CI | unsigned, fake-signed IPA | team-signed (`th build --xcode`) |
| install / launch | `simctl install` / `simctl launch` | `pymobiledevice3` + AppSync Unified / `uiopen` over SSH | `xcrun devicectl` / Spotlight in the mirror window |
| screenshots | `simctl io screenshot` | TrollVNC framebuffer (`harness/rfb.py`) | iPhone Mirroring window capture |
| taps, typing | WebDriverAgent (appium, an XCUITest runner, HTTP on port 8100); idb as fallback when `idb_companion` runs | VNC pointer and keys | HID-level CGEvents into the mirror window (ShawnPana/phone-harness, MIT, cloned by `install.sh`) |
| finding elements | WebDriverAgent accessibility tree | tesseract OCR | Apple Vision OCR |
| onboarding | pre-seeded | pre-seeded over SSH | walked |
| status in `docs/HANDOFF.md` | verified end to end 2026-09-20 | verified end to end 2026-09-20 | driver written, window capture verified, pairing not completed |

`th daemon` keeps one driver connection (WebDriverAgent session or VNC link) alive behind a Unix socket; the
sandboxed CI agent reaches the simulator only through it. `install.sh` clones WebDriverAgent and phone-harness at their
default branch (`--depth 1`, no pinned commit); the CI workflow uses a prebuilt WebDriverAgent that the runners pin.

Loop support (`--app loop`, added 2026-10-11) is written from Loop's source; `docs/HANDOFF.md` states that nothing of
it has run on a Mac yet and lists what to verify.

## 5. Skills

Twelve skills under `.claude/skills/`, symlinked into `~/.claude/skills` by `install.sh`: `trio-test-e2e` (runs the
script, then the PR testing), `trio-test` (the chain, stage by stage), and one per stage: `trio-sim-setup`,
`trio-phone-setup`, `trio-checkout`, `trio-build`, `trio-install`, `trio-launch`, `trio-fake-devices`, `trio-pr-plan`,
`trio-ui-drive`, `trio-report`. The skills carry Trio navigation facts (onboarding order, tab names, device-picker
accessibility identifiers, the Glucose Simulator's UserDefaults keys) and the rules for reports (fake data only; no
device identifiers, Apple IDs or tokens). `CLAUDE.md` points an agent at `docs/HANDOFF.md`, the README,
`docs/phone-setup.md` and the skills, in that order.

## 6. CI and the web UI

**Where it runs.** `.github/workflows/e2e.yml` ("Trio e2e (simulator)") is `workflow_dispatch` only, on
`runs-on: [self-hosted, macOS, worker]`, with a 150-minute job limit. It needs a Mac with Xcode 26.2 (the only choice
offered), simulator runtimes, local git mirrors and a prebuilt WebDriverAgent. `./trio-test-ci` dispatches it from a
laptop with every input as a flag and follows it with `gh run watch`. There is no scheduled or PR-triggered run.

**Inputs.** App (`trio`/`loop`), the app's PR or branch, submodule PRs or branches, cherry-picks, build configuration,
skip onboarding, smoke (fake CGM and pump), Claude model (default `sonnet`), extra agent instructions, agent time limit
(default 30 minutes), post comment (default off), simulator device and runtime.

**Steps.**

1. `ci/inputs.py` maps the inputs onto `trio-test-e2e` flags and picks the run's PR.
2. `trio-test-e2e --mode simulator --yes --no-agent --comment never` (checkout to report).
3. **Agent**: `claude -p` with `ci/agent-prompt.md` (Loop: `ci/agent-prompt-loop.md`) and `ci/agent-limits.md`.
   Bash is limited to `./trio-test-harness`, `./bin/th` and `sleep`; file tools are limited to the harness checkout;
   permission mode `dontAsk`. `ci/claude-sandbox.py` writes the macOS sandbox settings: no network except
   `triodocs.org` and `loopkit.github.io`, writes only under `runs/`, `build/` and the installed app's own simulator
   containers, and one Unix socket (the harness daemon, started outside the sandbox). This step has
   `continue-on-error: true` and no GitHub token.
4. **Highlights**: a second `claude -p` with only Read, Glob and Grep reads `pr.md`, `steps.jsonl`, the tester's
   `agent-summary.md` ("claims to check, not facts") and the screenshots, and returns a JSON verdict with at most ten
   screenshots; `ci/highlights.py` validates it into `highlights.json`.
5. **PR comment**, only when `post_comment` is set: posted by a GitHub App; screenshots are attached inline only for
   PRs in the harness owner's repositories, otherwise the comment carries captions and a link to the Actions run.
6. Job summary (`ci/summary.py`), the run directory as an artifact and `report.html` as an unzipped artifact, both
   kept 14 days; the `xcodebuild` log on build failure.

**Web UI** (`th webui`, `harness/webui.py`): a token-protected page bound to 127.0.0.1 by default that runs the same
stages on the operator's Mac (default target `rooted-vnc`), shows the live log and the agent's findings, and posts the
PR comment only when the operator presses **Post PR comment** or ticked auto-post beforehand. **Continue**
(`harness/handoff.py`) can resume the agent's session outside the sandbox, make a git worktree of the tested commits,
or start a cloud session from the PR's head branch.

## 7. What a run records

A run is `runs/<timestamp>-<name>/`:

| file | contents | machine-readable |
|---|---|---|
| `run.json` | name, created/finished times, `status` (`running`, `passed`, `failed`, `partial`), `summary`, target, mode, app, PR URL, and `build`: target, configuration, bundle id, Xcode version, scheme, local paths, and `git` (short sha, subject, submodule shas, PR, branch, cherry-picks) | yes, JSON, no schema or version field |
| `steps.jsonl` | one object per step: `t`, `action`, `note`, optional `screenshot` (run-relative), extra fields | yes, JSON Lines |
| `screenshots/NNN-*.png` | one per step that took one | |
| `pr.md` | PR title, description, commit, test-plan stub | Markdown |
| `agent-summary.md` | the CI agent's final message | Markdown |
| `highlights.json` | `verdict` (`works`/`broken`/`inconclusive`), `summary`, up to ten `{screenshot, caption}` | yes, JSON |
| `report.html` | self-contained page, screenshots embedded as JPEG thumbnails | |
| `logs/`, `crashes/`, `files/`, `db/`, `perf.csv` | saved on request; crash reports with Mac and phone identifiers removed | partly |

So a run does have a machine-readable result: `run.json`'s `status` and `highlights.json`'s `verdict`. Two points a
consumer of that result needs:

- `trio-test-e2e` sets `status: passed` when the smoke stage succeeds. The agent is told to call `th run finish` with
  its own verdict, which overwrites it; if the agent step fails or times out (it is `continue-on-error`), `status`
  stays at the smoke stage's `passed`. The two fields answer different questions (did the app reach home with fake
  devices; does the review pass think the change works).
- There are no per-check pass/fail/skip counts, no requirement or check identifiers, no artefact digest, and no
  record of which parts of the PR could not be exercised other than in free text.

## 8. Fake devices

**At `c3c1bfe7` the harness uses only the apps' built-in simulators.** Trio: Glucose Simulator (device-picker id
`devicePickerItem-simulator`) and Pump Simulator (`devicePickerItem-MockPumpManager`), added through the home
header's "Add CGM" / "Add pump" or Settings ▸ Devices (`harness/flows/trio.py`). Loop: CGM Simulator and Pump
Simulator; a new CGM Simulator has no glucose model, so on the simulator the harness writes a sine-curve model
(110 ± 20 mg/dL) into `Documents/CGMManagerState.plist` and relaunches (`harness/flows/loop.py`).

A search of the tree (`grep -rniE 'g7sim|impossible|faketandem|omnipod|\bpod\b'` outside `.git`, exit 1) finds no reference to
g7sim, pod, faketandem or ImpossiBLE. `SimulatorDriver.launch` runs `simctl launch` with no environment, so nothing
injects ImpossiBLE's library (which pod's and g7sim's iOS Simulator transports need). TandemKit appears only as a
submodule under test and as a log source (`th logs tandem`); its driver talks to no pump in a harness run.

**History.** Commit `dd69a8d` (2026-10-01) added `th stress`: Trio `feat/tandem-closed-beta` built with
`TANDEMKIT_VIRTUAL_PUMP` and ThreadSanitizer, run on the simulator against faketandem with seeded chaos and recovery
checks, plus a nightly workflow and a unittest suite. Commit `83729b5` seven minutes later moved all of it to a
separate repository named in the commit message as jwoglom/tandemkit-stress (not cloned here; not verified). What stays
in this repository is the library support it calls in `harness/build.py`: extra Swift compilation conditions,
sanitizer settings for the iOS Simulator SDK only, a build deadline (`BuildTimeout`) and `save=False`. None of these is
exposed as a `th build` flag.

**What the device layer's simulators offer, for comparison** (read from their READMEs, not run): pod has
`-transport impossible` to serve an app in the iOS Simulator through ImpossiBLE; g7sim describes the same for the G7;
faketandem has a `virtual` TCP transport carrying GATT semantics and an HTTP harness API (`GET /api/log`, fault
controls). Attaching any of them to a harness run would need a launch environment (or the build condition above) and
a flow that pairs the device instead of choosing the in-app simulator; neither exists at this commit.

## 9. Nightscout

**The harness never configures Nightscout.**

- Pre-seeding writes only `onboardingCompleted` and `hasSeenFatProteinOrderChange` (simulator), plus
  `crashlyticsSharingEnabled=false` and `telemetrySharingEnabled=false` on the phone (`harness/flows/trio.py`).
- The onboarding walk taps "Skip Nightscout Setup" (`NEXT_LABELS`, `walk_onboarding`).
- Trio stores the Nightscout URL and secret in the Keychain (`NightscoutConfig.Config.urlKey = "NightscoutConfig.url"`,
  `Trio/Sources/Modules/NightscoutConfig/NightscoutConfigDataFlow.swift`; read in
  `Trio/Sources/Services/Network/Nightscout/NightscoutManager.swift`, Trio `e41c9db37`). `th db` reaches the Core Data
  store, `th files` only reads `Documents/`, and `th sim defaults` writes UserDefaults; none reaches the Keychain. The
  upload switch `isUploadEnabled` lives in Trio's settings JSON under `Documents/`, which `th files` can read but not
  write.
- The CI agent's sandbox allows network access only to the two documentation sites, and the `trio-pr-plan` skill tells
  the agent to list Nightscout among what fake devices cannot test.

**What a run uploads**: nothing, as shipped. Trio's `NightscoutManager` returns early from every upload when no
Nightscout API is configured (`guard let nightscout = nightscoutAPI, isUploadEnabled`).

**What it could upload** (inference from Trio's source, not run): an operator in an interactive mode could enter a
Nightscout URL and secret through Trio's own screens (onboarding or Settings ▸ Nightscout) with the ordinary `tap` and
`type` commands. Trio would then upload, from the fake devices and whatever the run did, glucose entries (when
`uploadGlucose` is on), treatments (pump history, carbs, overrides, temp targets, notes), device status and the profile
(`NightscoutManager.swift` lines 534–1081 at `e41c9db37`). The simulator app runs outside the agent's macOS sandbox,
so the sandbox's network rule would not stop the app's own uploads (inference from how the sandbox is applied, §6).

**Server-side checks**: none. No harness code reads anything back from a Nightscout server.

**Link to this project's server-side labs.** The harness covers the app side (does the change render and behave on
the device screens); this repository's labs cover the server side with synthetic clients:

| this repository | role | meets the harness at |
|---|---|---|
| `tools/mock_nightscout.py` | in-memory v1/v3 server for entries, treatments, devicestatus, profile | a URL a harnessed Trio could upload to, if one were configured |
| `tools/lab/rc-soak/` | A/B soak of two cgm-remote-monitor builds with a synthetic household (`traffic.js` includes a Loop/Trio uploader) | the uploads a harnessed Trio would make are the real-client counterpart of `traffic.js`'s Trio traffic |
| `tools/swift-nightscout-tests/` | Swift tests of Loop's upload behaviour against a local server | same contract, client side, without the app |
| `conformance/` | assertions, vectors and scenarios against a server URL | could assert on what a harnessed app uploaded |

None of these connections exists in either repository today.

## 10. Tests of the harness itself

**None at `c3c1bfe7`.** No `tests/` directory, no `test_*.py`, no `pytest`, `unittest` or `doctest` use
(`grep -rln 'def test_\|import pytest\|unittest\|doctest'` outside `.git`: no match, exit 1). The workflow runs the
harness against an app; it does not test the harness. The only test suite in the history (`tests/test_stress.py` and
four fixtures, added in `dd69a8d`) left with the stress lane in `83729b5`. `docs/HANDOFF.md` records manual and
offline checks instead ("checked offline only: argument parsing, … `ci/inputs.py`").

**What can run on Linux.** The command parser and the pure-Python parts import without macOS. Two probes, run with
`python3 -I -B` against a `git archive` copy of `c3c1bfe7` in a scratch directory (no network, no Apple tools):

1. The argparse tree (§3): 93 entries, 37 top-level.
2. `harness/appdb.py` against a throwaway SQLite file: `query("SELECT …")` returns rows; `query("UPDATE …")` is refused
   with `HarnessError: sqlite: attempt to write a readonly database` and the row is unchanged; `execute("UPDATE …")`
   changes one row.

**Ablation of probe 2.** `query()` has two guards: the URI `mode=ro` and `PRAGMA query_only = ON`.

| copy | `query("UPDATE …")` |
|---|---|
| unchanged | refused, value stays 5 |
| `mode=ro` replaced by `mode=rw` | refused (query_only still holds) |
| `mode=rw` and the `query_only` line removed | **accepted**, value becomes 9 |

The probe can fail, and fails only when both guards are gone. These are probes written for this document, not tests
the repository ships.

## 11. Agent-driven testing and human review

The repository is built for a coding agent: `CLAUDE.md` and `docs/HANDOFF.md` are written for "the next agent", 49 of
the 71 non-merge commits carry a Claude co-author trailer and 7 have Claude as author (§16), and every stage is a
skill.

The flow, as the code and prompts define it:

1. `trio-test-e2e` writes `pr.md` with the PR description and a three-line test-plan stub (smoke; exercise every
   user-visible change with before/after screenshots; note anything wrong).
2. The agent turns the description into checks (`trio-pr-plan`: classify each change as UI, driver, algorithm or
   non-UI; look every setting up in the docs with `th docs`; include a negative check for a bug fix; state what fake
   devices cannot test), drives the app (`trio-ui-drive`), may read logs, OS log, crash reports, `Documents/`, the
   database, and may change database rows to reach states the simulators cannot produce ("Change existing rows; do
   not insert or delete").
3. The agent closes the run with `th run finish passed|failed|partial --summary …` and renders `report.html`.
4. In CI, a second agent with no memory of the session reviews the run from files only and writes `highlights.json`.
5. A PR comment is posted (§6).

**Human steps.**

- Interactive (skill or terminal hand-off): the `trio-test-e2e` skill asks the user before posting the PR comment
  (step 5, `AskUserQuestion`); `trio-test-e2e --comment ask` is the default.
- Web UI: nothing goes to GitHub until the operator presses **Post PR comment**, unless auto-post was ticked.
- CI: the person who dispatches the workflow chooses `post_comment` beforehand (default off); with it on, the comment
  is posted without a further human step. The review pass is a second agent, not a person.
- The comment ends "Posted by trio-test-harness (simulator CGM/pump, no real patient data)"; with highlights it says
  the screenshots were "chosen by a separate review pass". It does not otherwise state that an agent ran the test.

## 12. Fit with the census and the quality-system proposal

**Census.** The 2026-09-30 census did not list this repository. The 2026-10-17 run of
`tools/programme/stack-census/census.py` (`results/census-2026-10-17-simulators.md`, generated in this worktree, not
yet committed) lists it in the controller layer: 71 commits in 12 months, 1 human author, 7 agent commits, 1 workflow,
`ci_runs_tests` true, 37 code files, 0 test files, 0 test declarations. Two of those figures mean something specific
here:

- `agent_commits_12m` counts commits whose **author** is an agent (7). Counting the Co-Authored-By trailer as well
  gives 49 of 71.
- `ci_runs_tests` is true because the workflow runs an end-to-end test **of the app** (Trio or Loop). It runs no test
  of the harness.

**"Automated hardware-in-the-loop rigs."** This harness is not one. It is an automated **simulator-in-the-loop** and
**on-device UI** rig: the real app binary, built from the PR, runs on the iOS Simulator or a real iPhone, driven
through its UI, with the apps' own software CGM and pump in place of devices. No radio, sensor or pump is in the loop,
and the device drivers' transport code is not exercised.

**"Per-release test reports."** It produces a per-**PR** (or per-branch) report, on demand, not per release; the
artifacts expire after 14 days and PR comments persist on the PR.

**The record shape (QUALITY-SYSTEM §4.1).** Against the six parts:

| part | harness run |
|---|---|
| identity | component (app), short commit sha, submodule shas, Xcode, configuration; no artefact digest |
| inputs | PR description and agent instructions; simulator device and runtime; no requirement IDs, scenario or fixture version |
| procedure | step log with times; automated by an agent, with the model named in the workflow input; who dispatched is in the Actions run, not in the record |
| outputs | a status and a review verdict; screenshots, logs and crash reports; no pass/fail/skip counts; no red control |
| known gaps | free text in the agent summary and notes ("what you could not" is asked for) |
| status | `passed`/`failed`/`partial` and `works`/`broken`/`inconclusive`; neither uses verified/validated |

## 13. Proposed wording

For the census record (`docs/60-research/programme/stack-census-2026-09-30.md` or its successor), controller layer,
after the paragraph on CI:

> **App-level automation.** jwoglom/trio-test-harness (from 2026-09-19) builds Trio or Loop from any PR or submodule
> PR, runs it on the iOS Simulator or an iPhone, drives it through its UI with the apps' built-in CGM and pump
> simulators, and has a coding agent exercise what the PR describes, with a second agent pass reviewing the
> screenshots. It runs on demand on self-hosted macOS runners and reports per PR. It has no tests of its own, attaches
> no external device simulator, and does not configure Nightscout.

Replacing the "Not found anywhere in the device layer" sentence:

> **Not found anywhere in the device layer:** fuzzing harnesses, automated hardware-in-the-loop rigs, and per-release
> test reports. The nearest is jwoglom/trio-test-harness in the controller layer: an automated simulator-in-the-loop
> and on-device UI rig that reports per PR, with software devices in place of hardware.

For `docs/00-overview/QUALITY-SYSTEM.md` §4, controller row, "exists today" cell, append:

> ; app builds from any PR driven on the iOS Simulator or an iPhone by an agent, with per-PR reports
> (jwoglom/trio-test-harness)

and, "the kit" cell, append:

> ; app runs with external device simulators (faketandem, pod, g7sim) in place of the built-in ones, uploading to a
> lab server that checks what arrived

For §4.1, after the table:

> jwoglom/trio-test-harness's `run.json` and `highlights.json` already carry identity (commit, submodules, Xcode),
> procedure (a timed step log) and a verdict; the parts it lacks are an artefact digest, requirement or check IDs,
> per-check counts and a red control.

## 14. Licence

No LICENSE, COPYING or licence statement exists in the tree or the history at `c3c1bfe7` (`ls LICENSE* COPYING*`: no
such file; `grep -ril licen` matches only the Xcode licence-acceptance step in `bootstrap-xcode.sh` and the README's
mention of it). Without a licence, default copyright applies: the code can be read and linked, but not copied,
adapted or redistributed, in this repository or elsewhere, without the copyright holder's permission. This document
therefore describes and cites the code and reproduces no part of it beyond identifiers and short quoted strings.
phone-harness, which the harness clones at install time, is MIT-licensed per the harness README.

## 15. Open questions

- **Licence**: whether the owner intends to add one, which decides whether any part (for example the run-record shape,
  the sandbox settings or the flows) can be reused here.
- **Visibility**: the repository is public (GitHub API `visibility: public`, anonymous request HTTP 200, 2026-10-17);
  a comment in `e2e.yml` still calls it private.
- **Status semantics**: whether `run.json`'s `passed` from the smoke stage is meant to stand when the agent step does
  not finish (§7).
- **Nightscout path**: whether a run that configures a lab Nightscout (for example `tools/mock_nightscout.py`) and
  checks what arrived is in scope for the harness, or belongs in this repository's labs.
- **External simulators**: whether the stress lane's faketandem attachment, or pod's and g7sim's ImpossiBLE transport,
  is intended to come back to the PR flow.
- **Census**: whether the census should count Co-Authored-By trailers as agent commits, and whether `ci_runs_tests`
  should separate "tests the repository" from "tests another repository".

## 16. Reproduce

```
cd externals/trio-test-harness
git log -1 --format='%H %cs'                     # c3c1bfe7… 2026-10-17
git rev-list --count HEAD                         # 73
git rev-list --count --no-merges HEAD             # 71
ls LICENSE* COPYING*                              # no such file
git log --no-merges --format='%an%x09%(trailers:key=Co-Authored-By,valueonly,separator=;)' \
  | awk -F'\t' 'tolower($1)=="claude"{a++} tolower($2)~/claude/{t++} END{print a, t, NR}'   # 7 49 71
grep -rniE 'g7sim|impossible|faketandem|omnipod|\bpod\b' --exclude-dir=.git .                   # no match (exit 1)
git show --stat dd69a8d 83729b5                   # stress lane added and moved
```

Command tree (scratch copy; imports `harness.cli` only, touches no device or network):

```
git archive c3c1bfe7 | tar -x -C "$SCRATCH/src"
python3 -I -B dump_cmds.py "$SCRATCH/src"         # walks build_parser()'s subparsers: 93 lines, 37 without a space
```
