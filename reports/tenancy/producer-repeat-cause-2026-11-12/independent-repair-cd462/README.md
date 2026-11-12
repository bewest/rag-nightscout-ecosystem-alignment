# Independent repair review: preserve known alarm repeat deadline

Reproduced2026-11-12. Approve the narrow source repair on clean immutable
corecd4629159809fb3cffbc6f57626f98f3ffdbdda7. No material blocker found in this
focused review. This is independent source/reducer/protocol evidence; runtime
owner separately owns its actual PostgreSQL warm-barrier proof and fresh repaired
paired qualification. No production edit, preserved-stack query/mutation, new
policy, cloud action or comprehensive campaign was performed by this lane.

The source archive is195c932293f3abc648da8fbe4356bf7360acd002 plus original
red instrument06032dd3b9fbc7979343b4ead308453ebc5c730a and repaircd4629159.
The only runtime-library delta is producer-state repeatAt selection/comment.
Candidate producer-state SHA9754e8563bde352170066f9757eb8018cedc86ad490b8216cfc94331414e4bf8.
No current/config authority, stale/late-effect eligibility, normal-intent filter,
operation-window, lock, index or schema changes. Missing model retains its known
deadline; eligible normal/unarmed output still retires it; repeatMs=null stays off.

## Explicit fixed expectations and meaningful red controls

The earlier nine-case script deliberately asserted the BUG; it cannot be called a
fixed-source pass. instrument-adaptation.patch records the explicit adaptation:
original unavailable/recovery assertions become retained-clock/no-early-repeat
assertions, and true due origin must encode the original60000 deadline rather
than null. Two extra cases cover unavailable-before-first output and repeatMs=null.
Final fixed script SHA77f5a01b9ebb05647774d2688930e7eb239c991a0ac7ccd8673a30d7eb603077.

All11 synthetic actual-source reducer scenarios pass. Same-config unavailable
and identical early recovery preserve original effect origin/deadline. ACK during
the gap emits its real clear and recovered same output retains EXACT clear origin.
Known normal-empty output retires its clock with stable clear provenance; normal
then real alarm produces a legitimate fresh origin. Changed configuration takes
its existing explicit reset/new-identity path.59999/60000/60001 preserves genuine
repeat boundaries; after an unavailable gap the due repeat origin includes the
original deadline. No prior model invents a clock/effect; selected repeat-off
remains off across unavailable/recovered observations.

Controls are measured and expected:

- Adapted fixed invariant against original195c: RED/exit1, including the
  repeat-null origin that must no longer occur.
- Original BUG-asserting script against candidate: RED/exit1, because its
  missing-clock expectation is now false. This is not a product regression.
- Adapted fixed matrix against candidate: GREEN/exit0.

Original captures remain unchanged. These are actual reducer/private notification
rules with test-owned in-memory state, not durable-store/native reproduction.

## Focused safety regression checks

Exact owned candidate source and this lane's owned same-lock dependencies:

```bash
M7_PRODUCER_CORE=/absolute/owned/core-cd462 \
M7_PRODUCER_COMMIT=cd4629159809fb3cffbc6f57626f98f3ffdbdda7 \
M7_PRODUCER_OUTPUT="$PWD/result.json" node fixed-matrix.cjs
NODE_ENV=test CI=true TZ=UTC node /absolute/owned/deps/node_modules/mocha/bin/mocha.js \
  --exit tests/notification-producer-state.test.js \
  tests/notification-producer.test.js tests/tenant-notifications.test.js
```

47 focused tests PASS. A separate independent actual producer/component plus
recording-store discriminator queues a normal request, observes unavailable model
without dispatch, then recovers the same output before due: zero unavailable
dispatches, one recovered dispatch, same sole durable request UUID. This includes current suppression, stale effect/clear
retirement, late completion/close fences, committed request/attempt before dispatch,
atomic rollback and same-request retry behavior. The selected producer protocol
also confirms unavailable model admits no normal effect. Existing consumer
mayAttempt/current-model fences and producer.select's source.eligible-or-clear
filter are unchanged; preserving a clock does not authorize retained normal work.
This lane does not reinterpret the runtime owner's separate62-test or native
three-test figures as its own execution.

No full suite, browser, enabled corpus, native campaign or new acceptance claim was
run here. Root owns the coherent union/final freeze and comprehensive acceptance.
Runtime owner owns native red→green, actual pending clinical oracle repair and
fresh paired qualification; original failed stack remains retained. Private
originals stay under the lane's owned scratch; all committed data is synthetic.
Capture manifest pins raw/public bytes; only scratch paths in error stacks are
normalized. The source worktree stays clean and no peer worktree was modified.
