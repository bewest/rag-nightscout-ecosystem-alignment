# Core D acceptance failure — 2026-11-12

**Captured outcome: FAILED.** The first UNIT tier reported **3562 passing, 1 pending and 1 failing**. Execution stopped there. The later seven tiers and the entire unfiltered enabled corpus were **NOT_RUN**. Cleanup completed; this failure does not constitute source acceptance or a capacity result.

This immutable leaf preserves a bounded, sanitized account of an already completed remote run. It performs no experiment rerun or repair. Public JSON/log excerpts are **new derivatives**, hash-bound to unchanged private originals; they are not presented as raw private captures.

## Selected source and instrument

| Captured identity | Exact commit |
|---|---|
| Core | `2d0ae0354a38b4a88f43bc2ae5ec60c085058f64` |
| Deployment | `dcc4a70bafd4edf31c5cab4bf3099883bd7e37f9` |
| Alignment | `c33acdc48208586354002573b93ce4f33d6c0c6a` |
| Execution harness | `f660a1171d605d6ad7517328a6ae0e8423a2e825` |

[Provenance](provenance.json) retains raw private spec, run record, source provenance, authorization/plan, both UNIT streams, controller/watchdog records, cleanup inventory and archive SHA256 values. It also binds the exact frozen fixture/descriptor sources. The remote worker bytes are not retained in the decoded archive: the captured worker hash independently matches the committed harness Python source. That source verification is distinguished from a nonexistent raw worker-file capture. The separately retained immutable local prepared bundle manifest matches the selected spec digest, and its worker bytes match the remote-recorded and committed hashes; this is explicitly local preparation evidence.

Captured remote toolchain: Node `v24.22.1`, npm `11.19.1`, kernel `6.8.0-147-generic`. The captured Node binary/worker hashes, source lock and CI environment hashes remain in provenance. No live remote remeasurement occurred after teardown.

## Captured failure and pending test

[The selected log derivative](failure-and-pending.json) retains the final Mocha counts, sole assertion failure and optional pending line, with original log line numbers and hash. ANSI color escapes were removed and the source-checkout prefix replaced by a logical role.

The failing case is `Internal service API contracts — fixes service ownership, names, wire paths and immutable versioned descriptors`, at `tests/internal-api-contracts.test.js:27:14`. Its captured assertion is **actual 2 versus expected 1**.

**Read-derived mechanism from the exact frozen source:** the fixture's version-2 whitelist contains `connector-inspection`, `alarm-delivery` and `lifecycle-participant`, but omits `evaluator-inspection`. The frozen evaluator-inspection JSON descriptor is version 2, so that descriptor receives the fixture's fallback expectation of version 1. This source inspection explains the captured symptom; it is not another execution or proof of a repaired candidate.

The single pending test is `moment-memo: document dates parsed once — is moment's own parse on every date string of VIEWS_CORPUS_DIR (read in place)`. The exact source uses `it.skip` without that external corpus, and no `VIEWS_CORPUS_DIR` key exists in the owned private test environment. This optional date-string corpus is distinct from the enabled multitenant corpus, which was not reached at all.

The source owner owns the minimal fixture repair, meaningful wrong-version red/restored controls and refreeze. None of those later changes or results is claimed by this leaf. The separately investigated native 503 warming observation remains unclassified here and is **not this failure**.

## Execution coverage

[The bounded summary](summary.json) records the first-tier command/status and every later tier's NOT_RUN status. Exact-source static inventory identifies **706 tracked test files across 8 tiers**: UNIT 289, DOM 19, dependency 32, core 26, harness 10, integration 287, stress 1 and browser 42. Those are **read-derived file counts**, not counts of passing test cases.

The configured unfiltered enabled corpus contains **86 suites**, including **47 suites with own-fixture declarations**, as read from the exact committed inventory. All 86 were NOT_RUN; no enabled-corpus execution record was produced. The worker's `completedTests: []` means no whole tier completed successfully; the captured UNIT passing/pending/failing counts remain separately reported.

Dependency installation, bundling, inventory and browser preparation had completed before UNIT started. Those preparations do not make the unexecuted tiers or corpus green. The owned Mongo readiness probe failed once and then succeeded; that transient readiness attempt is separate from the later descriptor assertion.

## Cleanup and cost

[Cleanup and cost evidence](cleanup-and-cost.json) preserves the independent boundaries:

- The worker created one owned Mongo container, removed it and verified container/volume absence. `ownMongoCleanupVerified` is true; fixture container and volume residual arrays are empty.
- Controller destruction was verified at `2026-11-12T17:37:14.698Z`; watchdog cleanup was verified at `2026-11-12T17:37:23.620Z`.
- Independent provider inventory at `2026-11-12T17:39:30.684158+00:00` reported **0 droplets, 0 firewalls and 0 run tags remaining**. Ephemeral private/public SSH key files were absent when this leaf was derived.
- The compute estimate is **$0.05652194443676207** over **406.9579999446869 seconds** of controller-start-through-watchdog accounting, including preprovisioning. It is an estimate, not an invoice. The selected single `c-16` host was priced at **$0.50/hour**, with an estimated maximum **$1.50 for 180 minutes**. Tax, transfer overage, retained artifacts and cleanup beyond the deadline are excluded; the estimate is not a billing cap.

No droplet, firewall, VPC, IP address, SSH key, host identifier, private environment/spec/inspect record, source archive or dependency tree is published. Hashes identify the retained private originals without disclosing their contents. Cleanup success does not turn the failed functional run into acceptance.

## Verification and scope

[The leaf manifest](manifest.json) binds the published artifacts. Publication checks parse JSON, verify hashes/local links and scan for private paths, credentials/URLs and whitespace issues. Their result is recorded separately from the failed remote experiment. The root/source owner owns programme queue, release, decision and acceptance rollup; this leaf creates no second programme acceptance record.

There was no runtime diagnosis fix, product test rerun, cloud call or additional spend in preparing this record. No further paid acceptance run is authorized by this leaf; native warming and planned source repairs/refreeze remain with their owners.

Publication check outcome: JSON/hash/local-link/privacy/whitespace checks passed. One static `make queue-check` attempt failed at queue validation on 16 existing missing external-worktree cwd references in this isolated checkout; later steps were skipped. [Publication verification](publication-verification.json) and [the retained output](queue-check-output.txt) preserve that limitation. No queue or peer worktree was changed.
