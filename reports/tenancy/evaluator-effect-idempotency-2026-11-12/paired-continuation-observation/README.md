# Repaired pair: continuation sampled an in-flight changed effect

Captured 2026-11-12. **Clinical qualification failed and remains open.** No
realtime move or clinical retry followed this observation. Retained state is
post-upload and effective evaluator membership three; it must not be reset or
replayed to manufacture an initial baseline.

Runtime core `cd4629159809fb3cffbc6f57626f98f3ffdbdda7`, image binding
`0f8749bc954812b9d384528da733680930e3b236`, actual image
`sha256:454d58b4d30a7a34f9d02005aab44dd7868cd3db6eb27e0f30fcbd623f91feab`.
Executed host diagnostic fixture
`d229e3a9cd8948c35731e0f1f937bc91387f6f77`. Selected topology remains
2 API / 2 realtime workers with 2 logical shards / 3 evaluator participants,
initial effective membership 2 then actual transition to 3, Vault SERVER,
diagnostics OFF. The earlier unclassified 20-second initial subscription timeout
and separate 216-ms read-only passage remain in
[their original leaf](../paired-subscription-diagnosis/README.md).

## Actual continuation result

One coordinator-authorized full clinical continuation failed in 9096.76 ms at
the typed effect oracle: the intentional changed B row was `attempting`, where
strict `accepted` was required. Initial setup passed: A alarm ACK 150 ms, B ACK
165 ms, B initial frame/read-write authorize ACK 222 ms, each one connection.
The sequence reached real uploads, evaluator membership three and the exact
post-transition B input frame before failure. The
[unaltered output](captures/clinical-continuation.log) records that failure.

The source fixture takes one durable snapshot after an unconditional 1500-ms
sleep following B's new frame. It does not conditionally await changed-effect
acceptance and corresponding fanout. This is a read-derived observational race
candidate, not a repaired product defect or retroactive acceptance result.

A later [read-only typed row snapshot](captures/typed-rows.json) at
1794493978911 contains exactly three normal rows, all accepted on attempt one:
A initial, B initial, and one distinct changed B effect. No extra identical
effects/origins, control clears or cancelled rows were present in that snapshot.
Changed B was created at 1794493932133 and accepted at 1794493934908 (2775 ms
later). The failed log's filesystem modification time was 1794493934918, only
10 ms after acceptance; this is not the original SQL snapshot timestamp.
That precise timestamp and final socket fanout evidence were not retained by
the failed fixture. The later snapshot therefore cannot prove the failed
snapshot's acceptance or final fanout. The strict oracle correctly refused an
in-flight row; no predicate has been weakened.

## Resource context and next boundary

A bounded [resource snapshot](captures/resource-context.json) records only this
lane's four owned retained projects: 54 running containers, sampled aggregate
CPU 578.06 percent, 16 logical host CPUs and load averages 10.35 / 8.66 / 8.00.
Per-container memory use is included; no process arguments/environment or
credentials were read. This is context, not attribution of the failure to load.

The proposed instrument repair is a bounded condition-based acceptance/fanout
observation, retaining strict identity/duplicate/clear/terminal-state refusals,
original repeat deadlines and the existing 20-second wait budget. It must have
an in-flight-to-accepted control and immediate duplicate/terminal refusal
controls. A future full qualification requires fresh owned state; the existing
failed state remains evidence. No runtime source, admission or notification
protocol change is implied. Coordinator approval and focused controls precede
any further run. Capture hashes are in [sha256.json](sha256.json).
