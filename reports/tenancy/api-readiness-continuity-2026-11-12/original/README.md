# Original B settings continuity failure

Captured 2026-11-12. **Stock/restore fixture FAIL; cause unclassified.**
Core `2d0ae0354a38b4a88f43bc2ae5ec60c085058f64`, deployment
`dcc4a70bafd4edf31c5cab4bf3099883bd7e37f9`, image
`sha256:b16e338214d19a409333a079a3950cb97eed9cd7cc00b5eacbff28e4bd72054d`.
Alignment/instrument c33acdc48208586354002573b93ce4f33d6c0c6a /
52c76f7500312bc3ce8006f3783444b04489bdf53cd1f764417f77cf8333ba1d (37files).
Fresh project/state `ns-evaluator-binding-proof-20261112-idle`, port18382, nonce
`a8d9cc6f-2c1a-4749-8bf4-b350cc39a4bf`; explicit 2API/2RT/shards2/3EV initially
member2, Vault SERVER, diagnostics OFF. [Exact identity](captures/identity.json).
No retry, reset, source overlay or current-state repair followed the failure.

The [original test output](captures/stock-failure.log) fails after11370.12ms on
strict B settings traffic health: three responses classified
`B_SETTINGS_STATUS_503_TENANT_WARMING`, where zero errors were permitted. The
original loop records no request start/end time, upstream replica or precise
pre-restore/measured-stage identity. The failure remains unclassified; a later
healthy role or initializer completion cannot retroactively explain or pass it.

The prior [startup check](captures/startup-ready-defaults.json) established both
evaluator owners initialized and ready, all15 roles running/13health checks,
and edge-routed A123/B177 read values. It did NOT establish every API×tenant
status cell initialized. A separate once-only new quiet idle-safety capture
passed before stock:21.0543s,9RPC, both owners TIME_NOT_EXERCISED/FUTURE_DUE,
zero time completions/timeWitness:false, stable identities/foreign rows. That is
not strict native TIME, a120-second pilot or this continuity criterion. Its
primary evidence belongs to the independent collector lane.

## Read-only chronology and limits

[Safe classification](captures/typed-chronology.json) was captured from timestamped
private API logs, current role identity and the restore demo's final JSON, without
issuing new HTTP warming requests or changing roles/state.

- API1 logged ready1/failed0 at17:25:16.685; ready2 was not logged until
  17:31:32.223. API2 had logged ready2 since17:25:13.626.
- Both roles logged ready1/deferred1 around17:31:34.438, then ready2 by34.615.
  Failed stock log modification time was17:31:35.359.
- The internal restore demo artifact reports state passed and
  bCommittedDuringRestore:true. The outer settings assertion nevertheless failed;
  its later B152-frame/same-session assertions were not reached.
- Warm log `loggedAfterMs` is boot-relative after-ms, not a measured individual
  tenant initialization duration. Global current role health is not historical
  per-tenant warmth; no tenant ID is attached to the ready-count log.

These facts support, but do not prove, the read-derived cold-replica precondition
hypothesis: initial serve-ready roles may initialize a tenant on its first request,
and edge-routed setup may not touch every replica. They do not assign the three
warming responses to a replica/tenant cell or to before/during the restore.
No initial warm-state cause is established or excluded merely by counts.

The source fixture starts four settings readers, breaks a worker on its first
error and starts restore once aggregate successes reach four. It retains neither
per-worker initial success nor direct per-replica initialization proof. Hence
its original capture cannot distinguish cold setup from a measured continuity
regression. Source-only controls and a bounded explicit precondition must be
evaluated before prescribing a fixture-only repair. Any warming/error during the
claimed measured interval must remain a failure; blanket retries or longer
measurement deadlines would not resolve this evidence gap.

## Next boundary

Settings authority controls, strict clinical2-to3, second strict native TIME
capture, controlled realtime move and image export were NOT_RUN. The current
state already contains stock/demo mutations and is retained evidence, not a
fresh baseline to reset/replay. Parent's subsequent coreff515 assertion-only fix
does not relabel this actual2d image/result. All new source/deployment/image
qualification waits for the coherent coordinator boundary. No product fix or
clinical scheduling cause is claimed here. No full/browser/corpus/capacity
acceptance is claimed by this failed fixture.

Capture hashes: [sha256.json](sha256.json). Full timestamped API logs remain
private0600 in the owned state; published captures contain synthetic typed data
and source/image identity, no credentials or raw request/event payloads.
