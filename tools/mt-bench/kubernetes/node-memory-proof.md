# Node memory proof, without admission

This fixed read-only port measures the selected Node's memory and eviction
policy. It does not admit a workload or change preflight, allocation, requests,
the existing guard or the original 20% soft reserve. `MEASURED` means that the
bound observation completed, never that capacity fits. Omission changes nothing.

The implementation is limited to the reviewed Linux Kubernetes v1.34.12 source
contract. Its public-source bundle identity is
`ecd15669b09d030e499502d37e5ee9ca5314f4b8de761ca6f1f990b3bf8bab8e`.
This leaf implements the source-derived design as an independent port.
Operator39 owns any later live execution after independent review.

## Source semantics

The Linux [summary provider](https://github.com/kubernetes/kubernetes/blob/v1.34.12/pkg/kubelet/server/stats/summary_sys_containers.go)
reads `node.systemContainers[name=pods]` from `GetPodCgroupRoot()`. The
[provider](https://github.com/kubernetes/kubernetes/blob/v1.34.12/pkg/kubelet/stats/provider.go)
uses cAdvisor for this aggregate even when individual Pod statistics use another
backend. Root memory comes separately from `/`. This closes the container-sum
gap; it does not infer Pod usage from DaemonSet metrics.

The [memory conversion](https://github.com/kubernetes/kubernetes/blob/v1.34.12/pkg/kubelet/stats/helper.go)
reports `availableBytes = local cgroup limit - workingSetBytes` when finite.
Their sum is the reported local limit, not the minimum of arbitrary ancestor
limits. Missing memory support can produce zero working set without available
bytes; that is unavailable evidence. The port rejects missing fields, overflow,
inconsistent counters and duplicate Pod-root entries.

The [eviction implementation](https://github.com/kubernetes/kubernetes/blob/v1.34.12/pkg/kubelet/eviction/helpers.go)
uses root and Pod-root available memory separately. With `pods` enforcement,
hard `memory.available` thresholds also generate an allocatable-memory signal.
Soft thresholds retain their grace periods. Minimum reclaim participates in
the recovery comparison. Percentage thresholds use each signal's reported
capacity and the version's float32 conversion; the port assumes no default
threshold. Filtered config comes from the loaded `kubeletconfig` object in
`configz`, rather than a guessed disk configuration.

The reviewed v1beta1 typed `omitempty` maps may omit an empty reservation or
threshold map; that means the loaded map is empty, not that a default threshold
should be reconstructed. A missing loaded-config object or missing summary
memory pointer remains unknown. Source-valid minimum-reclaim percentages above
100% stay representable; they do not create capacity.

## Fixed interface

A caller creates a private 0600 scope from its reviewed controller authority:
explicit context, exact Node name/UID/boot/version/capacity/allocatable,
kubectl/guard/helper/source hashes, the original finite deadline and finite
source-age/skew selections. The CLI accepts only that absolute scope reference
and a nonce on stdin. It accepts no resource, URL, argv or endpoint override.

The collector brackets two private samples with normal guarded Node and complete
assigned-Pod census reads. Private GETs are exactly the selected Node's
`stats/summary` and `configz`; all raw bytes stay in memory. Only typed numeric
memory/policy projections, safe Node identity, timestamps, booleans and hashes
leave the process. Errors suppress raw stdout/stderr and exception strings.
Per-GET timeout is the existing 20-second bound, clamped by the original deadline.
The 32MiB response acceptance/JSON bound is checked after pipe capture; it is not
a streaming process-memory bound. Raw oversized output can consume memory before
the collector refuses it. This leaf does not claim a stricter streaming limit.
Node heartbeat versions and Pod readiness refresh may change; UID/boot,
allocation, policy, resources, roster and container incarnation may not.

Both root and Pod-root samples retain source time, working set, usage, available
and derived local limit. Policy retains actual reserved memory, cgroup/enforcement
settings and every memory hard/soft threshold with grace and minimum reclaim.
The original reserve remains a separate exact `max(512MiB, A/5)` input. A future
consumer must preserve it **beyond** applicable eviction/reclaim thresholds;
`max(F, threshold)` is not equivalent. There is no admission consumer in this leaf.

Unknown version, source, policy or missing evidence refuses. Positive identity,
tool, nonce or policy drift fails. Existing arbitrary stricter ancestor limits
remain an explicit unproved limitation shared with the old model; this port does
not introduce a new ancestor-inspection gate or claim complete hard-limit safety.

## Qualification boundary

Focused controls use the real CLI and caller with pinned inert kubectl/guard
executables. They cover output loss/redaction, missing/duplicate Pod root,
quantity and limit errors, policy parsing, timestamps, UID/boot/census/tool drift,
deadline, foreign scope, forged response and secret sentinels. A meaningful
comparison ablation must fail and its restoration pass. No live Node, Pod,
provider action or full application campaign belongs to these controls.

Current08 remains refused. Root owns the later accounting-contract decision;
operator39 alone owns any authorized live numeric proof capture.
