# Fresh paired native qualification — 2026-11-12

**Reproduced: the authorized local paired native criteria pass.** This is a
bounded shipping-composition qualification, not full functional/browser/corpus,
capacity, pilot or release acceptance. The coordinator owns those remaining gates.

## Exact inputs and custody

| Input | Captured identity |
|---|---|
| Core | `ff5156b984424f1ef34bcef22d5bfa0071354cfa` |
| Deployment and executed host fixtures | `cf5bda3f2d189bac5d60269df5644759c40db9e1` |
| Frozen alignment instrument | `8ae6f4a3729548de0c88cc0ee5b3c0aede9aba61` |
| Instrument content | `52c76f7500312bc3ce8006f3783444b04489bdf53cd1f764417f77cf8333ba1d`, 37 files |
| Actual image | `sha256:399dea76f971451143b65c02be37c99e76d240d607d1f5b45a35fd564d7e6fd2` |
| Project | `ns-evaluator-binding-proof-20261112-ready` |
| Fresh nonce | `0dc3af55-99df-4fd9-8b1b-8771f68be6f1` |
| Topology | 2 API instances, 2 realtime workers / 2 logical shards, 3 evaluator participants with desired membership 2→3, Vault SERVER, diagnostics OFF |

[Identity](captures/identity.json), [tool inputs](captures/tool-inputs.json), and
[executed binding hashes](captures/executed-binding-sha256.json) bind this run.
The retained [local orchestration drivers](drivers/) and
[executed fixture invocations](captures/fixture-invocations.json) document the
sequence. They are dated evidence, not instructions to replay against retained
state. The source-only image was newly built from committed core/deployment archives;
no retained state, source overlay into an old project or old image relabel was used.
Host fixture execution used Node 22.23.4; the image records Node 24.22.1.

The old idle project was archived and stopped with all containers/data retained.
The only removal was the two preauthorized empty networks of the already stopped
due project, by full IDs after project/workdir/15-container checks. The tested
canonical guard verified unchanged retained metadata; network count changed 33→31.
[Resource custody](captures/resource-custody.json) pins the private archive digest.
Those historical network IDs are irreversibly removed: restarting that old project
requires deliberate networking reconstruction. No containers, volumes, images or
private database state were removed.

## Ordered observations

1. All ten startup stages exited successfully. Fifteen roles ran with thirteen
   health checks healthy; both initial evaluator owners were ready. This startup
   inspection deliberately issued no public tenant HTTP before the new barrier.
2. [Stock/restore](captures/stock-restore.log) passed. All four exact API × tenant
   tuples returned status-ok on their first attempt; no warming response occurred
   in this run. Post-probe CID/boot bookends matched. The original four public-edge
   B settings workers all succeeded before restore spawn and completed 175 reads
   with zero errors. Polling, WebSocket, API3 reload, initial 123/177 frames, tenant
   isolation, real restore/census and B's unchanged socket assertions passed.
   [Readiness](captures/api-readiness.json) and
   [request chronology](captures/settings-continuity.json) retain typed stages and
   timestamps; measured edge upstream attribution remains explicitly unknown.
3. [Settings controls](captures/settings-controls.log) passed through actual source
   lower-port settings/policy/authority fences. Both tenants were configured;
   wrong-tenant and revoked authority refused; an excess writer grant refused
   with `SETTINGS_STORE_UNSAFE`; restored narrow grants admitted again. Synthetic
   authority metadata was fixture setup, and settings values were never written
   through SQL. This is not a shipping public owner-configuration bootstrap claim.
4. [Clinical evaluator handoff](captures/clinical.log) passed desired membership
   2→3. Within the original observation/repeat bounds there were three expected
   accepted normal effects, zero cancelled rows and zero accepted clears: one
   unchanged A effect and B's initial plus intentional changed-input effect.
   Exact timestamped B401 input/frame, source effect digests, matching fanout,
   current checkpoints, stable consumer and unchanged B socket passed. Handoff
   measured 1119 ms against the configured 30000 ms lease. This is a bounded
   logical-effect observation, not a forever-zero-repeat claim; the oracle does
   not independently recompute the B401 alarm payload from clinical semantics.
5. All mutations paused for the API-owned exactly-once strict TIME capture before
   any realtime move. Its primary home is
   [native ready-pair TIME](../../evaluator-trusted-scheduling-2026-11-12/native-ff515-cf5-ready/README.md)
   at commit `3987fe49931537236eb549ce8ea3b1cccd699e1f`. It passed the current strict
   checker on actual listeners and retained all foreign rows. This record links
   that independent measurement rather than copying its evidence.
6. Only after that PASS/release, the single
   [controlled realtime move](captures/realtime-move.log) passed. The real old boot
   stopped; an actual checkpoint row held the replacement cold. The cold handshake
   returned 403 and handoff refused; actual publication pin exclusion and omission
   of an idle participant refused. B's timestamped frame and old-route-generation
   alarm continued while A warmed. Cutover admitted the ready new owner, the exact
   A/B nonce probes matched once in their intended slots, forbidden probes stayed
   absent, and checkpoint/session/connection/census checks passed. The final probe
   recopy followed all awaited census checks. Background clinical B notification
   traffic was captured separately and supplied no probe credit. The publisher
   exited 0 with completion observed and no stderr code; journal, backend and route
   generations finished complete/2/2. See
   [publisher summary](captures/publisher-summary.json) and
   [placement completion](captures/placement-completion.json). Raw child captures
   remain private under the owned project.

No failed phase was retried, no state was reset, and no deadline, cadence, threshold
or workload was changed. The native negative controls are retained alongside the
positive proof logs. Prior source/fixture ablations remain in their original homes;
this run did not duplicate unchanged source campaigns.

## Tested image export

The exact tested image was saved by ID after Config Env/history and committed
source-only build inspection, without rebuilding or pushing to a registry.
[Build attestation](captures/image-build-attestation.json) records only the public
build Env allowlist; no database/operator/Vault credentials are image Env inputs.
[Export attestation](captures/image-export.json) pins linux/amd64, archive config
SHA matching the actual image ID, 284444672 archive bytes and archive SHA256
`4358289c768ef758f9647bfd71d97b0bca62ff81879a9ca95c06d85c3dcfffa7`.
The mode-0600 archive remains private for the coordinator's custody/import process.
It is not a remote deployment or acceptance result.

## Limits and next boundary

The [original stock warming failure](../../api-readiness-continuity-2026-11-12/original/README.md)
and [original publisher failure](../../realtime-publisher-failure-2026-11-12/original-and-controls/README.md)
retain their failed/unclassified chronology. This fresh PASS does not retrospectively
assign either cause or relabel old images. The reproduced fixture repairs and
failed-repair controls are recorded in
[readiness controls](../../api-readiness-continuity-2026-11-12/readiness-fixture/README.md)
and [move controls](../../realtime-publisher-failure-2026-11-12/final-tail-controls/README.md).

The already closed quiet idle-safety smoke was not repeated. Its old 2d/dcc/b16
attribution stays historical; the coordinator's
[joined input comparison](../../api-readiness-continuity-2026-11-12/joined-candidate/closure.json)
is read-derived support for that narrow reuse, not a fresh quiet run, strict TIME
substitute or future pilot idle result. This run did exercise fresh strict TIME
before the move; the move's normal B write changes later scheduling conditions.

All captures are synthetic and were checked against the private seeded credential
carriers/root secrets before publication. [sha256.json](sha256.json) pins the
capture bytes. The coordinator now owns comprehensive acceptance and any remote
image adoption/pilot; no cloud action occurred in this lane.
