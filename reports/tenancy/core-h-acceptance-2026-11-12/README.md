# Core H full functional execution — 2026-11-12

**Captured full functional execution: PASS.** All eight ordinary tiers and the unfiltered enabled-corpus command returned 0. The worker reports passed/errors[]. Its captured sourceAcceptance remains **COORDINATOR_REVIEW_REQUIRED**: coordinator final prcheck and an acceptance receipt are separate. This is not release, production, baseline, pilot or capacity acceptance.

This immutable leaf records the completed H campaign. It adds no experiment rerun or source change. Public artifacts are **new bounded derivatives**, hash-bound to the unchanged private assessment and original captures. Separate native diagnostics and later changed instruments are not imported into H.

## Source and instrument

| Captured identity | Exact commit |
|---|---|
| Core | `9db0ce94f072c8f34aab889f0181afa4269a6758` |
| Deployment | `d76ef17878edb610cdeae75aeef9c07f94b60753` |
| Alignment | `5d7fa02746f4695a222f1fc400dc59b61a8c717e` |
| Harness | `7209cb29020543a82412cd69d2751ca939cf4318` |

[Provenance](provenance.json) retains raw worker/result, corpus, source/spec, command/log, archive and cleanup-record hashes. Recorded remote toolchain: Node `v24.22.1`, npm `11.19.1`, kernel `6.8.0-147-generic`, with the captured Node binary/lock/CI environment hashes. The recorded worker hash matches the exact committed harness source; decoded evidence does not retain worker Python bytes, so that comparison is not mislabeled a raw worker-file capture.

Three directly remeasured anchors are:

- Worker result SHA256: `203c422119c36b981c0773bba382f90557a8ad540aeaa5313447be50569f6602`.
- Corpus record SHA256: `cf622a73aac7aa8121ae7e20fed0e0c641411d310f0e08d62cabbb26aa935959`.
- Remote evidence archive SHA256: `3791914f840ac814ee3d44fb645b6d92f7a41b50f342eda949fac5f2132c2688`.

## Captured results

[Execution evidence](execution.json) preserves terminal Mocha counts, original stdout summary line numbers and each captured return code.

| Stage | Passing | Pending | Failing | Command |
|---|---:|---:|---:|---|
| UNIT | 3563 | 1 | 0 | PASS / rc0 |
| DOM | 205 | 0 | 0 | PASS / rc0 |
| dependency | 368 | 2 | 0 | PASS / rc0 |
| core | 319 | 0 | 0 | PASS / rc0 |
| harness | 99 | 0 | 0 | PASS / rc0 |
| integration | 3643 | 836 | 0 | PASS / rc0 |
| stress | 18 | 0 | 0 | PASS / rc0 |
| browser | 686 | 0 | 0 | PASS / rc0 |
| enabled corpus | 839 | 1 | 0 | PASS / rc0 |

The eight ordinary tiers and enabled corpus are separate executions. Ordinary-tier pending cases are not counted as passing bodies, nor are their counts evidence that the enabled corpus ran. The worker's completedTests lists all nine stages.

Harness stderr includes one expected nested red-control diagnostic, `TEST_EXECUTION: no intended test files (support tests do not count)`. Exact H source `tests/test-select.test.js:253–262` instantiates a reporter with support files only and asserts that its completion reports failure. That self-test passed and the outer harness returned 0. The diagnostic remains in the derivative with source attribution; it was not suppressed. Other stages, including the enabled corpus, have no execution diagnostics.

## Corpus scope and pending case

[Corpus evidence](corpus.json) records 86 selected unique file paths, exactly matching the frozen source's full unfiltered inventory, and its actual terminal 839 passing/1 pending/0 failing result. Selection of 86 files is not by itself an independently measured executed-file count. The runner uses strict execution accounting and emits no missing-file diagnostic, but its internal executed-file set is not serialized and no separate per-file event ledger is retained. This leaf preserves that distinction rather than inventing a file-completion count.

The sole enabled-corpus pending case is **reports end-to-end successful request latency and throughput**, the optional `NS_TENANT_COMMIT_CLOCK_BENCHMARK=1` workload in `tests/tenant-commit-clock-http.integration.test.js`. Its explicit pending-opt-in heading is captured. It supplies no performance/capacity figure. Ordinary UNIT's external date-string corpus and dependency's optional AJV checks remain separately pending as reported; the 836 ordinary integration pending cases do not replace the enabled-corpus execution.

## Cleanup and cost

[Cleanup/cost evidence](cleanup-and-cost.json) records worker-owned Mongo cleanup verified with empty fixture-container and volume residual arrays. The corpus separately verified removal of its shared Vault/PostgreSQL fixtures and their anonymous volumes; remaining:[].

Controller destruction was verified at `2026-11-12T20:50:13.022Z`; watchdog at `2026-11-12T20:50:20.518Z`. Independent provider inventory at `2026-11-12T20:50:45.357104+00:00` reported **0 droplets, 0 firewalls and 0 run tags**. Ephemeral private/public SSH key files were absent when assessed. Provider/resource identities, addresses, environment values, keys and database URIs are not published.

The archive decoded to **240 files / 13004475 bytes**. The compute estimate is **$0.2339845833182335 over 1684.6889998912811 seconds** of controller-start-through-watchdog accounting, including preprovisioning. It is not an invoice or a billing cap. The selected functional-execution profile's maximum was 180 minutes with a $1.50 runtime estimate ceiling. No tenant-capacity or production-cost conclusion follows.

## Publication verification and handoff

[Derivation controls](derivation-controls.json) retain four bounded in-memory metadata counterexamples: wrong pin, missing successful stage, failed corpus and unverified owned cleanup all refuse; the original captured tuple passes. These are assessment controls, not product tests or another campaign.

[The manifest](manifest.json) binds this leaf. Publication checks cover JSON, hashes, local links, privacy and whitespace; their outcome is distinct from the successful remote execution. No source archive, dependency tree, full private spec/environment/inspect data, credentials, personal path or host/provider identifier is copied. The programme owner owns final prcheck/receipt, release/decision/queue rollup and any future campaign authorization.

[Publication checks](publication-verification.json): JSON/hash/local-link/privacy/whitespace and original-capture hash checks passed. One static `make queue-check` attempt failed at queue validation on 16 existing absent peer-worktree cwd references in this isolated checkout; later steps were skipped. [Exact output](queue-check-output.txt) is retained. No queue or peer worktree was changed.
