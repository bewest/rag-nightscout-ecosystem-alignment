# Explicit M7 component profiles — integration interface

This is a pure declaration capability. It neither enables a topology nor runs a
measurement. Every identity and comparison retains `runtimeProof: UNMEASURED`.
It cannot substitute for the producer's freeze, runtime, SQL/isolation, settings,
evaluator-progress, recovery or acceptance gates. The existing producer remains
unchanged. `MT-SCALE-UNBOUND` remains open.

## Sources and boundary

Built from alignment `8f839da964fb3274a4428c994a43132b58ea3f24`, with read-only
shipping inspection of deployment `eea9b6cac96d42b48237c00c226394f9bfe37cfb` and
immutable producer `c8a7a9b04a165b96a9659a9306df3d03be02a081`.
The separate API lane owns moving evaluator-progress producer/receipt changes.
Only this module, its schema, tests and interface document belong to this lane.
No runtime/deployment, adapter, provenance, capabilities or receipt file changes.

The adopted evaluator shape is fixed partitions with one selected owner per
tenant. This declaration supports standalone and fixed worker topologies. It
adds neither PostgreSQL HA nor realtime failover. An optional Agent remains a
separate process alongside the Vault server; server observations cannot count as
Agent observations.

## Functions

Import `component_profiles.py` directly from this directory. It has no external
runtime dependencies, file I/O, environment reads, subprocesses or automatic
selection. All malformed declarations raise `Refused` with a bounded
`M7_COMPONENT_*` code. The caller must cap raw input at 65,536 bytes **before**
JSON parsing; canonical output also has this byte cap. Pass ordinary JSON values.

| Function | Input and result |
|---|---|
| `validate_selection(value)` | Exact selection schema; returns an independent copy. |
| `prepare_environment(selection)` | Only source-owned API/RT/evaluator selector variables; no Agent enablement or ambient defaults. |
| `exact_role_inventory(selection, compose)` | Complete resolved shipping Compose service set, including ops profile; returns sorted serving role map and one-shot list. Checks command/profile roles and sink exposure. |
| `resource_overlay(selection)` | Deterministic Compose `services` map containing only `cpus` and `mem_limit` for selected scaling services. |
| `profile_identity(selection, context)` | Canonical declaration including derived inventory/resource map, explicit unmeasured status and SHA-256. |
| `validate_identity(identity, expected_context)` | Rebuilds every derived field from selection and independently supplied context; rejects even rehashed arbitrary roster/resource changes. JSON numeric/boolean types cannot alias one another. |
| `compare_profiles(before, after, axis, expected_context)` | Revalidates both identities, requires exactly one allowed changed scalar, and returns a comparison declaration. No performance verdict. |

`expected_context` must come from the caller's independently verified frozen
source/instrument/host/plan/authority data, never from the submitted identity.
Hashes here are identity checks, not signatures or proof that a plan was admitted.
Original product custody and authority gates remain mandatory.

## Selection schema

[component-profile.schema.json](component-profile.schema.json) describes the
closed JSON selection shape. There are no default values. The Python validator
also enforces the cross-field rule `tokenMaxTtlSeconds >= tokenTtlSeconds`, strict
integer values and the document bound; JSON Schema alone is insufficient.

All fields are required:

- `version: 1`, `apiReplicas: 1 | 2 | 4`.
- `realtime: {mode: standalone | fixed, workers: 1 | 2 | 4, shards: 1..4096}`.
  Standalone requires one worker. `shards` stays explicitly declared even while
  inactive; only fixed mode passes it to the source selector. Fixed one-worker
  mode and standalone are distinct. Shards may be fewer than workers: configured
  idle workers must still appear in inventory and resource attribution.
- `evaluator: {mode: standalone | fixed, workers: 1 | 2 | 4}`. Standalone requires
  one worker. Fixed mode uses the shipping pool/ordinal binding; this module does
  not invent membership or relax exclusivity.
