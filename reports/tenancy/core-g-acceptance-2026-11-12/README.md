# Core G acceptance failure — 2026-11-12

**Captured outcome: FAILED; source NOT_ACCEPTED; capacity NOT_ASSESSED.** All eight
ordinary tier commands returned 0, with 8,901 passing and 839 pending test cases
in their terminal summaries. The enabled corpus then returned 1: **838 passing,
1 pending, 1 failing**. Cleanup does not turn this run into acceptance.

This immutable leaf is a bounded, sanitized derivative of the existing G capture,
not another run or repair. It retains no credentials, private environment, raw
log dump or provider/resource identifiers. Private original hashes and the
hash-verified parent assessment are bound in [provenance](provenance.json).

## Exact executed inputs

| Identity | Commit |
|---|---|
| Core | `761e8f19373c4fbbd6fc888b51b35c9b2eb677a1` |
| Deployment | `31565abe437ea84214aa0068f75de1246c06e45e` |
| Alignment instrument | `502b46b05bc9a581d2c371f18f7e0e71852f0578` |
| Execution harness | `7209cb29020543a82412cd69d2751ca939cf4318` |

Captured Node `v24.22.1`, npm `11.19.1`, kernel `6.8.0-147-generic` and the Node,
lockfile, CI environment and worker hashes retain their original attribution.
The committed worker bytes independently match its captured hash; that does not
create a nonexistent original target-file mode observation.

## Completed commands and coverage limits

[Summary](summary.json) reports recorded outer command exits, not inferred child
process exits. Terminal Mocha counts are test cases, not source-file counts.

| Ordinary tier | Passing | Pending | Recorded exit |
|---|---:|---:|---:|
| Unit | 3,563 | 1 | 0 |
| DOM | 205 | 0 | 0 |
| Dependency | 368 | 2 | 0 |
| Core | 319 | 0 | 0 |
| Harness | 99 | 0 | 0 |
| Integration | 3,643 | 836 | 0 |
| Stress | 18 | 0 | 0 |
| Browser | 686 | 0 | 0 |

Pending is not passing and ordinary integration's deferred opt-ins do not become
executed because the later corpus ran. Harness stderr includes an intentional
nested `TEST_EXECUTION` no-intended-files/support-tests diagnostic; this leaf
makes no blanket claim that every stream lacks such text. The integration and
corpus had no captured execution-guard failure; their recorded command outcomes
and terminal summaries remain the authority here.

The corpus selected **86 suites**, matching the exact frozen unfiltered source
inventory. A separate per-file body-completion event ledger was not serialized;
**86 selected is not an independently measured executed-file count**. The saved
corpus record reports start `2026-11-12T19:43:52.352Z`, finish
`2026-11-12T19:55:08.157Z` and global 838/1/1 outcome. No later repaired results,
other campaigns or independently passed bodies are stitched into G.

## Sole failure and optional pending benchmark

[The bounded failure derivative](failure-and-pending.json) keeps original log
line numbers and source SHA. The failing case is `AP_CLI_ONE_AND_REFUSALS`, at
`tests/admin-provisioning.integration.test.js:138:12`. Its permission-refusal
assertion compared **0 to expected 64**. That captured assertion is not presented
as a separately recorded CLI child-process ledger.

**Read-derived hypothesis from exact G source:** line 137 creates the supposed
readable-file fixture with requested mode `0o644` and no explicit chmod. The
committed selected worker sets umask `0o077` at line 277. Thus the fixture may
not have established the intended group/world-readable precondition. **G did not
capture the actual target-file mode: it remains UNMEASURED.** This source
explanation is not conclusive attribution of the historic failure, a reproduced
runtime permission vulnerability or evidence of a repaired candidate. The source
owner separately owns focused real-CLI/precondition diagnosis and any fixture
repair; none is claimed by this leaf.

The one corpus pending case is `reports end-to-end successful request latency
and throughput`, `tests/tenant-commit-clock-http.integration.test.js:293`, under
its explicit `NS_TENANT_COMMIT_CLOCK_BENCHMARK=1` opt-in. Its performance benchmark
was not exercised; ordinary functional coverage does not make it a latency or
throughput measurement. Other pending catalogue/classification work is separate.

## Captured cleanup and publication scope

[Cleanup](cleanup.json) separates retained observations:

- Worker-owned Mongo cleanup verified; fixture container and volume residual
  arrays empty. Corpus-owned PostgreSQL and Vault fixtures were recorded removed,
  with verified absence and no remaining corpus fixture entries.
- Controller cleanup verified at `2026-11-12T19:55:50.902Z`; watchdog at
  `2026-11-12T19:55:58.370Z`.
- Saved provider inventory at `2026-11-12T19:56:48.437703+00:00` reports 0 droplets,
  0 firewalls and 0 run tags. This is review of a retained parent capture, not a
  new provider query. Ephemeral private/public key absence is a **parent-observed**
  filesystem fact from its hash-bound assessment, not independently re-observed.
- The captured compute estimate is an estimate, not an invoice or billing cap.
  No additional resource activation or spend occurred in deriving this leaf.

[The derivation script](derive-public.py) reads only supplied local artifacts and
pinned Git objects, verifies parent/raw hashes, independently checks each terminal
count/outer return code, and publishes a fixed field selection plus a small
failure excerpt. [Manifest](manifest.json) binds public bytes. No source/fixture,
queue, release or captured original was edited; the coordinator owns the next
freeze and acceptance decision. G remains FAILED.

Publication verification: JSON parsing, bounded field/credential/privacy scan,
local README links and whitespace checks pass. The one static `make queue-check`
attempt stops at 16 existing missing external-worktree cwd references in this
isolated checkout; later steps were NOT_RUN. [Verification](publication-verification.json)
and [its retained output](queue-check-output.txt) preserve that failure rather
than treating it as green or altering queue/peer worktrees.
