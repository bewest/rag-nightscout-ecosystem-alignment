# Reader idle package observations — 2026-11-12

**Reproduced: nine idle windows from a partial A/B/B/A study. No capacity
acceptance or causal pool-gain claim.** Run `reader-idle-ab-20261112-b` captured
three windows for A and three each for two B epochs. Reverse A reached ready but
captured no windows: `IDLE_WINDOW_DEADLINE_RESERVE` preserved collection/cleanup
budget. Its original PARTIAL status and controller failure remain unchanged.

[Selected observations and provenance](summary.json) were independently recomputed
from the closed raw bookends. Originals remain in ignored evidence, identified
below; no logs, per-tenant rows or capture archives are committed here.

## Exact comparison and workload

A is core `9db0ce94f072c8f34aab889f0181afa4269a6758` / binding
`d76ef17878edb610cdeae75aeef9c07f94b60753`; B is core
`debcc2c7a44fb812b342d0e524ff0611045094d1` / binding
`07c536dcae1111adb3017742d54af81e4e68ff0c`. The captured binding runtime tree is
identical. Saved image qualification pins and image IDs are in the summary;
labels alone are not an installed-byte proof. Transport is
`9a21239fc6b295444846ab5ea8c60a2470686071`, Node 24.22.1/npm 11.19.1.
Each epoch has one API, realtime, evaluator, PostgreSQL and Vault instance.
All epochs share one host boot/Docker daemon: 16 logical CPUs, Xeon Platinum 8280
@ 2.70 GHz. This compares source packages, not an isolated retained-reader change.

There are 1,000 synthetic tenants. The effective setup is the shipping primer,
which intends one SGV per tenant, timestamped separately, plus authorization,
ownership and session setup. The same primer bytes are captured for both arms.
Requested seed 42/history 24/HOT 10 metadata does **not** establish execution of a
24-hour generator or HOT client workload. Stored primer counts, clinical-data
age, ready age and matched clinical demand remain UNMEASURED. All nine windows
schedule zero client HTTP requests and sockets; ordinary logging is OFF.

## CPU with observed completed work

Mean cores use each role's actual cgroup read brackets, not nominal 120 seconds.
If reads occupy intervals [a0,a1] and [b0,b1], elapsed is bounded by b0−a1 and
b1−a0; counter delta divided by these bounds yields the displayed range.
Bounds below round outward to 0.001. User/system are whole PostgreSQL-container
CPU components, never SQL-family CPU. Summary includes evaluator/API/realtime
user/system ranges and per-role elapsed bounds.

| Epoch/arm/window | PG total | PG user | PG system | Evaluator total | TIME completions |
|---|---:|---:|---:|---:|---:|
| 1/A/1 | 7.440–7.460 | 3.317–3.326 | 4.123–4.135 | 1.361–1.365 | 211 |
| 1/A/2 | 7.250–7.267 | 3.246–3.254 | 4.004–4.013 | 1.337–1.341 | 209 |
| 1/A/3 | 5.966–5.978 | 2.713–2.719 | 3.252–3.259 | 1.065–1.068 | 209 |
| 2/B/1 | 4.242–4.250 | 1.929–1.934 | 2.312–2.317 | 0.840–0.843 | 208 |
| 2/B/2 | 4.275–4.284 | 1.954–1.958 | 2.321–2.326 | 0.836–0.838 | 208 |
| 2/B/3 | 4.234–4.243 | 1.947–1.952 | 2.287–2.292 | 0.814–0.817 | 209 |
| 3/B/1 | 4.267–4.276 | 1.955–1.959 | 2.312–2.317 | 0.840–0.842 | 209 |
| 3/B/2 | 4.282–4.291 | 1.976–1.981 | 2.305–2.310 | 0.847–0.850 | 208 |
| 3/B/3 | 4.238–4.247 | 1.954–1.958 | 2.284–2.289 | 0.827–0.829 | 210 |

TIME totals are 629/625/627 across the three measured epochs. At both ends of
every window all 1,000 tenants are ready/admitted, total completed acquisitions
remain 1,000, and failed completions remain 0. Runtime and each tenant's nested
`progress.generation` stay stable within each epoch; counters never decrease.
`bodyCycles` in JSON counts legacy entered bodies, not successful completions.
These are sampled completed-work observations, not continuous liveness or
identical clinical-cycle/demand proof.

All third-window delivery states are idle at both ends; TIME deltas are 209/209/210.
The repeated B CPU band remains lower than the observed A band, with no collapse
of credited TIME work. Early A also settles substantially. Missing reverse-A
windows, differing timer populations, unknown ages/demand and host/cache/order
effects prevent a full ABBA or causal speedup conclusion. No SLO is inferred.

## Liveness and attribution limits

Early B `idle1-before` bookends contain 43 and 44
`EVALUATOR_NOT_EVALUATED_WITHIN_BOUND` alerts, at reported evaluation ages
60,027–62,960 ms and 60,066–63,001 ms respectively, despite ready=true and failed=0.
The other 16 bookends, including every settled third-window bookend, have none.
Zero failed completions therefore does not mean zero liveness alerts. Source
`evaluator-runtime.js:564–565` at B confirms this age is confirmation/creation age,
not execution or request latency. These alerts alone do not establish missed
clinical work. Two settled snapshots retain past dueAt values while that work
is already running; they are not measured queue lag or deadline failure.

Official database-session rates remain null/UNMEASURED: both stats_reset values
are null, with captured reason `COUNTER_IDENTITY_RESET_OR_NULL`. No raw counter
growth is promoted to qualified QPS/churn. All three separate logged diagnostics
remain UNMEASURED with `IDLE_DIAGNOSTIC_PEER_MISMATCH`; no statement/service/family
attribution or SQL-to-CPU substitution is made. Fourth diagnostic was not run.

## Closure and retained provenance

All four epoch finalizations have no failure entries and exact-owned cleanup
verified. Independent saved proof reports 0 owned droplets/firewalls/tags and
removal of 2 temporary keys. Controller child/wrapper exit 1 is retained through
an explicitly retrospective tool-completion transcription, not an independent
contemporaneous OS receipt. Watchdog process exit remains UNMEASURED; its saved
cleanup is verified. No result was inferred from another process's exit.

Earlier run `reader-idle-ab-20261112-a` remains a closed setup failure with
`IDLE_OWNED_COMMAND_FAILED`, zero windows and UNMEASURED idle/tenant outcomes;
its independent cleanup is also verified. It is not relabelled by this record.

Retained evidence ID: `perf-cloud-reader-20261112/reader-idle-ab-20261112-b`.
Original archive 33,061,673 bytes, SHA256
`f7c83354aada4f2aa8e621c8040a142c364934f0238e2134e2a9ad759fa4d5bb`.
Summary binds the primary result, input manifest, 18 raw-bookend hashes, independent
cleanup and retrospective process witness. No new runtime, SQL, provider call,
source acceptance, clinical acceptance or measurement was executed for this record.
