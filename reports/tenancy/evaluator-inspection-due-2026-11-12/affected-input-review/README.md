# Due-state export: affected paired inputs review

Captured 2026-11-12. Independent scope: read-derived source/input review plus a
pure actual-source fractional-deadline discriminator. No peer edits, live-stack
queries, UDS/PG tests, resources, build or new qualification state were started.
This does not replace the source owner's actual private-module/native proof.

Confirmed clean source `47b43b6246ce7f94f1f1f0d01830495a78b28add`, history
`cd4629159809fb3cffbc6f57626f98f3ffdbdda7` →
`acae7b630cc64d8bb53e1973c2c84491ed01c69a` → `47b43b6`.
Exactly four changed paths against cd462: private inspection DTO, its JSON schema,
and the existing inspection/partition tests. No evaluator runtime, due calculator,
operation window, producer, scheduling policy, clinical/data/authority storage,
grants, dependencies or build rules changed. No remaining blocking read-derived
mismatch identified in this corrected narrow delta.

## Preserving the source's existing deadline domain

The runtime already exposes dueAt/dueReason in health; the previous private DTO
omitted them. The export adds observations, not instructions to evaluate.
The first draft required integer deadlines. Existing tenant environment accepts
finite numeric pump.warnClock (environment.js typed extended setting), while
`lib/data/evaluator-due.js` computes pump-clock-warn from that minute value.
For synthetic `warnClock=1/7`, at 1700000000000, actual nextDue produces
1700000008572.4285. Existing runtime arm accepts finite deadlines, so narrowing
the observational response to integers refused a source-valid scheduler value.

The [same preservation invariant](captures/fractional-due-reproducer.cjs) runs
actual nextDue and actual DTO: [original acae](captures/original-acae.json) exits
one with inspection refusal, [corrected 47b](captures/corrected-47b.json) exits
zero preserving exactly that fractional value and reason. The control uses
synthetic component inputs; it is not a public settings/API or clinical test.
No value is rounded and no scheduling/state policy is modified. Corrected DTO
and schema both accept finite nonnegative number/null, with no integer/MAX_SAFE
restriction, and refuse missing or malformed observations. Reasons remain typed
ASCII at most 128 characters. Null due time requires null reason.

## Exact input and compatibility consequences

| Input | Effect of this delta |
|---|---|
| Runtime image | lib is a committed build input. DTO/schema are loaded in-process; new exact core image required. Old image454d cannot expose these bytes via honest labels or source overlay. |
| Deployment binding | No new topology, env setting, PG/Vault capability, schema or placement input. Coordinator must refresh SOURCE/delta metadata as required by the supported overlay tooling, then pin the exact resulting pair once. |
| Private client/schema | Preview retains private module version two. Older strict-v2 clients reject added response fields; no mixed-source compatibility claim. Use exact compatible source/client/schema with new image. Normal public APIs are untouched. |
| Selected inspection cost | Existing explicit <=128 selector, selected health lookup and empty summary paths remain. Two row fields add bounded metadata; no roster iteration or work trigger was introduced in DTO diff. This is read-derived; owner retains counted/native controls. |
| Host shipping instrument | Existing e91 stock/restore/settings/clinical/controlled-move fixture behavior and mutations need no changes for these extra private response fields. Their private probe executes from the new source/image. |
| Collector receipts | Raw source views gain due fields, but compact progress receipts previously omitted them. Join the owner's explicit versioned passthrough before qualification so evidence retains both due values, without silently changing progress policy. |

## Shortest honest next qualification boundary

1. Finish the companion receipt passthrough and independent source review, then
   coordinator joins/pins one coherent new core/binding/instrument tuple.
2. Build one exact image with verified new source/deployment labels. Use genuinely
   fresh owned state/nonce with the same explicit 2API/2RT/shards2/3EV desired2-to-3,
   Vault SERVER, diagnostics OFF topology; retain prior states/images/proofs.
3. Reuse unchanged e91 ordered startup and focused stock/restore with B traffic,
   settings controls, one actual clinical2-to-3 sequence and controlled realtime
   move only after clinical PASS. The previously successful sequence's actual
   shipping test time was about 26 seconds, excluding preparation/startup.
4. Release one stable bounded read-only collector window only after mutations,
   using compatible client and due-preserving receipt instrument. A quiet or
   insufficient-work result stays UNMEASURED; do not manufacture a due opportunity,
   extend cadence/deadlines or infer a scheduler defect from legacy freshness.
5. Coordinator owns the single coherent full/browser/enabled-corpus/capacity
   acceptance boundary. No additional leaf-wide campaign is justified by this
   observation-only diff.

The old runtime cd462/0f8749/image454d scripted PASS remains exact-scoped historical
evidence. It does not qualify the new DTO or reveal the original B due state.
All new actual-image/progress conclusions await the coordinator-authorized run.
Capture hashes: [sha256.json](sha256.json).