- `secrets: {mode: vault-server | vault-agent, agent: {...}}`. The `agent` object
  always declares `tokenTtlSeconds`, `tokenMaxTtlSeconds`, `policySha256`,
  `secretIdTtlSeconds: 0`, `secretIdNumUses: 0`. Positive serving token lifetimes
  are at most 2,764,800 seconds. The object remains planned, inactive metadata
  in server-only mode; its policy hash is not a claim that a policy exists.
  Selecting Agent later cannot silently change these other fields. Private
  machine credential custody/revocation and consumed-file restart rules remain
  shipping Agent obligations.
- `resources` has exactly six policies: `api`, `realtime`, `evaluator`,
  `postgres`, `vault-server`, `vault-agent`. All are declared, including inactive
  Agent, so worker-count changes use the same policy with no invented budget.
  Each is either `{mode: unlimited}` or `{mode: finite, cpuNano, memoryBytes}`.
  Finite CPU is 10,000,000..128,000,000,000 nanoCPUs; memory is
  16,777,216..1,099,511,627,776 bytes. No float, boolean, negative, implicit or
  partial finite limit. Host-effective ceilings are separately measured.

`prepare_environment` emits `NS_API_REPLICAS`; fixed RT adds
`NS_REALTIME_WORKERS` and `NS_REALTIME_SHARDS`; fixed evaluator adds
`NS_EVALUATOR_WORKERS`. Ambient selector variables must be stripped by the
producer before applying this explicit map. Agent mode must separately consume
the paired shipping Agent plan, not an invented environment switch.

## Inventory and resource semantics

Inventory requires the exact configured serving services: all API/realtime/
evaluator instances, PostgreSQL, Vault server, feed-reader, admin, tenant-admin,
UI, nginx, optional socket-edge and optional Agent. One-shot services are
bootstrap, primer, placement-operator, demo, and optional vault-agent-bootstrap.
Unknown, missing, relabelled or incorrectly profiled services refuse. This
inventory is a configuration observation. It includes every configured idle
worker; it cannot determine tenant assignment or attest that a process is alive.
`workerMembership` explicitly retains that limitation.

The resolved Compose argument uses dictionary-shaped volumes, not raw short
syntax. Only the Agent and exact API roster may mount `/run/ns-vault`; all API
mounts must be read-only, share the Agent's bind source, and the Agent must have
its writable bind. Subpaths, foreign roles, missing API sink, volume replacement
or divergent sources refuse. This does **not** validate the rest of a Compose
object or its files. Source-owned exact archive, private path/UID/mode/symlink,
image, grants, plan and operation custody checks remain prerequisites. PostgreSQL
command/settings and other mounts are not reinterpreted by this helper.

The resource overlay overrides only six scaling classes. It never touches
ancillary services, including the existing feed-reader 384m bound. Replicas of
one role get exactly the same per-role budget. It writes CPU decimals without
floating-point conversion. Explicit unlimited writes `cpus: "0"` and
`mem_limit: 0`; this clears that service's prior direct limit and remains an
unlimited declaration, never a finite measurement. Runtime integration must
reject conflicting inherited quota/cpuset/deploy-limit forms, resolve and check
the merged Compose result, then measure actual Docker/cgroup limits, host
ceilings and throttling. This leaf has not run that integration.

## Context, identities and comparisons

Context has exactly `coreCommit`, `deployCommit` (40 lowercase hex),
`instrumentSha256`, `hostIdentitySha256`, `sourcePlanSha256`,
`settingsFingerprintSha256` (64 lowercase hex),
`diagnostics: {mode: off | on, intervalMs: 1000..60000}`, and
`custody: {kind: paired-compose-plan-v1, sha256: <64 lowercase hex>}`.
`sourcePlanSha256` pins the immutable paired source plan, not a per-cell generated
roster file; generated files need their own producer hashes/verification.
Unsupported custody kinds and unknown context fields refuse. Pin actual image
IDs and runtime-effective limits separately; a declaration cannot supply them.

Allowed single comparison axes:

- `apiReplicas`, `realtime.mode`, `realtime.workers`, `realtime.shards`,
  `evaluator.mode`, `evaluator.workers`, `secrets.mode`.
- `resources.<one of the six classes>.cpuNano` or `.memoryBytes`.

