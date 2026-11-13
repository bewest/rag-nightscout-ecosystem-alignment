# Local address-pool exhaustion and custody sequencing

Captured 2026-11-12. Local infrastructure/instrument record, not a source product
fix or clinical failure. New exact runtime core47b43b6246ce7f94f1f1f0d01830495a78b28add /
bindingbe95214a6cae427e1898b0ca6ce39825163ee291 image
`sha256:6138dbf5cec8dc7c4897e3c1d969868a37bb7fb3eb0af46feca7595fdbb3f361`
built once and passed its label check. Fresh state/project
`ns-evaluator-binding-proof-20261112-due`, port18381, nonce
`6ca2cfd8-d54d-4f11-b03a-e5f40aa1f1ab` remained unchanged throughout this boundary.

## Original failure and scoped remedy

[First startup attempt](captures/initial-network-failure.log): image check passed,
then Docker refused initial backend network creation because predefined address
pools were fully subnetted. No service had started. This first infrastructure
attempt remains FAIL; it is not relabeled as a product failure or uninterrupted
first-attempt acceptance.

After read-only ownership inventory, the coordinator explicitly authorized only
the oldest owned stopped project's two empty networks to be removed by exact
full IDs. Full config/labels/IPAM/options and all twelve stopped containers'
network/mount/image metadata were archived privately before removal. Ownership
project/working-directory and zero endpoints were reasserted. The
[sanitized remedy record](captures/remedy-summary.json) contains the two full IDs,
before/after network counts33-to31, remove exit0 and retained twelve container
IDs/images/statuses. No disconnect, global prune, foreign network action,
container/volume/image removal, reset or reprovision occurred.

Original network IDs were irreversibly removed. Old proof network identity is
historical; restarting those retained old containers requires explicit network
reconstruction. Containers, volumes, private database state and images remain
retained. This limitation was explicitly authorized and recorded.

## Instrument error and actual continuation

The post-removal Python equality assertion compared Mounts arrays by order and
failed for two containers. The surrounding shell lacked fail-closed chaining,
so it continued into the one authorized startup continuation before the mismatch
was classified. Startup completed all ordered phases with exit0; the pause
attempt found no remaining startup driver. This unsupported continuation past
the failed custody assertion is an instrument/orchestration error, preserved in
[the boundary record](captures/orchestration-boundary.json); not a source fix.

Canonical comparison found no semantic custody differences: only mount list
ordering changed. Root independently read back the full private archive and
confirmed exact two authorized empty network IDs, ownership, all twelve stopped
container/image/network/mount identities and33-to31 counts. Qualification stayed
paused until that readback and explicit continuation authorization.

## Fail-closed next-action guard and controls

[Test-owned guard](custody.cjs) compares all recorded keys, normalizing nested
arrays as order-insensitive multisets while retaining multiplicity. Network
objects are keyed by name; alias and mount order do not create false differences.
It checks expected count, unique full container IDs, stopped/exited state and
exact project/work-directory ownership. It makes no Docker/resource call.
An explicit next-action callback is invoked only after verification. A callback
failure is not mislabeled NOT_RUN after it actually started.

[Actual twelve-container verification](captures/canonical-verification.json)
passes. [Four controls](captures/guard-controls.log) pass: ordering-only equality;
semantic mount/network/image/ownership/running/duplicate changes refuse before
callback; exactly one callback for valid custody; correct labeling of a callback
failure. Removing semantic comparison from a scratch copy makes that same
[control go red](captures/semantic-guard-ablation.log) with Missing expected
rejection. No actual startup or resource action is made by these controls.

The subsequent stock/settings/clinical driver calls this same guarded function,
not a shell chain, and deliberately stops before realtime move. This guard was
not retroactively applied to the already-completed startup and does not erase
the original assertion/continuation. No rebuild, startup replay, reset, new nonce,
additional write or deadline/cadence change was used. Coordinator's revised
sequence is strict clinical PASS → post-EVALUATOR-handoff read-only collector
window BEFORE realtime move/B161 write → collector release/root disposition →
conditional realtime move. Actual qualification/collector results are separate.

Private full archive path is recorded in the local handoff; its hash is retained
in the boundary capture, not its private mount descriptors. Public captures use
synthetic typed metadata only. Hashes: [sha256.json](sha256.json).
