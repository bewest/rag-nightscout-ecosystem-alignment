# M7 native synthetic stored-count oracle: source and SQL evidence

The bounded source capability and SQL compiler/count semantics passed. Selected
controller SQL integration, a new application image, the clinical native episode
and native capacity acceptance remain **UNMEASURED**. This record is a selected
projection; [summary.json](summary.json) carries exact anchors and provenance
checksums. Raw logs, SQL, per-tenant observations and retained database files remain
outside Git under the evidence identifiers listed there.

## Source boundary

Deployment `fd24ec8aef878a982f175dc2c927fd46e1e1bd98` adds the opt-in
`stored-counts` controller command on base
`3d13c63bc404397d6daee501c152288b12d5931d`. Core stays
`074eab44ee75b9175c951b6a8add3df3e9554af7`. The binding tree is
`21a7c2c52a2b2d5e0112b0866d2440f93f04e10e`; the reduced fixture and five-file
recorded delta are unchanged. Independent review approved this exact source.

The command accepts a fixed native run marker and one to 128 canonical tenant
UUIDs. It returns aggregate counts from the fixed `nsdemo` entries, devicestatus
and treatments tables, all requested rows including zeros, and marker counts
outside the requested roster. It uses the existing controller lock and shared
observer ceiling of two, with durable uncertainty retention. Recording controls
reproduce this source behavior; they do not execute SQL or qualify native behavior.

**The caller must pass the whole same-marker episode roster and require all four
foreign totals zero.** Foreign means outside that requested roster. Batching a
larger same-marker episode would count other legitimate batches as foreign. A
partial roster supports no global-cleanliness inference. The intended native
roster has 16 tenants and fits the 128-tenant bound.

## Reproduced failures and controls

Initial deployment `4272ead77400aa0fc356188c78135ebce8f11410` omitted ordinary
observe's canonical incarnation check. Root reproduced ordinary observe refusing
with `CONNECTION_CONTROLLER_LEDGER` while counts reached one recording SQL call.
The final repair reuses that predicate: both methods refuse and recording SQL
calls stay zero. Eight count checks, six controller checks and one adapter check
pass on the repaired source. Source identity and package checks pass.

Nine earlier source controls each failed and restored: exact selector fields,
roster bound, foreign SQL exclusion, positive foreign retention, credit reservation
before SQL, shared observer ceiling, resource identity, project custody, and
foreign diagnostic retention on disk failure. Their attribution remains initial
4272; the separate ledger regression measures the final repair. The foreign SQL
shape control is source evidence, supplemented by the actual SQL control below.

The first isolated SQL instrument omitted `docker exec -i`. SQL stdin was not
forwarded; psql returned empty output and the JSON assertion failed. It measured
no count semantics. Its original script and captures are retained. The exact
container was removed and root independently confirmed absence.

## Actual PostgreSQL compiler/count measurement

The corrected instrument used the exact local pinned PostgreSQL image, pull
disabled, no network and no published ports. Its setup session witnessed
PostgreSQL 16.15 and `server_version_num = 160015`. It verified that the final source
module bytes equal the original immutable 4272 module before exporting the SQL.
Empty requested rows, seeded requested/foreign counts and deletion of only the
synthetic foreign rows matched expectations. Removing foreign exclusion from a
scratch expression produced foreign entries two instead of expected one: the
assertion failed while SQL itself exited zero. Restoring the exact exported
expression passed.

The run used 31 host commands, 137390 raw output bytes and 2.015 seconds within
40-command, 8-MiB and 300-second limits, including a 90-second cleanup reserve.
Exact CID/image/birth/project/mount custody was checked before execution and
cleanup. The only container was stopped and removed; root independently confirmed
its absence. Private data is retained. This fixture validates generated SQL syntax
and count meaning only. Root owns the subsequent coherent source, image,
instrument and profile join for the clinical native episode.


The selected projection matches retained case results and root cleanup hashes.
The record worktree's `make queue-check` attempt failed before gates because
ignored external lane directories required by queue validation are absent there.
The retained validation log records those paths; no worktree was repointed and no
queue state was changed. This limitation does not change the measured source and
SQL compiler results above.
