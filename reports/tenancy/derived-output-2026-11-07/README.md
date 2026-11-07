# Evaluator, realtime and API: derived-output characterization

*2026-11-07. Reproduced synthetic component comparison; source/corpus explanations
and recommendations are read-derived. Homes: ARCH-DERIVED-FRAME and
MT-RUNTIME-PLAN. No application change, release/milestone promotion or publication
service is adopted.*

**Verdict:** selected current properties agreed between evaluator and API.
Realtime produced a different output: the browser record frame, preserving
controller predictions. Share compatible current-property results; keep raw
frames, historical calculation, authorization and notification effects separate.
The repeated work observed includes input/projection handling, not a duplicated
realtime alarm-plugin cycle.

## Boundary and results

Application `f0fac99a2fccee259c9a76eba0123058bf288d96`, tree
`09dd7baf52d51f2725e7cac732fabd3f8280b482`; Node `v22.23.4`, PostgreSQL `16.15`.
Actual evaluator/realtime source modules and restricted PostgreSQL readers ran,
plus the actual properties HTTP handler with a synthetic preauthorized context.
This is not acceptance of the complete public authorization/role stack.

Two reseeded campaigns used **one child and one PostgreSQL process**, crossing
Loop, OpenAPS and treatment-only provenance with small (34–35 records) and
history (758–759 records) inputs. Acquisition paths had two warmups and five
retained samples per campaign/cell, in alternating order. Tick cells had one
sample per campaign. These are not independent process repetitions. Selected
property hashes matched between reseeds in all six cells: 360 metric rows and
six intended controls. Per-cell distributions and source/closure attribution are
in the [portable measurements](summary.json), without private paths, credentials
or Docker identities.

| Probe | Reproduced result | Decision implication |
|---|---|---|
| Current values | Required bgnow, delta, direction, IOB, COB and device uploader-battery properties agreed at the JSON wire boundary. Loop IOB/COB were 1.25/18; OpenAPS 1.75/21. | These six families are scoped reuse candidates, not proof of every plugin/property. |
| Realtime | Latest SGV agreed with BG for this single-uploader fixture; raw controller predictions remained present. | Properties cannot replace the record/frame contract. This is not a general multi-uploader bucket-mean rule. |
| Time without writes | At +45 minutes, IOB changed from 1.25/Loop to 1.425/Care Portal with the same checkpoint; API agreed at the later instant. | A checkpoint-only cache is incorrect. Time, expiry and provenance matter. |
| Corrections | Journey-shaped carb create/edit/delete changed COB 60 → 90 → 30; evaluator/API agreed and realtime reflected edit/absence. | Require invalidation/absence recovery. Writes were fixture-persisted shapes, not client-ingress acceptance. |
| Units/history | Under mmol settings, delta retained mg/dL −2 with scaled/display −0.1; evaluator/API agreed. Retro BG differed from current. | Preserve units/formatting policy and historical/on-demand semantics. |
| Future input | Evaluator acquisition included a future row; framed API/realtime excluded it. Current BG still agreed. | Input policy and result equivalence differ. Source inspection explains the sandbox/BG bucket exclusion of future readings. |

Source paths at the pinned application: `lib/data/tenant-projection-evaluator.js`
calls `views.evaluateCycle`; `lib/server/realtime/projection.js` calls
`snapshot.load`/`dataWithRecentStatuses`, without the derived-property phase;
`lib/server/tenant-app/derived-frame.js` runs selected setters without notification
phases. Observers wrapped selected plugin factories, not every computation.
Measured evaluator cycles observed nine setter/six notification-check calls;
API nine/zero; realtime zero/zero. Zero selected realtime setter calls does not
mean no computation: recovery, transformation and frame construction still run.

Controls detected actual BG-setter corruption, checkpoint-only stale reuse,
cross-tenant result substitution, reuse after disabling IOB, a stale frame after
physical deletion, and partial SQL input failure. All passed restoration.
Assertion controls required their intended AssertionError/message; unrelated
API/SQL failures could not count. Full grant revocation, adversarial isolation
and offline client-cache recovery are outside this comparison.

