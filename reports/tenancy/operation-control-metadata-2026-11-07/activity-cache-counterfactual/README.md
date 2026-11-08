# PostgreSQL activity-cache counterfactual — 2026-11-07

**PASS: 9 / 9 primitive groups; runtime physically closed.** This native PostgreSQL
experiment exercised statistics caching and an explicit strict-membership model.
It did not execute the CRM cohort/controller, establish CRM acceptance, apply a
shipping source fix, or identify the original joined-attempt actor.

The observed server version number was **160015**. The run used **5 PostgreSQL
clients**, **3 peak simultaneous clients**, **51 queries** and **0 forbidden egress**.
These are single functional-experiment measurements, not capacity or recovery-time
claims. [summary.json](summary.json) provides portable instrument, source-attribution
and capture hashes. Source attribution is `28c4cb12d80a2bb2c16022ca9adcaa9e1d49f744`,
tree `c65d84ce96d928926c3bbc536a65b85cbbe83c6c`; attributed CRM modules were not executed.

| Counterfactual | Native PostgreSQL observation | Explicit modeled membership check |
|---|---|---|
| Retired actor, refresh omitted | Fresh independent observation confirmed absence; held transaction retained the old tuple | Intended red: stale retired tuple caused unknown refusal |
| Same held client refreshed | Cached retired tuple disappeared | Current empty actor set passed |
| New unregistered actor, refresh omitted | Fresh independent observation confirmed presence; held transaction still returned an empty set | Intended red: the assertion requiring unknown refusal failed |
| Same held client refreshed again | New actor became visible | Strict unknown-actor refusal restored |

Three native sentinel samples retained the same held backend/transaction/isolation
anchor, unchanged own uncommitted writes and the independently committed verifier
row. The verifier continued to see only committed data. The transaction advisory
lock remained held and independent acquisition stayed refused across both refreshes.
Only **explicit rollback** discarded the operator's uncommitted changes and released
the lock; the verifier's committed row survived. Independent server-side release
observation and the final physical resource/process readback passed.

This reproduces the PostgreSQL cache primitive and the modeled omission-red/refresh-green
behavior. It does not prove that caching caused either earlier CRM failure. The
focused c2 actor projection remains separate, and the original joined-attempt actor
remains unattributed. A targeted same-client refresh-before-census implementation
needs its own source controls and coherent joined re-acceptance.

This immutable public projection reads retained evidence only. Raw runtime identities,
roles, backend timestamps, paths, endpoints, credentials and private filenames are
excluded. No tests, services or native experiments were rerun for this projection.
