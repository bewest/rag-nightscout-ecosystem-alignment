# Representative PostgreSQL backup/upgrade capability proof — 2026-11-06

**Reproduced: passed at the representative entries-and-clock boundary.** The five
PostgreSQL cases passed, all four semantic controls failed for their intended
physical effect, their targeted restorations passed, and a fresh unmodified
five-case restoration passed. No product defect was found in this focused run.
The initial dependency-layout setup failure is preserved separately as invalid
operational evidence.

Application source: `f77c025f8e797775faca0e179cc84fc3ca9c5874`. Proof instrument:
`c3f9e6270de75c44e54b6864059437305854a3a2`,
[`tools/lab/tenant-backup-upgrade`](../../tools/lab/tenant-backup-upgrade/README.md).
Exact source archives, scratch probe patches and capture hashes are indexed in the
[sanitized aggregate](backup-upgrade-native-f77-2026-11-06.json). Dates use the
maintainer's local November 6; runtime timestamps below are UTC November 7.

## Executed boundary

The fixture contains two synthetic tenants, three typed entry rows (including an
ObjectId/string twin), and two write-clock rows. It runs real PostgreSQL migrations
and SQL. Independent observer connections read back persisted counts; no fake SQL
client supplies this result. PostgreSQL version: `16.15 (Debian 16.15-1.pgdg13+2)`;
Node `v22.23.4`. Local image identity:
`sha256:066167ff39c2a612402ce99b734ea1cff92a9d1f2ac52f697a5f0384f0d88d6b`,
repository digest
`postgres@sha256:9e2cf6287f25c3151f4c9421ccce2b17f3e60061c111a29165e0d2cdd9ff0a97`.
No pull ran. A private dependency copy matched the application package-lock;
caller database environment was cleared. No peer dependencies or source changed.

| Stage | Reproduced result |
|---|---|
| Original private dependency setup | Failed before any fixture: ERR_MODULE_NOT_FOUND for debug. The copied dependency root was not named node_modules. Corrected the private layout without changing application source. Not a semantic red or a native pass. |
| Corrected initial five-case run | 5 passing / 0 failing / 0 pending |
| Four semantic mutants | Each 0 passing / 1 intended assertion failure / 0 pending, plus independent physical evidence below |
| Four corresponding targeted restorations | Each 1 passing / 0 failing / 0 pending |
| Fresh final unmodified five-case run | 5 passing / 0 failing / 0 pending |

The five cases exercise digest/ACL prewrite refusal and bound-identity refusal;
typed restore, sequence advancement, explicit grants and forced RLS (including
foreign-write refusal); self-consistent tenant-row loss against an independent
source oracle; interrupted and lying-insert rollback followed by rerun; and
upgrade/old-catalogue refusal/fresh-target rollback without changing upgraded rows.
They use a superuser operator fixture and a NOSUPERUSER NOBYPASSRLS application
role. They do not establish a separately constrained production operator identity.

## Meaningful controls

The mutations run only in archived scratch source. Probe patches retain the
original assertions and add separate observer queries at the failure boundary.
All source trees and catalogues remain unchanged.

| Mutation | Intended assertion and independently reproduced physical effect |
|---|---|
| Disable file-digest check | Digest-refusal assertion fails because refusal moves to RESTORE_ORACLE_MISMATCH. The damaged artifact issues 5 INSERTs and 1 sequence update before the later oracle/ROLLBACK; independent target readback is empty afterward. This is failure of prewrite refusal, not absence of the later oracle. |
| Disable restore readback comparison | Expected rejection is missing. Restore reports acceptance of 5 writes while independent target clocks are 0 versus source clocks 2; all 3 entries persisted. |
| Substitute COMMIT for ROLLBACK | Empty-target assertion fails after the intended interruption. Independent observer sees 2 committed tenant-A entries, versus expected 0, with no clock rows. |
| Suppress independent comparison differences | The assertion naming the missing tenant/table fails. Independent source has tenant B entry count 1; target has 0, while tenant A retains 2 and both clock rows remain. |

Each red is an ERR_ASSERTION with the specified symptom and physical effect.
No timeout, setup exception, TypeError or unrelated refusal is counted as a control.
Every corresponding original check passed after source restoration.

## Resource attribution and evidence

Ten valid fixture invocations created ten owned containers and ten observed
anonymous volumes. Each exact container and volume was independently confirmed
absent, with no emergency cleanup required. Container/volume/network inventories
returned to the same preserved baseline after every invocation (159 containers,
462 volumes, 8 networks). Recorded native launcher/Docker child identities were
reaped and independently absent; unknown resources were not removed.

The invalid setup created no fixture and also left the baseline unchanged.
**Final runtime RELEASED: `2026-11-07T00:58:56.719204Z`.** The integration coordinator
was informed before any broader campaign. Per-invocation removal timestamps and
private resource/child identities remain in the local evidence capsule.

Manifest hashes, reverified after capture:

| Capture | SHA256 |
|---|---|
| Invalid setup | `1b82c72f1c4863aca8191e75cf7871fb7d2d994a78a43c6695a311501a9f4e1f` |
| Corrected initial | `46903637d18b98cd7f1ac91fece4f8a351eadda649b49dcc233c522a760fa861` |
| Controls/restorations | `59e8e4407457c77d2e8dc6e61a017eec126ebbfb2cd79bcc4797d9fcce028db9` |
| Final restoration | `e6235514d5d252b6d68d8609fedc45d1eeba22cbac8a4684d17fe4da15f31868` |

The integration coordinator owns the release-record update. Local capsule index:
`externals/work/backup-upgrade-native-capability-20261106/index.json`.
One evolving lane handoff:
`externals/work/HANDOFF-codex-backup-upgrade-continuation-20261106.md`.
Raw captures are local/untracked; public records contain aggregates and hashes.

## Remaining boundary and next integration

This proves representative entries/clock operations on exact f77. The reviewed
lifecycle inventory contains more domains; the full selected catalogue set,
independent lifecycle request ledger, populated policy/FK data and newer schema
successors need assembled Batch C validation. Default upgrade backup storage is
memory-only; durable persistence, process-crash recovery, provider/Vault keys,
retention, artifact bounds and performance remain unmeasured. Preparation commits
separately, and PostgreSQL sequence changes are not transactional.

Next, the coordinator selects one coherent Batch C head and complete inventory.
Use existing journey request builders and probes for a bounded client-visible
comparison of restored/rollback multitenant data with the single-tenant reference:
typed identities, ordering, incremental clock/history reads and tenant isolation.
The existing journey launcher targets single-tenant MongoDB, so reuse/adapt its
request descriptors with the current multitenant client-replay instrument; do not
infer PostgreSQL recovery equivalence by launching that old runner unchanged.
No journey/application/full/browser/whole-corpus campaign ran in this proof.
