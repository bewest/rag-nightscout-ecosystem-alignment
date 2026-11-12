# Source-paired M7 receipt validation

Reproduced on exact alignment source `142e301b745ddc7b2a60fbc1ed5db032eeb00b46`, original history after `7d468fc24455cf2a221bb92e02406a88c6aab50c`, based on `d8ad514b82a4f114fb450da2750db70ffcc172da`. This is a local recorded-evidence capability, not application acceptance or a capacity measurement. No production PASS receipt or expectation was created.

The [validator](../../../tools/queue/gates/m7_joined_receipt.py), [focused controls](../../../tools/queue/gates/test_m7_joined_receipt.py), and [integration contract](../../../tools/queue/gates/m7_joined_receipt.md) implement the complete local capability. [Source attribution](source.json) pins exact bytes and Python version. Queue, release and decision files are untouched.

## Reproduced checks

```bash
python3 -m unittest discover -s tools/queue/gates -p test_m7_joined_receipt.py -v
python3 -m py_compile tools/queue/gates/m7_joined_receipt.py tools/queue/gates/test_m7_joined_receipt.py
```

[Exact committed focused result](focused-exact.txt): **42 tests pass**. Controls use synthetic records in owned temporary directories, removed afterward; they do not run native infrastructure or write shipping checkouts. Python syntax and source whitespace checks pass.

- Functional acceptance rejects missing/not-run or nonzero tiers, zero/failing tests, undeclared pending counts, incomplete enabled corpus, missing criteria/controls, missing restoration, diagnostic-as-full and wrong source/image/instrument/artifact identity.
- An explicit one-pending policy with a reason passes; the actual D5 exception is the absent external `VIEWS_CORPUS_DIR` moment date-string corpus. This is not a missing enabled multitenant suite and does not make pending tests passing tests.
- Source-specific clinical evidence may retain an explicitly approved earlier core/baseline attribution. Changing that attribution refuses; no automatic ancestry or runtime-equivalence inference exists.
- A checker-source ablation that skips controls falsely admits an incomplete record and makes the refusal oracle fail. Restoring the actual checker restores refusal. Independent role/HTTP-shape guard ablations likewise falsely admit incomplete records and make their refusal oracles fail.
- Synthetic capacity milestone proof with 3k/four APIs PASS and one/two APIs honestly FAIL passes its specified scope without any 10k row. A failing claimed target, absent comparison, inconsistent assessment or missing numeric observations refuses. The full-ladder contract remains a separate optional scope.
- Pilot fixtures cover each explicitly pinned fixed API profile 1, 2 or 4 across 500/750/1k; missing/mixed pins refuse. A fixed two-API pilot cannot claim API scaling or 3k capacity.
- Broad scaling rejects missing components, a single/duplicate configuration, zero samples, booleans replacing measurements and absent binding inventory. Actual HTTP shape names and serving-role inventories are pinned by profile/replica/window. Missing realtime, missing RSS, wrong seven-shape set and negative CPU/memory observations refuse.
- The full-ladder CLI is exercised against copied source/contracts in a temporary tree: before/after file bytes are identical, including absence of import bytecode caches.

The gate reads actual worker command statuses/return codes and Mocha stdout, actual enabled-corpus records, and original per-cell capacity fields. Independent artifact pins and literal outcome predicates supplement rather than replace completeness checks. The coordinator selects and reviews the complete required native/client/clinical/OIDC/control checklist.

## Actual failed-campaign negative control

The real retained D5 worker `result.json` was read, never edited. Its source is core `d5e2e874659155c952b5b5deb862f12f982ac02e` with deploy `bc7b8c56b19d7a87fea668e0adb8b939e580de1e`. It reports UNIT return code 29; its actual stdout epilogue is 3,478 passing, one pending, 29 failing. All seven later tier commands are absent.

The exact final validator refuses it with **`M7_CAMPAIGN_INCOMPLETE`**. [Sanitized observation](actual-failed-campaign.json) retains the actual input hash, assessed counters and refusal. The surrounding test-only graph has synthetic identities; it is ephemeral and cannot be used as a production receipt. The private runner's argv/environment/log contents were not copied. [Absent proof CLI](absent-proof.txt) independently exits 1 with `M7_JSON_FILE`.

## Review findings and preserved boundaries

Initial source `7d468fc2` lacked adequate role/shape/RSS completeness predicates despite artifact integrity pins. Coordinator review identified that a wrong seven-shape set or omitted serving-role observations could pass. Follow-up `142e301b` adds source-selected exact inventories and real CPU/RSS/memory requirements with semantic controls. The accepted focused result above is on the repaired source.

Upstream shapes were inspected before implementation. RSS is the original `processRssKiBAfter` Docker `top` table, not a numeric scalar; the gate validates numeric RSS KiB rows and does not substitute cgroup memory. The existing strict campaign checker requires all 12 ladder cells PASS, so it remains optional: making 10k stretch mandatory for the adopted 3k milestone was rejected. Raw failed per-cell summaries are consumed directly because the campaign master appends only successful returns. The older adapter pilot checker remains unchanged; the new receipt pilot predicate explicitly pins the selected replica profile.

A separate **read-derived, not reproduced here** producer issue remains with the next profile lane: transient k6 is sampled as a Compose service, but after it exits the reducer can create a stats-only role lacking snapshot fields and subsequently index `anonBytesAfter`. This checker invents no RSS for exited load generators. Their observations belong separately from the serving-role inventory. No producer file was changed by this lane.

## Integration owner and checks

Root owns actual expectation/receipt creation after valid proof, exact accepted historical attributions, queue wiring/control entries and programme state. Functional acceptance does not demand future capacity; capacity milestones do not imply broad component scaling. The tool contract lists the required queue wiring and malformed/missing-proof controls. No current source/application/capacity verdict is promoted by these synthetic checks.

`make queue-check` was attempted in this owned alignment tree and exited 2 during queue validation because programme gate worktree directories are absent. [Output](queue-check.txt) is retained; this is missing local setup, not a product failure. No queue setting was changed to suppress it. No full/browser/capacity campaign, cloud action, source push or PR was performed.

Captures replace workspace prefixes and trim line-end whitespace before immutable recording. Original local captures remain in the lane handoff.
