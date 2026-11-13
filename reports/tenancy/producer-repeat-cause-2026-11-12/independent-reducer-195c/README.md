# Independent transient-ineligibility repeat-clock cause

Reproduced2026-11-12 on clean core195c932293f3abc648da8fbe4356bf7360acd002,
actual producer-state reducer and shipping private notifications, synthetic only.
No production source, preserved stack, membership or authority policy changed.
This is deterministic in-memory causal evidence, not native-store reproduction.
Runtime owner separately owns the actual durable warm-barrier discriminator and
repair. The existing real clinical acceptance failure remains failed pending it.

Producer-state blob b9a06f9fc1bfb6ca09f7a965d99e2b84cfb986f8,
file SHA77300e2eaa4d47adbb5bb0580779758cd75059e3246a2be0d962c66a7a1efc60.
Caller producer.js blob bcb6845ac42625eac71827679325f2f235534e7a.
Executed final script SHA a37025c41eec895ab58fb09caba859c3d17b756025ff0c4583ac949136b70324;
result SHA7be5a225d57795085a3890e78b5f86f93f22a835bfeb5a775a6add93e1567681.
An owned detached195c source archive used this lane's owned exact-lock dependencies.

## Mechanism and meaningful control

Armed output at t0 sets repeatAt=t0+60000. At t0+1000 the same configuration is
transiently ineligible. Output, alarm-state digest and normal effect origin stay
identical, but repeatAt disappears. Identical content/configuration/checkpoint
recovered at t0+4438 is not fresh, yet satisfies at >= (prior.repeatAt ??0).
It emits the exact same effectIdentity under a NEW origin derived from
`['producer-transition-v2',['repeat',next,null],0]`, then sets deadline t0+64438.

The caller turns missing/nonmatching current output into eligible:false while
retaining authoritative configuration; the reducer's `!armed(cycle)` clock-drop
therefore covers unavailable output as well as actual normality. This is not an
ownership-policy or cache explanation. The producer's ordinary state lock and
atomic intent commit do not restore the lost deadline.

The unchanged-output invariant is RED on that actual source sequence:
UNCHANGED_OUTPUT_MUST_WAIT_FOR_ORIGINAL_REPEAT_DEADLINE. A single-field causal
control preserves the original repeatAt before identical recovery; the SAME
source reducer/invariant is GREEN, retaining original effect origin and deadline.
This modifies only test-owned previous state, not product code. It establishes
the lost-clock dependency, not the full eventual repair contract.

Nine actual reducer scenarios, with assertions and complete results:

- Same content without unavailable gap: original origin/deadline retained.
- Transient ineligible gap: deadline disappears and identical effect gets new origin.
- Original deadline preserved: no early repeated effect.
- Genuine due boundary59999/60000/60001: no early repeat, one at60000, no replay at60001.
- Gap followed by genuine due output with original deadline: repeat still occurs.
- Changed configuration: explicit existing reset path/new identity and origin.
- Known normal empty clinical output: clear, stable clear origin across empty polls,
  repeat clock absent.
- Normal then real alarm: legitimate fresh origin, unaffected by original repeat slot.
- ACK while ineligible: actual control clear; identical recovery preserves that exact
  clear origin and emits no normal alarm during the active ACK.

The script computes and asserts the exact repeat-null cause origin. The runtime
owner separately published native matching-origin metadata at its retained
clinical-origin-cause-match.json, SHA2888e3c578271ed6001a03e83d8ee1ae376fbf4b25f21f4e008f770b7d0aa9ef
(two accepted-request matches). This lane read that metadata but did not produce
its database observation or independently rerun native state. Native acceptance,
current-authority/late-effect/phase/restore protection and the eventual patch
remain runtime-owner/root criteria.

Reproduce with a NEW clean owned exact195c archive and owned same-lock dependencies:

```bash
M7_PRODUCER_CORE=/absolute/owned/core195c \
M7_PRODUCER_OUTPUT="$PWD/result.json" node reducer.cjs
node invariant.cjs transientIneligible       # expected RED/exit1
node invariant.cjs preservedDeadlineControl # expected GREEN/exit0
```

Shipping notification logging precedes the JSON on stdout; result.json is written
directly, not parsed from that mixed stream. All nine reducer assertions pass;
control-results.json records expected red/green exits. Capture manifest pins raw
and public bytes; only a scratch path prefix in the red error stack is normalized.
No secrets, actual user data, live stack queries, new service resources, capacity,
cloud or broad campaign were involved. Root owns failure/BF records and causal
integration; production edits remain exclusively with the runtime owner.
