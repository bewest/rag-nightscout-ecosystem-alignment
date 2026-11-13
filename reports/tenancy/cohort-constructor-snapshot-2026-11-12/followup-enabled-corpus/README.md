# Enabled native corpus registration — 2026-11-12

The coordinator identified a completeness gap in the
[constructor snapshot repair](../README.md): its new native suite was in the
integration tier but absent from the enabled multitenant corpus. The actual
[before-list check](before-list.txt) refuses the missing inventory row.

Source follow-up `71348c1ea62ce8cc7ab9eb4c73f7c4c9b1fcef21` adds the file/flag row
to `scripts/test-multitenant.js` and the ownership/cleanup row to
`docs/multitenant-test-corpus.md`. It includes the preceding fixture-only
`5606226ec856d461b254c372228608eb1b462c5d` history. Product and native test bodies
are unchanged by this registration.

The [selected inventory](after-list.txt) now includes exactly the requested
suite with `NS_COHORT_SNAPSHOT_DOCKER_TEST=1`, no shared database capability, and
its own PostgreSQL fixture. The fixture pins image
`postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`,
uses an owned random-loopback container and generated private capabilities, and
removes only that container and its anonymous volume in teardown.

Execution through the actual enabled-corpus runner, selecting only this suite,
[passes 3 checks with 0 pending and 0 failing](selected-run.txt). The
[run record](selected-run.json) is retained. The runner provides no shared
fixture here: creation and teardown are performed inside the selected test, so
its own container is not a runner-created shared resource. The
[tier inventory](tier-inventory.txt) remains 702 files in 8 tiers.

This measured the registration and selected native execution while preparing
the committed follow-up. It was not a full enabled corpus or comprehensive
campaign. The earlier native initialization implementation and captures remain
source-attributed separately; actual fresh paired shipping restore and evaluator
acceptance are still pending. Captures are pinned by [SHA256SUMS](SHA256SUMS).
