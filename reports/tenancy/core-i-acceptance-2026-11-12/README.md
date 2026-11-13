# Core I primary failure evidence — 2026-11-12

**Captured result: FAILED / full acceptance NOT_ACHIEVED.** UNIT returned 1 with **3583 passing, 1 pending and 1 failing**. Execution stopped there: the other seven tiers and the entire planned enabled corpus were **NOT_RUN**. No corpus file is retained or fabricated. This is not release, production or capacity acceptance.

This immutable leaf projects I's primary saved records directly. It is not a reconstruction from an earlier successful campaign. Public artifacts contain bounded, whitelisted fields and original SHA256 anchors; no raw logs, private environments or identifiers are copied. Source diagnosis, repaired-candidate acceptance and programme rollup remain with the root owner.

## Frozen source

| Identity | Exact captured commit |
|---|---|
| Core | `df71c8e815d65d3abcdf6109664ea841bba17733` |
| Deployment | `8c27567186f7ede8b6c49674d9751f9e79e8d330` |
| Alignment | `f5d29a53bf41baf4dc03c3abfaa9a57929e6337c` |
| Transport | `f9a39f7dbca1efb9787afd61c15443e545717ef2` |

[Provenance](provenance.json) binds the captured source/Node/lock/worker metadata, exact frozen failure-source bytes, private spec/result/command/log/cleanup records and archive. The archive SHA256 is `c8b67db690c943d9edadc5a759268a127f7e91136acf7f12c0fcae3eedcfc604`. Captured toolchain is Node `v24.22.1` and npm `11.19.1`; no local application execution was used to infer this identity.

## Actual failing command and coverage

[Execution projection](execution.json) preserves the actual argument array `node scripts/test-tiers.js run unit`, its 1800-second command bound, captured start/end times, failed status and return code 1. The terminal Mocha summary is 3583 passing / 1 pending / 1 failing. The single pending case is the optional external `VIEWS_CORPUS_DIR` moment date-string check; its actual name and original line number are retained separately.

The sole failure is **EVALUATOR_REGISTRY_CURRENT** in the bounded read-through/pinned atomic publication cache suite, `tests/realtime-publication-cache.test.js:211:43`. The assertion observes **settingsReads 0 versus expected 200**. The exact frozen source still requires 200. The worker reports COMMAND_FAILED_unit and completedTests:[]. The captured sourceAcceptance flag is COORDINATOR_REVIEW_REQUIRED; failed execution supplies no full-acceptance receipt.

**Runtime cause remains UNCLASSIFIED.** A mock-hook or test-fixture explanation is a hypothesis until independently reproduced. This leaf does not replace the expected count with 0, waive current per-tenant settings reads, or weaken freshness guarantees. It makes no assertion about a repaired candidate. Independent old-reference baseline work is a different measurement and is not mixed into I.

## Fixture, cleanup and bounds

[Fixture/cleanup projection](fixture-and-cleanup.json) records Mongo startup and before-UNIT health/limit commands passing. Actual mongod PID1 nofile limits were **65536 soft / 65536 hard**. Final worker ownMongoCleanupVerified is true, with empty fixture-container and volume residual arrays; positive removal/absence commands returned 0.

Controller and watchdog cleanup are verified independently of the failed functional result. The independent provider audit at **2026-11-13T00:10:22.525Z** reports **0 droplets, 0 firewalls and 0 tags**, plus **two exact-original temporary key removals**. Timestamps are UTC; the leaf uses the repository's November 12 work date. No key paths, provider IDs, network addresses or private inspection records are published.

Configured bounds were one `c-16` functional-test host, at most 180 minutes and a $1.50 runtime estimate ceiling. `compute-estimate.json` is absent, so actual compute cost is **UNMEASURED**; no earlier-run cost is substituted. Cleanup success does not turn the failed run into acceptance.

## Projection verification and handoff

[Five bounded negative controls](projection-controls.json) refuse a wrong source, laundering the failure into PASS, lowering the current-read expectation, inventing later corpus coverage and dropping owned-cleanup proof. The original I projection is accepted only as consistent **failed evidence**. These are in-memory metadata controls, not product tests or another campaign.

[The manifest](manifest.json) binds the leaf. Publication checks cover JSON, artifact hashes, local links, privacy and whitespace, with actual static-check outcomes recorded separately. No application/source fix, campaign, cloud/SSH/native test, plot, private-file mutation, queue/release edit or push was performed by this lane. Root owns the ordinary original-history merge and any later publication or source diagnosis.

[Publication verification](publication-verification.json): JSON/hash/local-link/privacy/whitespace and primary-anchor checks passed. One static `make queue-check` attempt failed at queue validation on 16 existing absent external-worktree cwd references; later steps were skipped. [Exact output](queue-check-output.txt) is retained. No peer or queue file was changed.
