# Realtime sharding, composition and recovery

The edge and realtime use the same tenant-to-slice function. Each tenant's connections and delivery work go to its owning process. Evaluator and realtime can have different slice counts. The deployment assigns ordinals and changes K by planned restart. The November fixed-roster publisher and versioned move map retired when static hash ownership was adopted. [Ownership decision](multitenancy-decisions.md#static-hash-ownership) · [Ordinal binding](multitenancy-decisions.md#statefulset-ordinal-scaling)

## Client and alarm semantics

Realtime loads the tenant on connection and reconciles current output under the client's authority. A replacement process receives fresh connections. It reconstructs current state from the stored evaluator result. Connected viewers receive subsequent deltas. Reconnect does not replay old alarm notifications. An eligible alarm repeats on its heartbeat clock. [Connection-driven realtime](multitenancy-decisions.md#realtime-connection-driven) · [Alarm parity on reconnect](multitenancy-decisions.md#realtime-move-alarm-parity) · [Communication contract](evaluator-realtime-communication.md)

## Evidence and remaining qualification

The [candidate 5 discovery record](execution-log.md#candidate-5-qualification-and-nominal-discovery) distinguishes write-to-viewer latency, connector delivery and the run's capacity verdict. The [November 15 placement reference](../../archive/tenancy/realtime-placement-2026-11-15.md) retains the tested stop, warm, publish and reconnect sequence on its named sources. Use the [production guide](production-critical-path.md) for the evidence required to admit a deployment.

Sections in the captured guide:

- <a id="implemented-boundary"></a>[Implemented boundary](../../archive/tenancy/realtime-placement-2026-11-15.md#implemented-boundary)
- <a id="logical-roles-and-process-placement"></a>[Logical roles and process placement](../../archive/tenancy/realtime-placement-2026-11-15.md#logical-roles-and-process-placement)
- <a id="placement-routing-and-durable-state"></a>[Placement, routing and durable state](../../archive/tenancy/realtime-placement-2026-11-15.md#placement-routing-and-durable-state)
- <a id="controlled-moves-and-failure-recovery"></a>[Controlled moves and failure recovery](../../archive/tenancy/realtime-placement-2026-11-15.md#controlled-moves-and-failure-recovery)
