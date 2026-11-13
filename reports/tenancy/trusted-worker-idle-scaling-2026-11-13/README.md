# Trusted-worker idle scaling — 2026-11-13

**Reproduced: quiet evaluator reconciliation still grows with tenant count.**
The reviewed batch removes repeated unchanged-settings reads and tenant-by-tenant
discovery queries, but its healthy feed still rotates through the roster.
This experiment measures that remaining work in an evaluator subsystem. It does
not measure the full deployment or establish a production capacity.

[Selected measurements and provenance](summary.json) retain the six windows.
The [source record](../trusted-worker-performance-2026-11-13/README.md) owns the
implementation, review, controls and metadata-only native qualification. Every
measurement below is **reproduced**; architectural explanations are labelled
**read-derived**. Raw captures remain unchanged outside Git.

## Boundary and workload

Core `4b13bf8bbfe578416441d7322837ec5aabeba1ea`, paired deployment source
`84accb33c3daccebfdf886300c3ba6c638e003c6`. The deployment binding was not executed
in this experiment. The instrument imports an immutable core archive and its
private dependencies. Independent verification matches all 2,398 tracked source
blobs to that core commit and recomputes all six window projections.

One actual evaluator scheduler uses the shipping clinical component, plugins,
durable replay, trusted metadata reader, operational lifecycle, feed consumer and
tenant statistics reader. Source migrations create the clinical, clock,
lifecycle, settings and operator-policy schemas. Each synthetic tenant has a
24-hour entry/device-status history at five-minute cadence. Enabled plugins are
`bgnow`, `delta`, `direction`, `simplealarms` and `treatmentnotify`.

The subsystem omits realtime, operation windows, delivery consumers, deployment
boot and the shipping feed reader. A synthetic PostgreSQL notification heartbeat
replaces the feed reader; its calls are counted separately. No HTTP or socket
clients run. It cannot establish selected execution-budget, restore, clinical
acceptance or total deployment cost.

Counts run in order 10, 50, 200, with one worker and two nominal 120-second quiet
windows per count. The feed ticks each second and sweeps every 30 seconds.
Settings retention and operational verification use their ten-minute defaults;
the configured clinical slow timer is one second. Timer configuration alone does
not imply a time-only cycle is due. Seeding and startup take different amounts of
time, so input age at window start is not exactly identical across counts.

One disposable PostgreSQL 16.15 container has two CPUs, 1 GiB memory and 512 MiB
data tmpfs. Its ten-connection ceiling has zero reserved superuser slots, a
fixture-specific correction rather than deployment advice. PostgreSQL statement
statistics are installed only in the maintenance database. The native Node
process has a 768 MiB old-heap bound. Ordinary statement logging is off.

## Measured quiet work

Each range contains the two observed windows; it is not a confidence interval.
SQL execution time is PostgreSQL statement execution, not database CPU or request
latency. Counts include the actual sampled window edges; nominal duration and
readout timestamps are preserved in the summary.

| Tenants | Metadata SELECT calls per window | Metadata rows returned per window | Metadata execution ms per window | Full settings reads |
|---:|---:|---:|---:|---:|
| 10 | 40 / 40 | 40 / 40 | 1.749 / 1.779 | 0 / 0 |
| 50 | 120 / 120 | 200 / 200 | 7.815 / 8.647 | 0 / 0 |
| 200 | 120 / 120 | 801 / 801 | 20.828 / 22.567 | 0 / 0 |

Each metadata SELECT has a read-only transaction envelope. Total worker SQL
statements per window are 120 at 10 tenants and 360 at both larger counts.
**Read-derived:** the rotation selects approximately `tenant count / 30` rows
per second. The call count plateaus while more rows are processed in each call.
One batched call therefore does not imply constant database work.

| Tenants | PostgreSQL CPU, percent of one logical core | Evaluator process CPU, same unit |
|---:|---:|---:|
| 10 | 0.2 / 0.1 | 0.2 / 0.2 |
| 50 | 0.6 / 0.3 | 0.3 / 0.3 |
| 200 | 0.3 / 0.3 | 0.6 / 0.5 |

CPU is rounded to 0.1 percentage point. PostgreSQL CPU includes the synthetic
heartbeat and background database work. These readings do not establish a
monotonic database CPU slope. They must not be substituted for SQL execution time
or extrapolated to thousands of deployed tenants.

## Work and control observations

All six windows have zero settings reloads, operational checks, feed refusals and
trusted-reader refusals. No natural time-only evaluation is due within a window;
the earliest due times and zero overdue counts at the ending snapshots are
retained. Zero time-only completions is therefore consistent with this workload,
not evidence for active-alarm deadline acceptance. A separate forced scheduler
tick returns an actual clinical time-only result with a valid checkpoint and
revision. That control is not natural timer demand.

An explicit actual metadata scan proves the SQL counter sees its query and
transaction. Cached settings add zero reads; forcing a settings read adds one.
This is a positive detector calibration, **not** an ablation of the old deployed
settings path. That requested legacy-path comparison remains **UNMEASURED**.
The source batch's independent semantic ablations retain their separate scope.

Ten-minute settings reloads and operational verification do not occur inside
these fresh window pairs. Their amortized cost is unmeasured here. The quiet
subsystem has no writes or viewers; this record supplies no loaded-capacity,
notification delivery or clinical deadline result.

## Retention, failures and next measurement

Retained evidence ID: `trusted-worker-scaling-20261113`, under ignored
`externals/work/trusted-worker-scaling-20261113/`. Its final `SHA256SUMS` digest is
`a381b498dca3052f5a054b6586e7f5d02849ec40b56e12b44774dec7b59b367b`.
Independent checks match all 60 listed artifacts and both completed measurement
containers are confirmed absent by their exact IDs. The core archive verification
and selected-result reduction are independent of the instrument's own summary.

The initial short two-tenant smoke did not span the rotation and cannot support
SQL inference. A ten-tenant startup attempt then failed with PostgreSQL `53300`:
three reserved slots left only seven ordinary connections. Driver and server
logs establish this fixture admission failure. Correcting only the disposable
reserve setting allowed commissioning and the count series to complete. The
failed attempts and the earlier case-sensitive cleanup-classification error are
preserved; they are not relabelled successful measurements.

The deployment's separately owned 500-tenant A–B–B–A comparison remains a distinct
measurement boundary. It must establish actual role/family SQL and CPU, runtime
readiness, write/read/checkpoint convergence and clinical work observations.
This subsystem curve cannot substitute for it. Whole-deployment scaling across
counts remains **UNMEASURED**. Connection-driven realtime and public socket
verification remain separate capabilities.
