# Native unavailable-model repeat-clock cause and repair

Captured 2026-11-12. **Reproduced** causal discrimination and focused repair
qualification. The [original actual paired failure](../original/README.md) stays
failed and immutable. No retained paired stack was reset, overlaid or replayed.
Fresh repaired shipping qualification and frozen comprehensive acceptance remain
unmeasured in this leaf.

## Source and scope

Original product `195c932293f3abc648da8fbe4356bf7360acd002` with the registered
native instrument committed first as `06032dd3b9fbc7979343b4ead308453ebc5c730a`.
Repair `cd4629159809fb3cffbc6f57626f98f3ffdbdda7` changes only the reducer's repeat
deadline selection and its comment, plus focused producer controls. Exact
[old/new reducer and unchanged instrument hashes](source.json) are recorded.

The producer previously retained prior output and alarm state during model
unavailability but removed the known repeat deadline. Identical recovery then
entered its repeat path with a missing prior deadline. That exact repeat/null
cause matches both early accepted duplicate origins in the original paired run.
The native fixture below isolates and reproduces the transition.

The repair retains the prior deadline while no eligible current model is
available. A valid unarmed output still retires its deadline; explicit repeat-off
remains off. Due processing and configuration reset use their existing paths.
Eligibility, stale/current-source, generation, ACK/clear, RLS, operation-window,
lock and schema guards are unchanged. No new lock, index, table or failover
policy is introduced, and unavailable normal effects remain inadmissible.

## Actual PostgreSQL warm-barrier discriminator

[Exact registered instrument](instrument-native.test.js), opt-in
`NS_EVALUATOR_EFFECT_DOCKER_TEST=1`, owns its digest-pinned PostgreSQL container
on a random loopback port. Actual runtime, producer, notification store, durable
attempt/acceptance and operation windows run against PostgreSQL. A controlled
fresh-owner clinical-create barrier lets the real producer observe a missing
current model before the new model is released. Actual clinical-view rules
produce a fixed synthetic output; suppression and sink acceptance are explicit
ports. This isolates availability from changes in clinical content. It does
not replace the full shipping membership/clinical/socket proof.

The lifetime pool has **max 2, observed 2 clients**, permitting the admitted
clinical warm job and producer observation to overlap. The outbox store has its
own max-one pool and setup/admin observer is separate. This differs from the
scheduler's earlier max-one nested-job proof. Exact owned container and recorded
anonymous volumes are verified absent after teardown.

| Check | Original | Repaired |
|---|---|---|
| New owner, no unavailable-model observation | One accepted logical effect; known deadline retained | Same |
| Warm barrier; unavailable observation; identical recovery at 4,438 ms | Deadline absent while prior output remains; second identical accepted effect; missing-clock cause matches | Original deadline retained; one accepted request, zero missing-clock causes |
| Warm barrier; recovery at the original 60-second deadline | One genuine repeat | One genuine repeat with the original deadline's provenance |

[Original enabled-corpus capture](native-original.txt) and [runner record](native-original.json):
**2 passing, 0 pending, 1 failing**, exact assertion
`NATIVE_IDENTICAL_RECOVERY_MUST_NOT_CREATE_EARLY_REPEAT` (`2 != 1`).
[Repaired capture](native-fixed.txt) and [record](native-fixed.json):
**3 passing, 0 pending, 0 failing**. The same native test bytes are used on both
sides. Test tiers and enabled-corpus registration include this suite; inventory
is 706 files / 8 tiers and 86 opt-in suites.

The [producer protocol controls before repair](producer-controls-original.txt)
report 10 passing / 2 failing: early recovery and genuine due-origin provenance.
The [focused repaired batch](focused-fixed.txt) reports **62 passing**, covering
producer/outbox rules, real normal-to-alarm transition, existing retry/current
source/ACK/clear policy, consumer composition, partitioning and scheduler caller
fences. The independent review's pure safety matrix is a separate evidence home.
No full campaign was run by this leaf.

## Corrected shipping oracle, without clearing the old failure

Binding `5ce61e1414637097c526d23a5729be6a425361a0` corrects only the test oracle:
B's intentional changed reading is one legitimate new payload. The expected
accepted normal transitions are A initial, B initial, B changed. Exact source
effect digests and origins distinguish these; immutable initial request IDs and
origins remain unchanged. Cancelled superseded rows are classified separately.
Extra live/pending or accepted identical effects and fabricated clears refuse.
Actual socket fanout must match those three effects, the new B frame carries its
exact upload timestamp/checkpoint, and the proof must finish before both original
durable repeat deadlines. Heartbeat cadence is never changed to pass the test.

[Oracle controls](oracle-focused.txt): **11 passing, one actual shipping skip**.
The [actual preserved bad-row control](oracle-actual-bad-rows-control.txt) still
rejects the identical early A effect. Removing only the two exact repeat/null
origins yields a labelled metadata counterfactual with three intentional effects;
that is not repaired runtime evidence. The [control script](oracle-actual-bad-rows-control.cjs)
projects synthetic fanout digests from typed rows, not actual observed sockets.
An initial adapter naming mistake (`payloadDigest` versus `effectDigest`) was
corrected; the committed oracle now refuses incomplete typed identity metadata.

Run the registered causal suite in either exact source:

```bash
node scripts/test-multitenant.js --only evaluator-effect-idempotency --record /tmp/evaluator-effects.json
node scripts/test-tiers.js check
```

[Artifact digests](artifacts.sha256.json) cover the captures and exact instrument.
Root owns final source/binding pin refresh, fresh paired qualification,
comprehensive acceptance and programme/defect-register state. Neither this leaf
nor the independent collector qualification clears the preserved clinical gate.
