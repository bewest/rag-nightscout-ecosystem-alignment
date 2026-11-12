# Normal-baseline TIME applicability — 2026-11-12

This immutable leaf records a **reproduced pure actual-source projection/due discriminator** and a **read-derived phase applicability assessment**. It records the historical measurement basis, not a new policy or campaign authorization. No capacity result follows from it.

The selected commits are core `47b43b6246ce7f94f1f1f0d01830495a78b28add`, deployment `be95214a6cae427e1898b0ca6ce39825163ee291`, and alignment `4ddea55301c3d1f95faf25e15a80051bbb122e8b`. Explicit Git objects were used when peer HEADs had moved; core was clean at the selected commit before and after. [Source binding](source-binding.json) preserves source and private-original hashes.

## Reproduced measurement

The actual core `tenant-projection-evaluator` materialises its bounded memory projection and runs the actual plugins and `nextDue`. Settings use actual `catalogue.DEFAULTS → catalogue.project → environment`, checked against the blank registry-settings enabled-plugin list. Inputs reproduce the deployment primer's fresh normal synthetic SGV values 123/177, one second old, with no additional clinical records.

| Measured condition | Result for both normal values |
|---|---|
| Acquisition at the synthetic initial instant | Correct `bgnow`; no requested alarms |
| Next due after acquisition |599000 ms later, `sgv-recent-10`, `slow: []` |
| Explicit evaluation at599000 ms | Next due advances 1 ms |
| Explicit evaluation at599001 ms | No future due; `slow: []` |
| Per run |14 explicit observations; 2 acquisitions; 0 clinical SQL calls |

The twelve `evaluateTime` calls were invoked explicitly at selected synthetic instants. They **do not prove natural runtime TIME scheduling or completion**. The [full catalogue-default capture](full-projection.json) retains every result, not just a counter summary. [Execution](execution.json), [streams](streams.json), and the [path-redacted instrument](instrument-path-redacted.cjs) retain command/exit, source warnings and the code used. The Basal warnings about a missing treatment profile are expected for this primer and remain in the streams. An initial harness setup attempt refused tenant binding in single mode; the harness adopted the existing pure tests' explicit multitenant mode without changing source.

The [controls](controls.json) distinguish an input contrast from the meaningful red guard control. Disabling only `errorcodes` membership in a scratch copy of the actual ten-minute rule makes the original 599000 ms assertion fail, exit 1; the absent due is coerced to 0 in subtraction, producing `-1794484800000` instead of 599000. Restoring the original actual module returns exit 0. Private instrument/stream hashes are retained; no peer source was modified. This control exercises the due assertion, not a full scheduler or clinical-equivalence claim.

## Dependency and toolchain attribution

The source owner explicitly authorized a historical lane-owned exact-lock dependency fixture. It was not a fresh 47b installation. The fixture lock and selected core lock both hash `6418fe21c18346435f643b8496d6b7ec23c9c6de28f1925c3bb2028eb575e93e`; historical d505 and 47b `package.json` both hash `6bd42fb8f7c0d475209ef7d050a6ebaed7f2b461e12cb254124feabf0fd42a5f`. The fixture has no root `package.json`; historical package equality was independently measured from Git objects, not inferred from a directory name. [Dependency provenance](dependencies.json) names the historical evidence commit and the explicit absence.

The provenance home is alignment `2b197cfc32113612f812442547ae8555e87aaf7d`, `reports/tenancy/m7-core-acceptance-2026-11-12/oidc-d50502bb/instrument.json`, with earlier install records under `reports/tenancy/m7-clinical-equivalence-2026-11-12/`. No install ran for this discriminator.

A scratch Git archive of the exact core bypasses the peer's existing dependency symlink. Resolution rejects every non-builtin realpath outside that source overlay or the specifically authorized dependency tree. All 382 resolution paths are retained with logical path prefixes. No dependency tree or full source archive is published.

The actual pure host used Node `v22.23.4` and kernel `6.18.7-76061807-generic`; [toolchain provenance](toolchain.json) records the binary SHA256. Remote Node24/kernel portability remains **UNMEASURED**.

## Read-derived phase applicability

The selected [adapter](../../../tools/mt-bench/m7-joined/adapter.py) primes data before starting evaluator/remaining roles, requires acquisition readiness, then runs 60 seconds sampler-disabled idle, 120 seconds sampled idle, existing probe/socket prime, 300 seconds sampled load, then restart/recovery. These are source-contract timings, not observed deployment durations.

For a one-second-old reading at the controlled acquisition instant, the ten-minute due is still 539 seconds away when the sampled idle starts after the preceding 60 seconds. It remains 419 seconds away after both idle phases. Actual sequential primer/setup/readiness delays change each owner's starting data age; this experiment does not claim identical ages in an actual deployment. With unchanged normal input, only a roughly 8-to-10-minute initial SGV-age band can put the boundary inside a 120-second idle. Already-expired inputs may have no future due at all.

The core runtime schedules the component's actual future due; a slow heartbeat applies only when the component reports a slow reason. The measured normal input has none. Existing k6/probe writes refresh readings; a five-minute load does not guarantee every owner's ten-minute TIME boundary. The load observer accepts acquisition or TIME progression; recovery requires fresh acquisition in a changed runtime and may finish promptly. Its 900-second ceiling is not a required 900-second wait or a TIME witness.

The selected [progress assessor](../../../tools/mt-bench/m7-joined/evaluator_progress.py) requires a positive completed-TIME delta for every owner during idle, while due state is captured-only and not opportunity-assessed. Failure occurs at idle exit, before later probe/load phases. Therefore those later phases cannot rescue this particular idle gate. The finding is a missing applicability/witness capability, not reproduced evaluator malfunction. Future due cannot be presented as completed TIME or no-work PASS. An urgent alarm-message proof has different applicability and cannot establish the normal baseline's opportunity.

At measurement time the single recommendation was a separate source-owned normal-baseline TIME witness bracketing each owner's actual due and requiring naturally completed TIME under stable ownership/input, without changing the existing seed/settings/cadence or strict completion guarantee. This leaf does not implement or claim any later decision/capability.

## Reproduction boundary and publication

To reproduce the pure experiment, materialise the explicit core Git object into an owned scratch source, obtain an independently authorized exact-lock dependency installation, and replace the logical `<CORE_SOURCE>` and `<DEPENDENCY_NODE_MODULES>` path literals in the published instrument. Run `node` with only `PATH`, `LANG`, `TZ` and the explicit `NODE_PATH` selected as recorded. Do not run it against a peer checkout's dependency symlink. The path-redacted instrument is a derivative, not an additional executed capture.

All public captures are **new labelled derivatives** bound by SHA256 to unchanged private originals. Only local pathname prefixes were replaced; actual result values remain intact. The bounded control summary preserves exact symptoms and original hashes. [The manifest](manifest.json) binds every leaf artifact. No credentials, personal host paths, environment files, dependency tree or full source archive are included.

No application server, network, Docker, database, product build, npm installation or cloud action ran. There is no natural-TIME, SQL correctness, remote Node24, capacity, clinical-equivalence, full-acceptance or deployment claim here. The programme batch owner owns any later integration or decision record.

Publication checks: bounded JSON parsing, manifest hashes, leaf links, privacy scan and whitespace checks passed. One `make queue-check` attempt stopped at queue validation because 16 existing gate cwd references point to absent peer worktrees in this isolated checkout; later steps were not reached. [Exact publication check scope and missing-path diagnostics](publication-verification.json) are retained. No queue or peer files were repaired, and no application gate ran.
