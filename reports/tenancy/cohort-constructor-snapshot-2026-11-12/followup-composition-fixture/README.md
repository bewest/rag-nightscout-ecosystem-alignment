# Lifecycle composition fixture boundary — 2026-11-12

The coordinator's joined focused check found four failures in the recording
storage double used by `tests/internal-api-composition.test.js`. The
[original source repair](../README.md) added an asynchronous cohort snapshot;
this fixture still supplied only the synchronous datastore/backend accessors.

On source `5487e4b9cde3adffcd8b8150d4db3056703899d9`, the same isolated test module
[reproduces 15 passes and 4 failures](before.txt): lifecycle status over UDS and
HTTP is unavailable, a held-response drain times out, and the blanket-window
control reaches the wrong earlier error.

Fixture-only follow-up `5606226ec856d461b254c372228608eb1b462c5d` supplies the
async snapshot from the same recorded datastore and backend tuple as the prior
accessors. It changes no product code or assertions. The module then
[passes all 19 checks](after.txt), including current-wire service ownership,
suspended A refusal with B progress, the held application response drain, and
the blanket listener-window red control.

This is reproduced fixture compatibility repair, not native initializer or full
joined deployment evidence. Native tests continue to use actual PostgreSQL
initialization. The earlier source and native measurements remain unchanged;
fresh paired shipping restore and evaluator acceptance are still pending.
Captures are pinned by [SHA256SUMS](SHA256SUMS).
