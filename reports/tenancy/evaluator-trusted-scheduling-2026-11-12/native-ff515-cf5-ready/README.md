# Final ready-pair strict TIME witness

Reproduced 2026-11-12: the exactly-once post-evaluator-handoff, pre-realtime-move
private-listener observation passes the CURRENT strict v2 successful TIME checker.
This is a short native functional witness, not capacity, pilot idle, restart,
clinical-output or continuous deadline acceptance.

Core ff5156b984424f1ef34bcef22d5bfa0071354cfa; deployment
cf5bda3f2d189bac5d60269df5644759c40db9e1; actual image
sha256:399dea76f971451143b65c02be37c99e76d240d607d1f5b45a35fd564d7e6fd2.
Instrument 8ae6f4a3729548de0c88cc0ee5b3c0aede9aba61, content
52c76f7500312bc3ce8006f3783444b04489bdf53cd1f764417f77cf8333ba1d /37 files.
Nonce 0dc3af55-99df-4fd9-8b1b-8771f68be6f1 and owned-marker SHA
2f915e3eb1886bf784da1e97bd25f4f17a24130a47fd83cf32335ab9f3908b2d
were checked against the fresh ready project. Current post-clinical CIDs,
StartedAt, image and role labels were selected and checked before/after collection;
all container/runtime identities and ownership generations remained stable.

RT explicitly released a stable no-write window after its clinical2→3 sequence,
before its RT move. This lane made no writes, work triggers, public traffic,
configuration/membership changes, retries, extensions or lifecycle operations.
Three snapshots 10 s apart took 21.411618547979742 s, using 9 bounded RPCs and
20092 response bytes. Parallel round collection wall time summed to
1.3783426014706492 s (collector overhead, not CPU or a capacity measurement).
All 2 synthetic IDs on all 3 evaluator instances are retained in every snapshot:
18 rows total, including 12 foreign observations. Prior foreign counters may be
nonzero from earlier ownership; every foreign counter stayed unchanged.

| Owner | Acquisitions | Successful TIME | Legacy cycles | Failures | Generation |
|---|---|---|---|---|---|
| A/evaluator-2 |1→1|227→247 (+20)|228→248|0→0|11 stable|
| B/evaluator |1→1|227→246 (+19)|228→247|0→0|15 stable|

Both owners were admitted/ready with no code/alert and captured reason
slow:alarm-message. Actual dueAt values, helper sample times and UTC read brackets
are preserved, without inferring an opportunity/deadline SLO from sparse samples.
The result has 39 successful time completions, minimum owner delta19 and failure
delta0. No inspection-induced-work claim is inferred from this active observation;
the source/recording controls establish the read-only inspection boundary.

The [unchanged raw wrapper](strict-time/observation.private.json) SHA is
d27bd7e8f0668870cd219c03d8c44c9229d94c295a01d496b7090d0ddc343ad6;
its deterministic gzip SHA is
46c820c9f392cd3cf4a2ae2a371243719f5453181c6f4cc5ec9a983a39aa03e7.
The receipt uses this wrapper and proofPointer `/proof`; exact coordinator pins are
in [native-time-expectation.json](native-time-expectation.json). Its artifact path
is relative to the strict-time evidence directory. Source-only gate recomputation
returns the exact captured result.

Nine offline mutations of the actual captured rows/wrapper refuse a stalled owner,
hidden failure, foreign work, missing foreign coverage, runtime reset, generation
reset, invalid due scalar, wrong image and historical strict-v1 downgrade.
Restoration passes after each mutation; [controls.json](controls.json) retains exact
codes. The stalled control is a captured-row mutation, not a stopped live worker.
Recording-only driver controls additionally cover zero-work refusal, exact-once and
wrong nonce; they are not native captures. No repeated native observation ran.

Recompute with an owned Git archive of the exact instrument commit (including
`tools/mt-bench/m7-joined` and `tools/queue/gates/m7_joined_receipt.py`):

```bash
PYTHONDONTWRITEBYTECODE=1 python3 controls.py "$INSTRUMENT_ARCHIVE" strict-time/observation.private.json
```

Private originals remain 0700/files0600. Published captures contain synthetic IDs
and bounded operational metadata only, no credential/config contents. Historical
quiet and failed captures remain unchanged. Root owns final full acceptance,
paired qualification and capacity decisions; RT owns subsequent move/export.
