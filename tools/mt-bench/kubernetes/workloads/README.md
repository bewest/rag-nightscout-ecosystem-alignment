# Bounded Kubernetes workload inputs

Living contributor-facing instrument guide. Definitions are **read-derived** from
the existing M7 generator and frozen C2 core
`6463f24eea02a9e4355d988b1353f238f21d3609`; local generator/retained-data controls
are **reproduced** on 2026-11-17 Pacific. Kubernetes operation, production traffic
and capacity admission are UNMEASURED here. The
[production guide](../../../../docs/30-design/tenancy/production-critical-path.md#workload-and-resource-envelope)
owns the workload model. Adopted
[performance policy](../../../../releases/cgm-remote-monitor-16.0.0/decisions.md#performance-signals-not-gates)
and [capacity policy](../../../../releases/cgm-remote-monitor-16.0.0/decisions.md#m7-capacity-gate)
retain their existing homes.

These files supply inputs and independent reductions to the
[existing Kubernetes adapter](../README.md). They start no Kubernetes actor,
reserve no resource and add no capacity gate.

## Source mapping and scope

| Source anchor | Supported meaning |
|---|---|
| `tools/mt-bench/capacity/k6/workload.js:47` (`ALL_SHAPES`), adapted by `tools/mt-bench/m7-joined/workload.py:7` | Seven shapes: one entries, one devicestatus and one v3 treatment write; five latest-SGV, one devicestatus, one treatments and one status read per weighted cycle. Weights are assumptions taken from the existing synthetic client-shaped mix, not observed production frequencies. |
| C2 `lib/tenant-connector/config.js:40`, `runtime.js:73` | Connector defaults: five-minute successful-poll cadence, 15-second scheduling cycle, 150-second retry delay. Poll eligibility and records actually returned are distinct from a write per tenant every poll. These profiles do not start connectors. |
| C2 `lib/client/index.js:1165` and `1166`; original `capacity/probe.js:61` | Stock display and alarm namespaces use Socket.IO polling transport. A connected stock viewer is not one REST request per clock tick. The M7 probe opens the data namespace; it does not prove the separate alarm-namespace journey. |
| `m7-joined/workload.py:27` and `kubernetes/execute.py:223` | Explicit offeredRps rescales the selected mix; adapter fixes HOT_FACTOR=1, ACCEL=1 and all seven shapes. Integer rate bounds are 1–100 requests/s. The override, not ACCEL alone, defines actual cadence. |
| `m7-joined/viewer_plan.py:10`, `capacity/probe.js:8`, `m7-joined/probe.py:125` | logicalPollingClients is the total number of Socket.IO viewers assigned in roster order. Probe writes have their own global round-robin cadence. Ordinary REST reads are driven by k6 independently of viewers. |
| C2 `lib/server/serve/evaluator-consumers.js:78`, `:124`, `:197` | Pending/refused/repeating clinical work, persisted attempts and due intents require separate observations. An idle interval with no known opportunity proves no timer progress. |

For the implemented equal-weight roster, let `N` be ordinary eligible tenants,
`s_j` the shape weight and `R` the requested ordinary REST rate. M7 computes
`C_ms = round(1000 × N × sum(s_j) / R)` and issues shape `j` at nominal rate
`s_j × N × 1000 / C_ms`. Here `sum(s_j)=11`, write weight is 3 and read weight is
8. Ordinary per-tenant ingestion cadence is `C_ms`, even with `ACCEL=1`.
The extra probe rate is `1000 / probeEveryMs` while its window is open.
JWT setup, probe priming, Socket.IO HTTP transport and observer SQL are additional
work. Startup and finite scheduling boundaries can add one iteration per shape;
`R × duration` is a nominal integral, never a substitute for issued counters/CSV.

## Concrete proposed profiles

The three original aggregate profiles retain two provisioned/ordinary-eligible synthetic tenants and four
Socket.IO viewers. They seed no additional history, synthesize no alarm or reconnect
flood, and request no restart. Existing provisioner history and retention must be
read back; they are not assumed empty or production-sized.

| Input | Ordinary window / rate | Ordinary cycle | Probe cadence | Use |
|---|---|---|---|---|
| [small.json](small.json) | 22 s / 1 request/s | 22 s per tenant | 300 s globally | Small-path diagnostic and native generator shape control |
| [representative-mix.json](representative-mix.json) | 330 s / 1 request/s | 22 s per tenant | 300 s globally | Selected request mix across a nominal five-minute wall-clock interval; ordinary ingestion remains accelerated |
| [stress-discovery.json](stress-discovery.json) | 22 s / 10 requests/s | 2.2 s per tenant | 1 s globally | Short overload/discovery point, including explicitly accelerated clinical probes |

The first two offer about 0.273 ordinary writes/s and 0.727 ordinary reads/s;
stress offers about 2.727 and 7.273 respectively (**read-derived**). Even the
minimum integer rate accelerates a two-tenant mix by about 13.636. The aggregate selector keeps those original accelerated inputs.
Do not describe representative-mix as realistic cadence. The existing released
M7 `realistic-v1` selector supplies a separate per-shape cadence through the same
adapter; it does not round a fractional aggregate rate to an integer.

| Realistic profile | Eligible tenants / stock viewers | Nominal ordinary REST/s | Window |
|---|---:|---:|---:|
| [realistic-500.json](realistic-500.json) | 500 / 50 | 6.9444 | 1,800 s |
| [realistic-1000.json](realistic-1000.json) | 1,000 / 100 | 13.8889 | 1,800 s |
| [realistic-3000.json](realistic-3000.json) | 3,000 / 300 | 41.6667 | 1,800 s |

These are read-derived nominal rates, checked against actual generated k6
scenario options. Sensor and device-status writes and SGV reads recur every
300 seconds per tenant, treatment writes every 1,800 seconds, and other reads
every 900 seconds. For shape weight `s_j` and cadence `tau_j_ms`, the released
generator sets `timeUnit = round(tau_j_ms × s_j / workloadScale)` and
`rate = N × s_j`. Scale 1 preserves cadence; scale 2 is a uniform rate bracket.
Select a positive finite scale explicitly, independent of the roster and viewer
total. Every rounded scenario time unit must remain representable by k6.
All seven shapes remain required. An `offeredRps` field alongside realistic-v1,
nonuniform hot weighting or conflicting ambient selector refuses.

The realistic examples retain the exact public reference source/binding tuple
from the released scale bridge, not a new candidate selection or source PASS.
A successor needs explicitly revised profile pins and its own commissioning
packet. Binding rejects a source mismatch; it never silently repins. Their
2.1 CPU cluster limit is an unadmitted proposal from that bridge. Actual resource
fit at each population remains UNMEASURED. Each requests a 2,400-second work
window plus 600 seconds cleanup. A shorter diagnostic may declare a shorter
ordinary window and phase budget, retaining all actual observation limits.
The adapter supports 1..86,400 seconds within the real deadline and the stock
probe ledger's attempt bound; it does not extend an entered grant.

The ordinary viewer opens at a configured rate and prefers WebSocket.
`workload.viewerSetup` takes `opensPerSecond`, `stallSeconds`,
`transport` (`websocket-first` or `polling`) and `scenario` (`ordinary` or
`simultaneous-reconnect`). The reconnect scenario first primes the ramped cohort,
then reconnects it together and requires fresh frames. Commission and recovery
use the stock polling transport. The probe records effective settings and
actual transport counts for each connection phase.

The viewer planner assigns quotient/remainder counts in roster order, including
zero-viewer tenants. Storage checks cover all roster writers. Clinical witnesses
remain scoped to the independent probe writes; only assigned viewers require
client observations. Zero viewers records client delivery NOT_EXERCISED.
The bounded raw frame recorder refuses overflow; a longer or larger run does
not silently turn lost frame evidence into a pass.

Workload profiles carry no resource envelope. Kubernetes requests come from the
render; the scheduler decides placement (decisions `generous-run-resources`,
`requests-typical-scheduler-decides`).

Small/stress reserve a 900-second work window and representative-mix 1,200
seconds, followed by 600 seconds for exact owned cleanup. These bounds include
setup/prime, load and observation/drain; unchanged source timeouts can consume
the available window. The work deadline remains authoritative if they overrun.
No entry is seeded toward 10,000 tenants by these files.

```bash
python3 -B tools/mt-bench/kubernetes/workloads/profile.py describe \
  tools/mt-bench/kubernetes/workloads/small.json
python3 -B tools/mt-bench/kubernetes/workloads/profile.py dry \
  tools/mt-bench/kubernetes/workloads/small.json /absolute/owned/artifacts/dry01
python3 -B tools/mt-bench/kubernetes/workloads/profile.py bind \
  tools/mt-bench/kubernetes/workloads/small.json \
  /absolute/private/fresh-config.json /absolute/owned/profile-config.json
```

`bind` replaces the selected workload fields after checking the pinned
core/image-deployment/binding tuple, roster, planned native envelope and finite
fresh deadlines. A changed source requires explicitly revised profile pins and
its own focused qualification. Binding a realistic profile replaces the old
aggregate selector, rather than retaining an accidental override. Existing successor `pointId` is preserved to keep
markers distinct across reused fixtures; a conflicting hotFactor or unknown
workload field refuses rather than silently changing the workload. Pass its output, the exact
render and inventory to the existing adapter's `prepare`. That adapter owns
source/content hashes, actual namespace/Pod UIDs, native tools/scope and cleanup.
The runtime owner should execute the tiny point only after receiving its finite
allocation from commissioning. Frozen C2 source acceptance does not qualify a
different binding/instrument, or a changed pending source tuple.

## Observation and completion

| Work stage | Existing evidence and what it closes |
|---|---|
| Configured/offered | Profile plus actual environment, roster, generated workload hash, scenario plan, source/image/binding/instrument and time window. Nominal rate is not issued work. |
| Issued/responded | Per-shape `m7_http_attempts`, completed/category/status counters and independent scenario counters/CSV. JWT setup stays separate. Missing counters are UNMEASURED. |
| Accepted/refused/uncertain | Ordinary write outcomes and independent version-2 probe ledger. A timeout or unexpected mutation response cannot establish that the write did not commit; never retry to make the count match. |
| Stored | Original `discovery_counts.observe`: marker-scoped per-tenant/per-collection counts bounded by accepted/uncertain writes. A missing accepted row fails `M7_DISCOVERY_WRONG_DATA`. |
| Clinically complete | Original captured clinical witnesses, their distinct accepted-write coverage, and optional rerun of the T raw-SQL/typed-output oracle. This reducer checks recorded witness coverage; it does not repeat semantic clinical proof. All-writer completion requires the source-bound fixed input/intake/restore fence and complete backlog observations. |
| Delivered | Original `viewer_plan.check`: exact roster/viewer assignment and accepted-probe frame counts. Check authority/isolation independently through T access/raw-frame oracles. ConnectedAtEnd alone cannot prove delivery. |

```bash
python3 -B tools/mt-bench/kubernetes/workloads/reduce.py \
  /absolute/owned/run/load /absolute/owned/reduction01
# Retained M7 fixture instead of a T config:
python3 -B tools/mt-bench/kubernetes/workloads/reduce.py \
  /absolute/retained/fixture/load /absolute/owned/reduction02 \
  --fixture /absolute/retained/fixture
python3 -B -m unittest discover -s tools/mt-bench/kubernetes/workloads -p 'test_*.py' -v
```

T stores configuration as `run.json`; the reducer reads that exact contract.
Output keeps source/placement/actor identity, independent HTTP and stored results,
selected clinical coverage, delivered frames, available stage latency/freshness
and 10-second scheduling-count curves. Every retained input is checksummed.
It does not mutate originals. A lost witness fails coverage even if the recorded
top-level clinical verdict says PASS; dropped iterations are a figure by
operation and erase no accepted/stored/selected-clinical observation. That is
coverage accounting, not a performance SLO or capacity gate.

Capture before-prime, steady/load, drain and recovery bookends separately. For
each load point report configured and issued rates, latency p50/p95/p99/max by
shape, write-to-durable/output/client stage tails, freshness age, pending tenant
and job counts, final fixed-target catchup and observation deadlines. Publish
CPU/quota/throttling per role, RSS/cgroup usage, database time and statements per
unit, lock-wait sampling and its limits, WAL retention, storage/network and
generator/observer CPU/RSS/query/byte/time cost. Missing counters stay UNMEASURED.
Do not average away a growing backlog or hide a failed authority/clinical oracle
behind a successful reduction. A quiet matched comparison needs comparable
source, workload/history and placement; shared-node diagnostics retain contention.

## Next load ladder and unmeasured limits

1. Commission two tenants with access, stored, selected clinical and stock-frame
   controls. Run `small` with the released runtime input and independently reduce
   it. Any missing essential oracle keeps its dependent claim UNMEASURED.
2. On the same attributed source/history, admit `representative-mix`; extend
   observation to a known due-work opportunity plus drain if the finite window
   permits. Do not invent a clinical latency or availability target.
3. Step ordinary REST at 1, 2, 5 and 10 requests/s with fixed viewers, probe
   cadence and resources. Use stress-discovery separately to vary probe cost.
   Record saturation/refusal/drop/backlog curves as results; do not promote
   capacity from the last nominally issued rate.
4. Vary connected viewers, hot/cold skew, provisioned-vs-active population,
   retained history and reconnect burst independently after their instrument
   boundaries exist. T currently fixes equal weights and one full roster. No
   such missing dimension is silently implemented by these profiles.
5. The existing operating owner can explore 1,000/3,000/10,000 tenants on admitted
   resources with realistic cadence and source-qualified all-writer progress.
   These cluster profiles grant none of that headroom or other experiment budget.

Test shards are independent test-state Jobs; independent fixtures have independent
state; load workers divide one declared offered workload; API/evaluator/realtime
horizontal scale-out changes runtime topology. One cohort Pod remains one
replica. Neither test fan-out nor extra clients proves application scale-out.
Backing-store Pod replacement on emptyDir loses state and cannot qualify durable
recovery. Role restart, recovery without a new write, independent-tenant
continuity, alarm/due work, connector catchup, large histories, long endurance,
HA and production admission retain their own unmeasured boundaries.
