# Frozen 195c9322: native identity and client acceptance

**Reproduced:** the unchanged nine-stage native matrix completes with all nine
stages PASS on frozen core `195c932293f3abc648da8fbe4356bf7360acd002`. All three
original semantic mutation controls fail on their intended assertions, and all
three restored runs PASS. This closes this current-source native identity/client
criterion. It is not the full tier/browser/enabled-corpus campaign, paired
binding, clinical replay, pilot or capacity acceptance. The historical
[D505 result](../oidc-d50502bb/README.md) remains unchanged.

## Exact source, dependencies and runtime

A new owned detached source worktree at the exact frozen commit stays clean
before and after execution. A **fresh** `npm ci --ignore-scripts --offline`
installs the committed lock into that tree; no dependency tree or serving source
was borrowed. A fresh production browser bundle compiles successfully, retaining
the three webpack performance warnings. The [preparation record](runs/preparation.json)
and [instrument manifest](instrument.json) pin the source, lock, all 20 committed
harness files and all 16 newly generated bundle files. Harness bytes are identical
to those used by the historical D505 matrix.

The lock SHA-256 is
`6418fe21c18346435f643b8496d6b7ec23c9c6de28f1925c3bb2028eb575e93e`.
Actual execution uses Node **22.23.4**, npm **10.9.9**, Chrome
**154.0.8037.57**, UTC and oref0 companion
`d219baf9559d62a8bb0bd42014192a2d7c0839ef`. Ambient `NS_*`, `NODE_OPTIONS` and
`NODE_PATH` are removed before bundle/matrix/control execution. The production
bundle uses the shipping webpack command. No native harness, assertion, gate,
source fixture, role or source expectation was altered.

[Baseline summary](runs/matrix/summary.json), [control summary](runs/controls/controls.json)
and [result](result.json) preserve actual source/process/service attribution.
Disposable digest-pinned services are PostgreSQL **16.15**, MongoDB **7.0.43**
and HTTPS Vault **2.2.1**; actual container/image IDs, repo digests and mapped
loopback ephemeral ports remain in the summaries. Browser flows use actual
Chromium, signed HTTPS and the pinned client with a synthetic provider. This
neither observes a real IdP/device/live provider nor claims general client
interoperability. It is a local Node22 result, not a reattributed Node24 run.

## Commands and measured verdicts

Commands are the existing committed procedure, in the new clean source tree:

```bash
npm ci --ignore-scripts --offline
npm run bundle
tests/native/oidc-matrix/run.sh --out /private/new-matrix-output
tests/native/oidc-matrix/run.sh --out /private/new-control-output \
  --control single:single-shipping-eight-hour-exchange,browser:csrf,consumer:consumer-current-data-authority-bypass
```

Actual [matrix argv](runs/matrix-command.json) and [control argv](runs/controls-command.json)
are retained with only execution-local path prefixes normalized. Wrapper exit
records are zero; those do not replace individual stage/control assertions.

| Baseline stage | Verdict |
|---|---|
| vault-single | PASS |
| vault-multi | PASS |
| mongo-sessions | PASS |
| pg-sessions | PASS |
| mongo-http | PASS |
| owner-consumer | PASS |
| owner-authority | PASS |
| owner-browser | PASS |
| owner-compatibility | PASS |

| Existing semantic control | Actual red symptom | Restored |
|---|---|---|
| Single eight-hour exchange | Independent lifetime oracle observes `3600 !== 28800`. | PASS |
| Owner browser CSRF | Transport status oracle observes `200 !== 403`. | PASS |
| Current DATA authority | `next DATA operation must read current role authority`. | PASS |

Each red attempt exits 1 at the intended semantic assertion, without forced
termination; restored attempts exit 0. The control summary pins original and
mutant source SHA-256s and per-attempt families/cleanup. These reds are not setup
failures. There were no failed setup attempts in this fresh leaf. Every baseline,
red and restored attempt reports empty schema/backend/Mongo/Vault leftovers.

## Independent cleanup and publication

The original harness creates two uniquely owned projects, one per command, and
its unchanged cleanup removes their disposable containers, volumes, networks and
private TLS/password/token state. An additional read-only Docker label query
independently verifies **zero containers, volumes and networks for both projects**:
[resource check](runs/independent-resources.json). No retained Agent, RT, old
benchmark or peer resource was stopped or removed. The new source/dependencies,
bundle and raw captures remain local for review.

[Artifact manifest](artifacts.json) pins all 53 raw/published capture hashes and
sizes. Publication replaces only execution-local source/workspace/private-capture
path prefixes and trailing log whitespace; assertions, status codes, values, source identities and counts
remain verbatim. Original harness redaction is preserved; no unredacted fallback
was produced. No full/core campaign, new clinical execution, capacity/pilot/cloud
action, source/queue/release change or push occurs in this leaf. The coordinator
owns final joined acceptance and programme integration.

Record checks: all 53 published artifact hashes/sizes verify; staged whitespace
passes and `make docs-links` passes (27 checked, zero failing). `make queue-check`
stops at queue validation because this isolated evidence worktree lacks the
queue-declared external gate working directories. This is local setup
UNMEASURED, not a native product failure; no queue settings were changed.
