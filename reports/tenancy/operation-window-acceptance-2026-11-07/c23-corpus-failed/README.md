# c23 enabled-corpus failure

**Reproduced:** the entire declared 47-suite enabled corpus on `c23cf1f35d819738842041babc0aef2dbde96c21`, tree `761d763fbff124cdba7bcb8a87177fed7352ee25`, finished with **531 passing, one pending and six failing**. Mocha exited six; its runner exited one after 269.90837290976197 seconds. Both source/verification trees remained clean/exact. [Machine summary](summary.json) records the test verdict, failure locations, independent release and artifact digests.

| Failure family | Count | Actual symptom / source location | Next boundary |
|---|---:|---|---|
| Clinical projection after producer death | 1 | Committed synthetic reading missing at `tests/tenant-projection-evaluator.integration.test.js:144`. | Causal diagnosis; product-versus-fixture classification remains open. Preserve the clinical oracle. |
| Tenant-operations source insertion | 4 | `TENANT_ORDINAL_BINDING_REQUIRED` at fixture `source`, `tests/tenant-operations.integration.test.js:50`. | Evaluate the current typed insertion contract; preserve binding and authorization guards. |
| Tenant-operations upgrade/rollback | 1 | `LIFECYCLE_COUNTER_INVENTORY_INCOMPLETE: entries` at `tests/tenant-operations.integration.test.js:179`. | Evaluate catalogue/table/counter inventory and preserve the independent restore/rollback oracle. |

The independent observer correctly refused corpus status/test acceptance. It verified cleanup with no observer errors, recording 41 owned containers, 58 volumes and 129 process births. The supervisor stopped after the failed step and closed/reaped its host children. The lead independently verified exact baseline inventory/selected static metadata and all observer births absent, then found all 266 supervisor-retained/owner births absent. No complete configuration, full endpoint equality or global quiescence claim follows from that selected baseline profile. Scientific failure and physical release remain separate verdicts.

Exact command, following a finite single-use lead grant:

```bash
python3 externals/work/m6-coherent-c23-followon-final-prep-20261107/supervisor.py --spec externals/work/m6-acceptance-continuation-20261107/corpus-c23-supervisor-spec.json --grant externals/work/m6-acceptance-continuation-20261107/corpus-c23-supervisor-grant.json
```

The actual corpus command was `node scripts/test-multitenant.js --record <owned record>` with no `--only`, all 47 declared inventory files, and benchmark mode zero. The bound was 7200 active seconds plus one 120-second cleanup interval. No selective test pass, pending conversion, relaxed data oracle or automatic broad retry was applied.

Existing source owners separately diagnose the two capabilities. Focused measurement and meaningful controls precede original repairs, normal joining and one coherent final acceptance boundary. The accepted c23 native/full/browser results retain their exact attribution. Publication and whole-M6 admission remain held.
