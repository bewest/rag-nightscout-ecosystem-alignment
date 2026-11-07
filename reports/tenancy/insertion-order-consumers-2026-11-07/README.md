# Insertion order: actual server consumer proof

*Reproduced synthetic PostgreSQL 16.15/server-read evidence, 2026-11-07.
Unchanged application `f0fac99a2fccee259c9a76eba0123058bf288d96`, tree
`09dd7baf52d51f2725e7cac732fabd3f8280b482`.
[Instrument](instrument.cjs), [observations](observations.json),
[closure](closure.json). This is not HTTP, Android/iOS binary or full M6 execution.*

## Measured distinction

The real `lib/server/storage-reads.findOne` and profile factory/socket natural
order port read a native PostgreSQL profile table built from the exact selected
socket-order catalogue. Two profiles deliberately share a legacy lookup key but
have different `_id` and full profile values. The actual entries factory and
`storage-reads.list` supply an independently date-sorted comparison.

| Phase | Actual consumer result |
|---|---|
| Baseline | First-arriving profile `z-first` is selected over `a-second`; entries sort by descending date. |
| Renumber preserving relative order | Profile ordinals 1,2 become 100,200; the selected full public document remains exactly equal. Entries remain exactly equal. |
| Relative-order break | Profile ordinals reverse to 200,100; first match selects `a-second` and a different full store. Original-document equivalence fails at its intended assertion. Date-sorted entries remain exactly equal. |
| Fresh restoration | Original first profile and date-sorted entries results return exactly; no public returned document includes insertion_ordinal. |

The instrument changes only physical ordinal values and preserves synthetic
documents. These observations refute treating exact ordinal numbers as an
observed client requirement, while confirming a specific first-match ordering
dependency. They do not establish harm to a deployed client or sensitivity of
ordinary explicitly sorted dashboard/history reads.

## Existing client and server source trace (read-derived)

Released AndroidAPS NSClient v1 tag `3.4.2.3`, source commit
`05a3433598ac49a3ecafcbd218fc5c1fc39c8719`, uploads changed profiles via
[DataSyncSelectorV1.kt lines 786–803](https://github.com/nightscout/AndroidAPS/blob/05a3433598ac49a3ecafcbd218fc5c1fc39c8719/plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/DataSyncSelectorV1.kt#L786).
Its [NSAddAck.kt lines 31–36](https://github.com/nightscout/AndroidAPS/blob/05a3433598ac49a3ecafcbd218fc5c1fc39c8719/plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/acks/NSAddAck.kt#L31)
consumes the first returned record's `_id`. This is a released-client source path,
not a statement about the current AndroidAPS development upload implementation.

On f0, `lib/storage/write-intent.js:2676-2681` constructs the profile
NSCLIENT_ID/startDate match; `:2905` reads the first full matching profile;
`:2918` retains that record's `_id`; `:2922/:2927` updates/replaces it. Thus a
relative-order change can select a different record in a multiple-match resend.
No numeric ordinal is consumed by this client path. The native proof measures
the actual server read at that boundary; it does not run the upload/ACK journey.

Other read-derived boundaries: socket treatment/devicestatus first matching
records, raw unsorted food results and equal-position quickpick ties can depend
on ordering. Public entries/treatments/profile routes have explicit date/order
rules; exact unique-ID edits do not select among duplicate matches. No census
or this small proof supports an all-client claim.

## Source, controls and teardown

Frozen instrument SHA256:
`aa31cabd8268c3fa5a9e73443ef1a9a4054b7d5d959aefed430d05579ff78ecd`.
The actual reversed-order result is the authored semantic failure; restored
normal source/data passes afterward. Parent/frozen source hashes and child
exit 0 are retained in closure. Root independently verifies the frozen hashes
and current absence of the exact owned container/volume. Parent before/after
complete container/volume inventory equality is its own observation. No shared
resources, application source, production import guard or sequence default changed.

Private environment capabilities and finite parent capture remain local at
`externals/work/m6-consumer-order-feasibility-20261107/`. Reproduction needs the
exact archived app/dependencies, separate owned disposable PostgreSQL connections
and the instrument's private APP_SOURCE/PROBE_* environment; never use a shared
or real database. There is no timing, provider or lifecycle-admission claim.
