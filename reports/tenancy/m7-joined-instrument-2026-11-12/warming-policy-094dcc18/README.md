# Bounded typed-status warming policy

[Exact source, policy, controls and limits](proof.json) and the [manifest](instrument-manifest.json)
bind the [diagnostic-only receipt](diagnostic-receipt.json). The new policy retries
only an actual GET-status503 with exact TENANT_WARMING, preserving that first
response in the sanitized bounded trail. It follows a measured API cold contract;
it does not retroactively classify the unrecorded original remoteD refusal.

HTTP accounting version2 keeps successful4N criterion calls separate from known
warming refusals. Physical explicit DATA requests and trail records include both;
Socket.IO transport traffic is outside this explicit-call counter. All prior SQL,
frame, observed restart and recovery oracles remain required. A diagnostic receipt
or result cannot unlock CAP/pilot or assert full acceptance.

Real HTTP/stock-client and child-process controls cover warming→200, first-refusal
retention, immediate401/unknown failures (including after warming), no exchange or
write retry, probe exhaustion, deadline refusal and prompt process exit. The
positive child restarts the real owned server through an instrumented callback;
it does not assert a shipping Docker/PG/clinical acceptance result. The probe cap
uses a reduced fixturelimit2 to avoid an unnecessary512-request run; the module
rejects configuration above production512. Independent immutable source review
reported no blocking read-derived mismatch. No cloud or capacity run occurred.
