# Preexisting evaluator hot-file cache failures

Captured 2026-11-12. Final cache lane source is
`9f7e6bca2d39cb8d37fd9ac5918a9785eba0116e`. [Source and artifact hashes](result.json)
pin this addendum to the [original repair](../README.md) and
[placement ownership follow-up](../ownership-followup/README.md). Those captures
are unchanged. No comprehensive acceptance or capacity claim is made here.

The evaluator's outer metadata cache is **preexisting in frozen D5**, not introduced
by retained placement descriptors. Its source header promises fresh operator
configuration at every cycle. Independent actual-loader checks now reproduce both
failures: a same-size edit with identical instrumented metadata returns `v1` instead
of `v2`, and lowering the current byte limit has no expected refusal. The exact D5
module, read with `git show` and injected into a disposable test process, fails
both checks. Its SHA-256 is
`5653f8ef07137f7e097505b65405f25b35f6ded924a7eedfc6867ff84c7b1d05`.
The instrument preserves actual device/inode/size/mode while freezing timestamps;
no sleep or forced timestamp hides the edit. The separate old-kernel remote
collision capture remains the original filesystem measurement.

The narrow repair removes evaluator metadata-only caching from its supported
static/lab hot-file callback. Each call reads bounded bytes using the existing
single reader, compares text, and reuses JSON/roster parsing when unchanged. Current
bounds and named `PreviewConfigError` refusals remain effective. Changed roster
expansion and infrastructure still require restart. Secondary changed parses
retain their fresh infrastructure hash, close temporary placement, then borrow
the initial consumer transport; actual runtime ownership is unchanged.

Measured legacy unchanged path: 50 calls, 50 bounded reads, one JSON/roster parse,
zero roster-key enumerations and zero retained file descriptors. These file-size
costs belong to static/lab compatibility. Registry evaluator boot already replaces
that callback with admitted registry membership and per-tenant authoritative
settings reads. An actual boot composition discriminator poisons the legacy callback,
deletes its file, then executes 200 registry current reads: zero legacy file reads,
zero roster-key enumerations, 200 settings reads. Database and readiness adapters
are explicit doubles and the discriminator stops before clinical startup. This
measures callback selection, not fresh native database acceptance.

Final focused source-runner checks: **129 passing across 13 affected files**.
Evaluator-source ESLint exits zero with empty output; tier inventory reports
700 files / eight tiers. The prior module control and exact D5 control each exit
2 with two semantic failures. Shipping source is never modified by a control.
The retained [exact-D5-control.cjs](exact-D5-control.cjs) runs against the pinned
repair tests with the parent record's direct-Mocha command, `--require` this file
and `--grep EVALUATOR_HOT`; it requires the local repository to contain D5 history.

No full suite, browser/native database campaign, repaired-source old-kernel rerun,
capacity run, cloud activity, prcheck or push occurred. The coordinator must join
all planned source repairs and freeze the next acceptance candidate before repeating
the comprehensive campaign. Original static zero-read measurements are historical;
they are qualified by this explicit compatibility contract rather than rewritten.
