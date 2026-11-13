# Independent discovery observations: 500 / 750 / 1000

**Descriptive points; capacity acceptance NOT_GRANTED.** These are three separate
closed runs, not a matched scaling curve. All used reference core `9db0ce94…`,
deployment `d76ef178…`, image `293a5c53…`, one API/RT/evaluator and Vault server.
They do not measure the later retained-reader source. Full pins, instruments,
strict findings, missing fields and original hashes are in [summary](summary.json).

| Run / tenants | Original status | k6 requests | Failed requests | Dropped iterations | Probe frames observed/expected |
|---|---|---:|---:|---:|---:|
| A / 500 | PARTIAL | 6095 | 0 | 9 | 232 / 232 |
| C / 750 | MEASURED | 8389 | 6569 | 717 | 134 / 280 |
| B / 1000 | PARTIAL | 11184 | 9174 | 921 | 122 / 290 |

HTTP totals include **k6 setup JWT exchanges**, not socket/probe HTTP. They are
not capacity throughput. Rates include setup/runtime overhead; neither requests
nor SQL calls are divided by the nominal load duration. Probe frame denominators
are recorded expectations, not independently proved stored-write counts.

A's count query never ran; counts remain UNMEASURED. Its fingerprint instrument
failed as documented [here](../m7-discovery-fingerprint-2026-11-12/README.md).
B's legacy probe uncertainty remains UNKNOWN; its original hard refusal stays.
[Observer repairs](../m7-discovery-observer-repairs-2026-11-12/README.md) owns that
mechanism. C's v2 ledger closed with no pending attempts and GREEN count bounds.
MEASURED means observations were collected: C still has idle UNMEASURED, load
ERROR/FAIL and unavailable recovery baseline, with incomplete frame observation.
Count bounds override none of those findings. Missing counters remain null.
Absent codes stay null; B/C error labels appear separately as derived categories.

All hosts had 16 logical cores, but different Xeon Platinum CPUs: A8358, C8168,
B8280. Instruments also differ. The summary derives SQL request-bracket rate
bounds with the pinned adapter's `sql_counter_rate_bounds`, outward-rounded;
these are aggregate statement calls, not exact QPS, application throughput or
role CPU. Approximate cgroup core-equivalents use matching container bookends;
role reads are not simultaneous; unselected and host-side probe/load-generator
costs are excluded.
No causal performance or hardware-normalized claim follows.

Each retained cleanup audit verified controller/watchdog cleanup, zero remaining
owned droplets/firewalls/tags and removal of two original temporary keys.
Raw evidence stays outside Git under each run ID and matching cleanup-observer
ID. This whitelist projection was derived at alignment `c098d68d…`; no test,
query, resource action or new campaign was run. Original measurements are immutable.
