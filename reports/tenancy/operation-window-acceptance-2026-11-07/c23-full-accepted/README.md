# c23 full non-browser acceptance

**Reproduced:** all seven non-browser tiers passed on frozen source `c23cf1f35d819738842041babc0aef2dbde96c21`, tree `761d763fbff124cdba7bcb8a87177fed7352ee25`, using private freshly built assets and the reviewed finite supervisor/durable observer. [Machine summary](summary.json) records each tier and exact source/instrument artifact digests.

| Tier | Passed | Failed | Pending |
|---|---:|---:|---:|
| Unit | 2807 | 0 | 0 |
| DOM | 205 | 0 | 0 |
| Dependency | 368 | 0 | 2 |
| Core | 319 | 0 | 0 |
| Harness | 99 | 0 | 0 |
| Integration | 3979 | 0 | 172 |
| Stress | 18 | 0 | 0 |

Runner exit was zero after 349.8824773160741 seconds. Publishing and verification worktrees remained clean at the exact source/tree throughout. The existing pending tests retain their scope; they are not converted into passes.

The independent observer accepted the phase and verified cleanup with zero problems/errors, recording 22 owned containers, 32 volumes and 165 process births. The finite supervisor passed, closed host processes and reaped direct children with no unknown adopted children. The lead independently repeated exact baseline inventory/selected static-metadata comparisons and observer-birth absence, then found all 281 supervisor-retained/owner births absent. Baseline scope does not assert complete configuration, full endpoint equality or global quiescence. No unrelated baseline resource was reconfigured.

Exact command, following its separate single-use lead grant:

```bash
python3 externals/work/m6-coherent-lockfix-final-prep-20261107/supervisor.py --spec externals/work/m6-acceptance-continuation-20261107/full-c23-supervisor-spec.json --grant externals/work/m6-acceptance-continuation-20261107/full-c23-supervisor-grant.json
```

The consumed child command was `tools/lab/multitenant-rest-preview/owned.js all` against the exact isolated c23 verification worktree. The active bound was 7200 seconds and one cleanup bound was 120 seconds. All 28 ownership contracts and eight wrapper/observer code files matched the previously reviewed implementation; changed product and pure-test files did not widen resource ownership.

The [4935 failed campaign](../4935-full-failed/README.md) remains unchanged. This is the first complete c23 campaign; it was not repeated per leaf commit. Default-browser, enabled-corpus, cold Compose, client acceptance and final prcheck remain separate. No whole-M6, production, default, real identity/data, provider or device promotion follows.