## Observed costs

Values are medians of the three provenance-cell medians across the reseeds.
Protocol calls include transaction/tenant-binding statements. Tick cells have
only two observations each.

| Path | Small wall / CPU ms | History wall / CPU ms | Small / history PG calls |
|---|---:|---:|---:|
| Evaluator acquisition + cycle | 15.410 / 7.609 | 48.446 / 31.115 | 76 / 81 |
| Realtime acquisition + frame | 16.029 / 9.473 | 48.314 / 32.529 | 84 / 89 |
| API acquisition + properties | 10.686 / 8.689 | 21.346 / 17.656 | 76 / 76 |
| Properties HTTP round trip | 13.460 / 9.562 | 22.459 / 18.690 | 76 / 76 |
| Evaluator retained-input tick | 9.259 / 6.101 | 23.027 / 21.364 | 44 / 44 |

**A retained-input tick is not database-free.** Source explanation:
`lib/storage/postgres-projection-read.js` sends retained documents through
`jsonb_to_recordset` to reuse PostgreSQL query semantics. It avoids fresh
clinical-table acquisition but still queries the database. Median history
returned-row JSON bytes were 731,384/evaluator acquisition, 731,506/realtime,
226,222/API and 225,654/tick.

Median history browser-frame JSON was 138,842 bytes; evaluator/API full property
envelopes were 6,570 bytes. Different products are not interchangeable bandwidth
estimates. Full component-return size is recorded separately.

These are instrumented observations on one host. CPU includes observers, JSON
byte counting and the HTTP client where selected. SQL elapsed is a potentially
overlapping sum; row JSON bytes are not protocol traffic. Heap delta is transient;
RSS includes previous trials and is not retained memory per role/tenant. No
production throughput, cadence, replica count or scaling limit follows.

## Recommendation and remaining work

1. **Share a defined immutable current-property result**, initially the six
   exercised families, when tenant, input/projection identity and bounds,
   settings/plugin versions, units/locale and evaluation time/expiry match.
   Keep current authorization and field filtering at consumers. Partial/failed
   acquisition must not silently become a successful current result.
2. **Keep consumer-specific products:** raw browser/socket records, controller
   predictions/provenance, profile ordering, historical/retro calculation and
   endpoint shaping. Alarm suppression, notification intents/retries and delivery
   effects remain separate from reusable read data.
3. **Characterize reuse before adding a service.** ARCH-DERIVED-FRAME should define
   the result interface and compare bounded in-process reuse with current reads.
   The measured query work also justifies projection/acquisition optimization
   research. Preserve query semantics; these results do not justify substituting
   a convenient in-memory query engine.
4. **Distributed publication remains conditional** under MT-RUNTIME-PLAN:
   producer fencing, output durability, freshness/refusal and outage behavior
   require implementation and controls. Deployment/StatefulSet choice supplies
   none of these application guarantees.

Probe selection reused the journey map/builders and pinned open-source browser,
clock, Nightguard, LoopFollow, NightscoutKit, AAPS and Trio consumer sources.
Exact builder SHA256:
`26d104b1584eb2e91b4fb8314701e833aba4b77ab89cb2ab26eb84b0b850fb01`.
Older pinned AAPS/Trio Git objects were inspected rather than substituting their
changed checkouts. Selection is read-derived: no mobile binary, browser execution,
WebSocket fan-out transport, provider/device delivery or latest-client claim.
This f0 cohort does not accept the separate M6 lifecycle prototype.

Parent/child accepted and guarded egress was zero. Independent integration-owner
readback confirmed owned container/volume/child absence, exact restored inventory
and selected baseline metadata preservation. Final capture index SHA256:
`a42f2a826e4a7d7eac223aa08ddeae2519c7f0bde821867683480ae440b381f0`.
The earlier suspended-grant refusal remains immutable: it stopped before native
resources/child creation and is not relabelled a semantic control.
