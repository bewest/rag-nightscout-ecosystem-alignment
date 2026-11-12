# Registry and fixed-replica Vault Agent proof — 2026-11-12

Reproduced: the opt-in Agent capability passes its focused and finite native criteria. This is **not combined M7, capacity, browser or clinical acceptance**. [result.json](result.json) is the machine-readable manifest, including encoded/decoded artifact hashes and exact source files. Captures are immutable after this commit; later measurements belong in a new record.

## Source and instrument custody

Delivery is nightscout-deploy `fa558353154c875312da984926a4efd83dfcbef6`, based on the coordinator's `96cd3e6d48ce4117a558fad702911c71605f53b8`. Native execution used core `d50502bb6126bda2bb0af384569e1d95de114f2f` and deployment `43cd1e6a85e9b60a5b1b174a840609ce938169f6`. The five production Agent runtime files are byte-identical between that measured deployment and delivery; delivery adds proof instruments, tests and documentation. The native image remains labelled with its actual measured pair.

Source instruments live in `bindings/compose/vault-agent/tests/` in the deployment delivery commit. The manifest pins every source file. `native-probe.cjs` has SHA-256 `d7a87d11edc7f06eacf34634de1606451487971dd609240e213608609c90fdad`; the separate secret-lifetime probe has SHA-256 `49eec66b325dba39720ce08e35d3ce8e2cfe34841d2e85a930f84737e242d8e9`. Provider image, actual container/image identities, selected mounts and before/after API boot identities are in [native-resource-inventory.json](native-resource-inventory.json). [versions-and-bounded-log-observations.json](versions-and-bounded-log-observations.json) records Node/Vault versions and explicitly bounded log sampling. Log tail observations cannot establish absence.

## Measured criteria

- Focused delivery checks: 28 passed, zero failures/skips. They cover actual registry/static transformation, exact 1/2/4 API rosters, custody/refusal/partial-run bounds and selected RT/evaluator planning. Synthetic 2/1000/10000-tenant policy checks use doubled HTTP/parser adapters: they establish constant request/policy construction, not capacity.
- Actual production parsers accept generated 1/2/4 API configurations without mutating state. Actual native serving uses two API containers and two synthetic tenants.
- One constant-size serving policy and one machine AppRole permit the four serving Transit operations and refuse key-management/encrypt/management/human-management operations. The real Agent owns login/renewal; APIs read its sink. Only APIs receive read-only sink mounts and the Agent receives its writable mount.
- Real same-token renewal and max-TTL reauthentication succeed. Missing sink refuses despite old credentials remaining present; seal, expired token, consumed-secret restart and transport outage refuse. Explicit replacement secret-id, unseal and restored transport recover. Across the final phases there are 44 serving observations: 26 expected 200 responses and 18 expected 503 `AUTHORITY_UNAVAILABLE` responses. API container IDs and start times do not change during these faults.
- The shipping machine secret-id is reusable/nonexpiring (`secret_id_ttl=0`, `secret_id_num_uses=0`); serving tokens remain bounded (this proof: TTL 20s/maxTTL 60s). The private input file is consumed. Operator revocation/rotation remains explicit, and an Agent restart requires explicit replacement of the consumed input file.
- A distinct diagnostic role with token TTL 2s/maxTTL 6s and secret-id TTL 3s reproduces failed max-TTL reauthentication after secret expiration. Restoring secret-id TTL 0 yields two valid max-TTL reauthentications. These use the actual Agent, not an authored login/renewal loop. The diagnostic Agent containers and role were removed.

The preliminary `0ab635788539eabb2bd13d273f8af5159522574c` observation used short serving lifetimes but requested a 24h secret-id. It does not establish default-lifetime correctness. Its capture is retained separately from the final proof.

## Meaningful red and restored controls

The coordinator independently ran the committed in-memory controls against the measured bootstrap bytes. Restoring those bytes passes 20/20 without skips.

| Control | Actual red symptom | Result |
|---|---|---|
| Restore per-tenant policy union | `VAULT_AGENT_REQUEST_BOUND` in static 2/1000/10000 cost check | 19 pass / 1 fail |
| Restore static-only transform | Actual registry `IMPORTED_API_CONFIG_INVALID` | 12 pass / 8 fail |
| Omit second API transform | Second API retains `/run/ns-config/vault-token`; mixed/state refusals missed | 17 pass / 3 fail |

The initial native probe produced 404 `TENANT_REFUSED`: an actual Node 24 echo discriminator showed fetch did not preserve its supplied Host while `http.request` did. The probe was corrected and remeasured without a source/runtime change. Original instrument bytes and captures are retained; this is classified as `INSTRUMENT_HOST_TRANSPORT`, not a product failure.

## Remaining integration boundary

Deployment `npm test` fails at the inherited SOURCE tree check: actual `acfa763f1483343d12af5bafa05eb18ee1b5bf49`, recorded `8c12259b1dcc179be0738f0ce775c0bd6cd62626`. That tree is unchanged from the coordinator WIP. This lane does not modify SOURCE metadata. Downstream ownership checks run separately against the exact production core image pass 2/2 without skips. The coordinator owns source-pin refresh and final paired acceptance after other adopted repairs join.

No full campaign, capacity claim, live provider, custom SQL settings seed, default/pilot activation, cloud action or push occurred. RT/evaluator selection is planner-tested here; their live scaling acceptance remains separate.

## Resource disposition

All 12 containers in each owned serving project `ns-vault-agent-final-native-20261112` and `ns-vault-agent-short-native-20261112` are stopped. Their private states and volumes remain retained for review. Diagnostic Agent containers are absent and their diagnostic AppRole was deleted. No peer resources were stopped or deleted. The final native inventory and stopped-project capture substantiate the final project; local paths and retained preliminary state are described in the lane handoff.

Record consistency: all 31 artifact encoded hashes and available decoded hashes/sizes verify. `make docs-links` passes (27 checked, zero failing). `make queue-check` fails at queue validation because this isolated alignment worktree lacks the queue-declared external gate worktrees; no queue state is changed by this record. The initial sandbox-only docs attempt could not spawn Git and is not counted.
