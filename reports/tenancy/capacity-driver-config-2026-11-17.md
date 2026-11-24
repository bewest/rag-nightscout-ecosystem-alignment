# Configurable load-driver measurement — 2026-11-17

This record describes the local driver as measured on November 17. Configuration
selects finite scenario schedules, VU budgets and observers through the existing
runner interface. Native generated-k6 controls close the driver criterion;
Nightscout capacity remains **NOT_GRANTED**.

## Source and retained evidence

**Reproduced:** implementation `66ac405d0d81a7a7ca7ffcb6862a1803be4c3bfe`, based on
the clean operating-helper history `86aaf32c3e889bd60ac401aba19023243e66c197`.
Shared alignment main was `c6416cff320ae025146378a79998062168567780`. Nothing was
pushed. No application source or source-admission contract changed.

The retained evidence identifier is
`/mnt/data/nightscout-workspace/artifacts/capacity-driver-config-20261117/native05`.
Its `qualification.json` SHA256 is
`2e53219ab907a6b36bed25bfa576d9037f25c6dc4b19257a712648ebff44742b`.
`driver-sources.json` records the actual harness, generator, wrapper, launcher and
reducer bytes. Independent readback in the parent evidence directory's
`release-validation-final.json` matches every recorded byte hash to the implementation
commit and exactly reproduces all six saved assessments. The full instrument
SHA256 is `be198b16fcca5d3765a567e9a167aa9f7426e5954b7c152e63a0c72b4cfeb8fa`.
These files contain synthetic test observations and stay outside Git.

The already-installed native image was
`sha256:eeb0db19cd8d263aa57346cdbc7ea18e6fcfb2ba9497746a7ae82ceefc8c9fa5`
(k6 1.3.0). Each container had one CPU, 1 GiB memory, no swap and 128 processes;
at most two containers ran concurrently. Each native case used an independently
owned loopback HTTP server, with no application, database, provider or registry.
Every container exited zero with `OOMKilled=false` in the final capture. Exact
owned-container cleanup was confirmed after execution.

```bash
PYTHONPATH=tools/mt-bench/m7-joined python3 -B -m unittest \
  test_driver_config test_driver_vu_diagnostic test_driver_shards \
  test_realistic_mix test_workload_scale test_fingerprint_body \
  test_run_configuration test_runner test_discovery test_http_accounting
python3 -B tools/mt-bench/m7-joined/qualify_driver_config.py \
  --out /mnt/data/nightscout-workspace/artifacts/capacity-driver-config-20261117/native05 \
  --k6-image sha256:eeb0db19cd8d263aa57346cdbc7ea18e6fcfb2ba9497746a7ae82ceefc8c9fa5
```

The native command refuses an existing output directory; a repeat needs a fresh
explicit overflow path. The focused suite passed **62 tests**, with no skips.
`focused-release-final.log` owns the full output.

## Native results and controls

All figures below are **reproduced**, from actual generated workload bytes and
the existing local/sharded launch interface. Planned counts are summed per-scenario
integer ranges; issued and completed counts match independent loopback target
counts. JWT setup is separate. The two-shard case starts its status scenario one
second later, within the same six-second overall load horizon.

| Case | Population | Rate selection | Window / shards | Planned range | Issued / completed | Dropped | Offered work / HTTP |
|---|---:|---|---|---:|---:|---:|---|
| Small | 12 | 22 requests/s | 4 s / 1 | 88–95 | 93 / 93 | 0 | PASS / PASS |
| Sharded | 36 | 44 requests/s | 6 s / 2 | 260–274 | 269 / 269 | 0 | PASS / PASS |
| Realistic mix | 500 | existing realistic-v1, scale 8 | 4 s / 1 | 225–225 | 225 / 225 | 0 | PASS / PASS |
| Delivery before | 8 | 20 requests/s, follower reads | 4 s / 1 | 80–81 | 81 / 81 | 0 | PASS / PASS |
| Deliberate slow target | 8 | same plan, 200 ms response delay | 4 s / 1 | 80–81 | 17 / 17 | 64 | FAIL / PASS |
| Delivery restored | 8 | original response behavior | 4 s / 1 | 80–81 | 80 / 80 | 0 | PASS / PASS |

The realistic point uses the summary observer; the other points use CSV scheduling
observation. Realistic scale 8 is a uniform rate bracket, not sensor-cadence scale 1.
The actual summary retains each scenario's nominal floating offered count as well
as integer bounds. At an exact duration boundary, k6's timer can race duration
cancellation; the optional endpoint dispatch is included explicitly. The minimum
permits no missing nominal slot. Final small/sharded cases record 5/9 starts and
completions during drain; they are not folded into steady completion counts.
The [pinned k6 executor](https://github.com/grafana/k6/blob/v1.3.0/lib/executor/constant_arrival_rate.go#L300)
is the read-derived basis; the endpoint observations above are reproduced.

| Authored break | Exact symptom | Restoration |
|---|---|---|
| Change manifest offered rate while retaining actual emitted plan | `M7_DRIVER_MANIFEST_PLAN_MISMATCH` | Original manifest reduces to PASS |
| Move an ordinary request counter timestamp into setup | `M7_DRIVER_TRACE_PHASE` | Original trace reduces to PASS |
| Remove the second shard exit receipt | `M7_DRIVER_SHARD_MISSING` | Original receipt reduces to PASS |
| Hold the target slow with one finite VU | 64 dropped; 17 issued and completed; offered FAIL while HTTP PASS | Original target returns offered PASS |

Each break landed and produced the intended semantic failure. Restoration checks
use the unmodified capability reducer. The final native evidence manifest hashes
the restored captures.

Earlier captures remain retained: `native01` stopped because the reducer expected
a phase column, while actual k6 CSV stores it in `extra_tags`; `native02` retained
one shard's exit 137 under a shared 512 MiB driver limit (OOM cause UNMEASURED in
that capture); `native03` stopped on an incorrectly strict nominal-end timestamp
check. No failed capture is upgraded. These failures led to the actual CSV parser,
explicit test allocation/exit-state retention and endpoint/phase accounting.
They do not diagnose a product capacity limit. The earlier passing `native04` capture
is also preserved. A final focused regression reproduced and removed an unnecessary
time-unit cap that refused a supported low aggregate rate at a large population;
`native05` qualifies the final source after that correction.

## Integration and compatibility

The [runner contract](../../tools/mt-bench/m7-joined/RUNNER.md#configuration-driven-driver-measurement)
owns configuration fields, resource/file bounds and commands. The existing
runner configuration accepts `prepare.driver-plan` as a JSON string, and its
receipt projection binds the normalized plan. Changing a VU budget changes the
configuration hash. Source/topology authorization remains with its existing owner.
Historical trace/preallocated selectors and original reports/verdicts are intact.

The minimal launch integration changes the adapter parser, discovery k6 launch
and existing shard launcher. HTTP payload generation, status fingerprints,
stored-write oracles, clinical/client boundaries and source admission are reused.
Unknown executors/options, invalid windows/VUs, missing shard data and unsupported
remote launches refuse explicitly. Runtime CPU/memory stay in the existing
allocation. Trace limits are per file; shard count multiplies retained storage.

**Limits:** loopback metadata with two API replicas does not measure two serving
Nightscout instances. Native application topology, remote/Kubernetes wiring,
real application warmup costs, storage, authorization, clinical delivery and
capacity are **UNMEASURED** here. The new driver mode is local only; the actual
remote projection refuses it. Pooled percentiles and guaranteed pooled percentile
bounds stay UNMEASURED. No full application acceptance campaign was run.
