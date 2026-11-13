# Focused hybrid configuration-cache repair

Captured 2026-11-12. Core `96cc87c9f8809896f48de878a69bf7bb5a8ac69e`, branch
`codex/realtime-cache-repair-20261112`, is **fixed on a branch**. The focused
checks pass; comprehensive joined-candidate acceptance and capacity are unmeasured
here. [Result, source hashes and artifact hashes](result.json) pin this capture.
The prior [reproduced old-kernel collision](../realtime-cache-collision-2026-11-12/README.md)
is a separate immutable measurement; this repair does not alter that record.

## Contract and mechanism

The measured identical-metadata witness rules out a universal immediate in-place
freshness guarantee from filesystem metadata alone. The adopted hybrid contract
keeps generic/operator hot-file compatibility: `parsedFile` defaults to bounded
read-through, comparing bytes and parsing only changed text. Static/lab realtime
configuration and admission retain next-call visibility of same-size in-place
edits, without sleeps or forced timestamps. Their configured file-size cost is
explicit. Earlier static-roster zero-read performance measurements do not prove
that freshness property and are not a production registry cost model.

The redundant outer realtime cache also bypassed the current byte limit. Its
removal is independently measured by a synthetic configuration over 65,536 bytes:
a lower current bound now refuses the next read even when the file is unchanged.
The source-derived outer-cache ablation produces a missing-expected-rejection
failure. The generic parse-on-change expectation remains immediate; it was not
weakened to admit stale same-size edits.

Production registry realtime reads its role file at boot, then obtains each current
tenant from the admitted registry set and authoritative settings reader. The actual
`registryMode` composition discriminator makes 200 per-tenant calls after deleting
the boot file: zero boot-file reads and zero roster-key enumerations, while 200
settings reads still occur. SQL/resource adapters are explicitly doubled. This
measures the composition/cost seam; it does not claim native database acceptance.

Only machine-owned placement metadata opts into atomic-publication caching.
The actual publisher already writes a complete temporary file, fsyncs it, renames
it and fsyncs its directory. The reader retains one descriptor for the accepted
inode, preventing inode reuse after multiple unobserved replacements. This closes
the ABA gap that zero stale samples alone could not rule out. Bytes and cached
identity come from the same bounded-reader descriptor. A concurrent path rename
is measured: the opened publication is coherent and the following call sees the
new publication. The old handle closes before replacement acquisition; observed
peak and retained descriptors are both one. Cache hits still validate the current
byte limit and target metadata. In-place writes are unsupported for this atomic
machine publication contract.

Valid symlinks remain compatible for both modes. Target replacement/repoint,
missing/nonregular targets, invalid JSON, current bounds and permission refusal
are covered. EACCES is instrumented because CI may run as root; mode changes and
all descriptor cleanup use real files. Independent byte-growth coverage defeats a
false pre-read size and observes the existing read-limit refusal. No unbounded
reader or separate byte-reading implementation was introduced.

Runtime close paths release placement handles in realtime, evaluator consumers,
operation cohorts and central role composition, including failed boot and failed
shutdown. Finalization is fallback only. Reader factories are process/role resources,
not tenant resources: realtime role configuration, evaluator consumer route
configuration and operation-cohort configuration can each own one handle, up to
three in their co-resident process. Direct `load`/`loadRoutes` callers close explicitly.

Source mechanisms: `lib/server/realtime/contract.js:38`,
`lib/server/serve/config-file.js:73`, `lib/server/realtime/config.js:48`,
`lib/realtime-placement/index.js:115`; runtime cleanup is pinned in `result.json`.

## Checks and meaningful controls

Actual local host: Node v22.23.4, Linux 6.18.7-76061807-generic x86_64. This is not
a repaired-source rerun on the old kernel. Focused source-runner acceptance:
**53 passing across eight files**; changed-source ESLint passes; tier registration
reports **700 files / eight tiers**. The isolated publication cache tests instrument
coarse timestamps while preserving actual device, inode, size and mode.

| in-memory source ablation | measured exit / failing checks | exact discriminating symptom |
|---|---:|---|
| default metadata caching | 2 / 2 | same-stat in-place edit returns 1 instead of 2 |
| omit inode from atomic cache key | 2 / 2 | same-time replacement returns 1 instead of 2 |
| freeze accepted value | 15 / 15 | changed authority remains stale; required refusals disappear |
| restore outer realtime cache | 3 / 3 | lower current byte bound has no expected rejection |
| omit reader close | 5 / 5 | descriptor remains after actual role stop, failed boot and failed shutdown |

The source-derived mutations exist only in disposable test-process module exports;
shipping bytes and worktrees are never changed by the instrument. Fresh normal
processes pass after controls. Logs retain original bytes, compressed with their
hashes in `result.json`.

An initial omit-central-shutdown-close control was **vacuous**: it mutated cached
exports, while the focused role-composition test deliberately recompiles its actual
source wrapper with isolated role adapters. The mutation did not reach the tested
wrapper. Its green log is retained and makes no correctness claim; the corrected
omit-reader-close ablation reaches the actual consumed reader and fails all three
exit-path descriptor assertions. This is an instrument correction, not evidence
that shutdown omission is harmless.

## Reproduction boundary

Use the exact source and its own exact-lock development dependencies. A private
`TEST_ENV_FILE` contains only `NODE_ENV=test`, `CI=true`, `TZ=UTC`; the runner process
has no ambient `NS_*`, `NODE_OPTIONS` or `NODE_PATH`. Run:

```bash
node scripts/test-tiers.js run unit \
  tests/realtime-config-cache.test.js tests/socket-admission-cache.test.js \
  tests/realtime-publication-cache.test.js tests/multitenant-config-bound.test.js \
  tests/realtime-placement-map.test.js tests/realtime-placement.test.js \
  tests/realtime-placement-cohort.test.js tests/serve-internal-listener.test.js
node scripts/test-tiers.js check
```

For each control, set `M7_CACHE_CONTROL` to one table identifier (`metadata-default`,
`ignore-inode`, `freeze`, `outer-cache`, `omit-reader-close`) in a fresh test process:

```bash
node node_modules/mocha/bin/mocha.js \
  --require ./tests/fixtures/realtime-cache-repair-control.js --timeout 5000 --exit \
  tests/realtime-config-cache.test.js tests/realtime-publication-cache.test.js
```

The old `c32` probe intentionally pins D5 runtime blobs and refuses this repaired
source. Do not loosen its pins or reinterpret its historical capture as repair
acceptance. No full suite, browser/native database campaign, capacity run, cloud
activity, prcheck or push occurred in this repair lane. The integration coordinator
owns the coherent repaired-candidate campaign and programme acceptance update.
