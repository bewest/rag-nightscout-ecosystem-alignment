# Core J full-source execution — 2026-11-12

Status: **FULL_SOURCE_EXECUTION_PASS**. This primary record projects Core J’s own immutable remote capture. All eight tiers and the enabled-corpus command completed with status 0; the worker reported `passed`, no errors, and `COORDINATOR_REVIEW_REQUIRED`. Coordinator review, native qualification, final prcheck and any acceptance receipt remain with the programme owner. This is no release, production M7 or capacity acceptance claim.

## Captured execution

Reproduced remotely; derived here from saved command records and terminal Mocha summaries. UTC execution crossed into 2026-11-13; the dated leaf uses the local campaign date.

| Stage | Passing | Pending | Failing | Command status |
|---|---:|---:|---:|---:|
| unit | 3585 | 1 | 0 | 0 |
| dom | 205 | 0 | 0 | 0 |
| dependency | 368 | 2 | 0 | 0 |
| core | 319 | 0 | 0 | 0 |
| harness | 99 | 0 | 0 | 0 |
| integration | 3643 | 836 | 0 | 0 |
| stress | 18 | 0 | 0 | 0 |
| browser | 686 | 0 | 0 | 0 |
| enabled-corpus | 839 | 1 | 0 | 0 |

[Execution projection](execution.json) retains fixed command metadata and pending summaries. Unit’s optional pending case is “is moment's own parse on every date string of VIEWS_CORPUS_DIR (read in place)”. Dependency has two pending ajv resolution cases. The integration tier recorded 836 pending cases; these are distinct from the subsequent enabled corpus.

The [enabled corpus](corpus.json) selected 86 suites, exactly matching the frozen source inventory, and recorded 839 passing, 1 pending, 0 failing. Its optional pending case is “reports end-to-end successful request latency and throughput”; read-derived source attribution is `tests/tenant-commit-clock-http.integration.test.js:291–293`, behind the explicit benchmark opt-in. Global counts and selected inventory are captured; a separate per-file completed-body ledger was not recorded.

Harness stderr contains `TEST_EXECUTION: no intended test files (support tests do not count)`. This belongs to the passing nested negative-control case “does not count the database safety/cleanup files as intended coverage”: frozen source `tests/test-select.test.js:253–262` deliberately invokes the reporter with safety/cleanup helper files and asserts rejection. The outer harness command passed with 99 cases. The corpus stderr has no such diagnostic.

## Identity and cleanup

Exact source pins and captured toolchain are in [provenance](provenance.json). Node `v24.22.1`, npm `11.19.1`; the recorded lock and worker hashes were independently matched to the exact committed Git bytes. A captured remote worker SHA and matching committed bytes are recorded separately; no remote worker-file capture is invented. No H, I, baseline D, new image, native or external-smoke result supplies J’s execution proof.

[Fixture and cleanup projections](fixture-and-cleanup.json) preserve Mongo’s requested/configured/effective nofile 65536, owned Mongo cleanup verified, and empty container/volume residuals. The corpus created two owned fixtures (Vault and PostgreSQL); both removals were verified and remaining fixtures were empty. Controller and watchdog cleanup were verified. The independent audit at 2026-11-13T00:55:16.267Z found zero droplets, firewalls and tags and confirmed removal of both exact original temporary keys. This leaf publishes counts and states, excluding provider identities.

## Publication checks

[Five offline metadata negatives](projection-controls.json) reject a wrong source, missing stage, failed corpus, unverified owned cleanup and capacity overclaim, with the original projection restored after each. These controls test the publication boundary; no application campaign was rerun. [Publication verification](publication-verification.json) records JSON, hashes, links, bounded privacy/whitespace checks and the actual static queue-check outcome. [Captured static-check output](queue-check-output.txt) is retained. [Manifest](manifest.json) binds all leaf files except itself. Private originals remain unchanged; public JSON files are labelled whitelist derivatives. Programme decisions, queue/release updates and diagnosis remain with the source owner.
