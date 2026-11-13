# Composition fixture wire-version repair

Reproduced on frozen core `d5e2e874659155c952b5b5deb862f12f982ac02e`; test-only repair `7ce803582f5f6c4d7506ec5321121e67e00dff09` changes only `tests/internal-api-composition.test.js`. No product transport, schema, interface or rejection policy changes.

## Failure classification

The first comprehensive UNIT run failed three composition cases: UDS and HTTP positive route-owner probes expected 200 but received 503; the owner-fence ablation reported `Missing expected rejection`. The same **16 passing / 3 failing** reproduce in [isolated D5](isolated-D5-red.txt), without shared-database or earlier-test state. This is a stale fixture, not evidence of a live routing breach.

`lifecycle-participant.json` selects wire version 2; the transport independently checks route ownership and that wire version. The raw fixture defaulted to header version 1. Named clients already selected version 2 and passed. The old raw positive control therefore correctly refused, and removing the service-owner fence alone still left the version fence refusing: the ablation could not expose the intended owner defect.

Raw cohort-route probes now explicitly use the owning lifecycle contract's current wire version, independently of the deliberately foreign service ID. Foreign/unregistered service and method checks remain required before dispatch. An explicit version-1 probe must still refuse. The fixture retains a legacy version-1 status **payload**, which the current response schema deliberately supports; wire version and payload version are separate.

## Focused results and controls

| Check | Result |
|---|---|
| [Repaired composition suite](fixture-repaired.txt) | 19 passing |
| [Restored exact affected suites](restored-affected.txt) | 66 passing: composition, transport, shutdown, contracts, listener configuration and stale socket |
| [Exact committed source](exact-committed.txt) | 19 passing; clean product worktree |
| [Owner-fence-only source ablation](owner-ablation-red.txt) | RED, 2 failures: foreign co-resident service returned 200 instead of 503 |
| [Wire-version-only source ablation](version-ablation-red.txt) | RED, 2 failures: old lifecycle wire version returned 200 instead of 503 |
| [Restoration assertions](controls.json) | Original transport restored byte-for-byte; SHA-256 unchanged |
| [Changed-test lint](lint.txt) | Zero errors; two existing fixture filesystem warnings |

The ablations modify only the lane's own transport file and restore original bytes in `finally`. [Portable control instrument](controls.py) takes an owned worktree path; never pass another session's worktree. [Attribution](artifacts.json) pins both executed bytes and the published copy, whose only change is replacing the execution-local root with a positional argument. Captures strip ANSI, normalize workspace prefixes and trim line-end whitespace; original local logs remain preserved.

## Environment and commands

Node v22.23.4. Dependencies are the lane-owned clinical acceptance installation from the byte-identical frozen package lock, SHA-256 recorded in `artifacts.json`; no peer dependencies were modified. The component tests use actual private UDS/loopback HTTP and the recording operation-window protocol fixture. They need no MongoDB or PostgreSQL connection, and establish no native database/process/clinical acceptance.

Each Mocha invocation used a cleared environment with PATH and a temporary HOME, plus `NODE_ENV=test`, `CI=true`, `TZ=UTC`, then the checked-in CI environment loader. No ambient `NS_*`, `NODE_OPTIONS` or `NODE_PATH` was inherited:

```bash
env -i PATH="$PATH" HOME=/tmp NODE_ENV=test CI=true TZ=UTC \
  node bin/with-env.js ./tests/ci.test.env node_modules/mocha/bin/mocha.js \
  --fail-zero --timeout 10000 --require ./tests/hooks.js --exit \
  tests/internal-api-composition.test.js tests/internal-api-transport.test.js \
  tests/internal-api-shutdown.test.js tests/internal-api-contracts.test.js \
  tests/internal-api-listener-config.test.js tests/internal-api-stale-socket.test.js \
  --reporter dot
```

An [initial adjacent-suite selection](initial-affected-selection.txt) guessed two nonexistent filenames. Mocha warned and ran 49 existing tests; that output is retained and is not claimed as coverage of the absent files. The exact inventory was inspected before the corrected six-file command above. No expectation was weakened to make either original failure or an ablation pass.

## Integration boundary

The coordinator owns joining this repair with the other failed-UNIT repairs and refreezing before one comprehensive repeat. The D5 campaign is failed, not ready; later tiers and enabled corpus were not run by that campaign. This lane ran no full/browser/capacity campaign, cloud action, push or PR. Product whitespace check passed. Local report links and instrument syntax are checked; programme queue gates remain with the coordinator's populated workspace.