Every other selection/context field must match. Count comparisons recompute the
entire resulting inventory and resource overlay from the unchanged per-role
policies. No special case ignores arbitrary resource-map differences. A mode
change is compared at one worker, then worker count can be a separate axis. RT
shard comparison requires fixed mode. Resource comparisons require an active
class and finite limits on both sides. An unlimited-to-finite change alters the
resource declaration shape and is not accepted as a single finite scalar
comparison. Inactive policy/shard changes cannot represent measured scaling.
Changing CPU and memory together, token policy while enabling Agent, diagnostics,
source/host/plan or settings is a second-axis refusal.

Existing strict pilot/API profile equality must remain intact. Producer wiring
must explicitly version a component-comparison contract and retain the current
evaluator-progress policy and other base-profile fields; this new declaration
must not replace or bypass them. A source pair/instrument changes only with a
new frozen campaign, not during a scaling comparison.

## Required integration before measurement

1. The producer currently archives only multitenant and moves its `.env` out of
   the source tree. The shipping Agent plan requires exact pinned Agent files
   and authoritative private source `.env`. Preserve one authoritative prepared
   environment (an identical copy if needed), archive the paired Agent overlay
   into the owned cell, pin bytes, and retain original plan/custody checks.
2. Consume shipping provisioning/commission/Agent/API/prime/publish/remaining-role
   stages. Route effects through the exact frozen owned Compose config without
   relaxing source mount checks. Agent HCL/bootstrap ops mounts are exact pinned
   exceptions; APIs only gain the read-only sink. Unused privileged mounts must
   never reach publisher/operator. Prove actual planner/config compatibility.
3. Select exact generated API, realtime and evaluator overlays from source.
   Inventory every configured worker, including idle workers, at setup and
   runtime. Keep bounded dynamic role log/sample coverage and explicit truncation.
   Keep Vault server and Agent attribution separate; generator resources separate.
4. Sharded RT recovery must call the committed controlled replacement helper
   with confirmed stop and full authority/readiness/route fencing. Current raw
   restart refusal stays until that integration is proven. No automatic failover.
5. PostgreSQL profiles remain a single database with selected vertical budgets;
   pin pool/settings, record waits/statements and effective bounds. Preserve all
   restore/epoch/isolation/clinical/authorization gates and independent SQL oracle.
6. Functional/isolation/authority/oracle failure blocks advancement on all axes.
   A resource ceiling remains a failed measured profile. Missing runtime samples
   or effective-limit proof is UNMEASURED. Default, pilot and capacity execution
   require their existing separate acceptance/authorization contracts.

## Reproduced focused checks and controls

Run from repository root:

```bash
python3 -m unittest discover -s tools/mt-bench/m7-joined -p test_component_profiles.py -v
python3 tools/mt-bench/m7-joined/test_component_profiles.py --control api4
python3 tools/mt-bench/m7-joined/test_component_profiles.py --control idle
python3 tools/mt-bench/m7-joined/test_component_profiles.py --control agent
python3 tools/mt-bench/m7-joined/test_component_profiles.py --control second-axis
python3 tools/mt-bench/m7-joined/test_component_profiles.py --control identity
python3 tools/mt-bench/m7-joined/test_component_profiles.py --control limits
```

Measured 2026-11-12: normal **25 tests PASS**, all six control subprocesses
**exit 1**, then restored **25 tests PASS**. Controls compile only an in-memory
mutant; source files never change. API4 and idle omission produce
`M7_COMPONENT_ROSTER_MISMATCH`; Agent/server conflation produces
`M7_COMPONENT_ROLE_COMMAND`. Second-axis, identity and limit bypasses produce
`AssertionError: Refused not raised` in the corresponding refusal checks. These
are semantic reds, not setup/import failures. Python Draft 2020-12 schema check
also passes, accepts all 27 fixed-worker shapes and refuses an unknown field;
`jsonschema` was available on the test host but is not a module/test dependency.
Tests use independent synthetic resolved Compose dictionaries. No actual Docker
limit, shipping planner, serving, clinical, capacity or deployment result is
claimed by these checks.
