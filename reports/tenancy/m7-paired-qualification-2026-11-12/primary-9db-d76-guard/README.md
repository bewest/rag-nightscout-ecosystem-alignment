# Primary 9db/d76 native qualification and exported image — 2026-11-12

Reproduced: the new primary image passed the bounded clinical 2→3 handoff. Its first strict TIME observation was **UNMEASURED**, after a finite clinical episode had aged beyond the source freshness boundary. A separately authorized fresh-input episode on the same image established new acquisitions and finite due work; its separate strict TIME observation passed. The exact image was then exported with actual process exit 0. The original unmeasured observation remains unchanged.

## Exact inputs and scope

- Core `9db0ce94f072c8f34aab889f0181afa4269a6758`; deployment `d76ef17878edb610cdeae75aeef9c07f94b60753`.
- Image `sha256:293a5c531faac6c156305159246e39defd2592612c302af275efe807102a6d3e`, `linux/amd64`; new project `ns-evaluator-binding-proof-20261112-guard`, port 18385, nonce `77e7ad81-37b7-4ff2-8cb4-531327b4dbf1`.
- Two API instances, two realtime workers/two shards, three evaluator participants with desired membership 2→3, Vault SERVER, diagnostics OFF.
- Build/startup/configuration/clinical: alignment `5d7fa02746f4695a222f1fc400dc59b61a8c717e`, instrument `52c76f7500312bc3ce8006f3783444b04489bdf53cd1f764417f77cf8333ba1d` (37 files).
- Both later TIME observations and export: alignment `df18100cf13780cec904a792b2bb1ab8867bfb54`, instrument `63844506159ee61f2335d8e94694a21cc48bc558b36f8146d8eb968ebdfa4f6d` (40 files). The admission-contract engineering changed no application/core/deployment bytes.

This is minimal new-primary qualification. Previously qualified stock/restore, realtime move, settings negative, quiet and client proofs retain their original image/source scopes. None was replayed or relabeled. No capacity, 120-second pilot, unlimited freshness, or unchanged normal-data workload claim follows from these synthetic episodes.

## Startup and clinical result

[processes.json](processes.json) retains directly observed exits for all 18 phases, including export; all are 0. It derives from the original process recorder, not TAP inference. [api-readiness.json](api-readiness.json) proves every API×tenant tuple through actual status middleware, with exact instance bookends. Two typed warming responses occurred only during the allowed precondition, before the strict clinical interval.

[clinical.log](clinical.log) records actual 2→3 membership, three accepted normal effects (initial A400/B400 plus intentional B401 change), zero cancelled/clear rows, typed fanout/checkpoint/current consumer/B-same-session assertions and 1136ms handoff versus 30000ms lease. The initial socket setup recorded transient transport errors and successful existing reconnect behavior; the original successful predicates/deadlines remained unchanged. Thirteen bounded durable observations ended with accepted rows and A1/B2 fanout. Clinical process start/finish were 1794515114134/1794515122142.

## Original TIME remains unmeasured

Primary API-owned leaf: `reports/tenancy/evaluator-trusted-scheduling-2026-11-12/native-9db-d76-guard-unmeasured/README.md`, commit `b942e5b2aa3092987bbcdf8d9460edf1e37e69e0`. Raw SHA256 `142a2c21f0d68512ca6ffd918eb399dfbee38eef1782b9e837288c13763419d2`; supervisor exit 1. Both owners were ready with unchanged completed-time counts, null due/reason, no queued jobs or failures. This was neither a successful TIME witness nor a measured runtime stall.

Captured-only [chronology.json](chronology.json) places first TIME read 1,209,297ms after clinical finish. Exact original uploaded sample dates were **UNCAPTURED**; the fixture used `Date.now()` and awaited uploads within that phase, so finish is an upper bound. At capture, even the latest possible sample had exceeded its 600000ms freshness boundary by 609297ms. Source at the exact core: `lib/plugins/simplealarms.js:21` requests alarms only for age <10 minutes; `lib/data/evaluator-due.js:80–81` schedules that boundary and line149 adds slow alarm-message work only while notify is requested. Last-completion ages align with that finite episode ending. This supports expiry of the work opportunity during the engineering hold; it does not establish causes for any older failures.

## Separate fresh-input experiment

Root explicitly authorized a new experiment, not a retry or extension of the sealed window. [fresh-ingestion.cjs](fresh-ingestion.cjs) used the existing shipping JWT/HTTP upload logic exactly once per synthetic tenant: A400 and B401, current timestamps and unique synthetic identifiers. No settings, seeds, cadence, clock, plugin, membership, database SQL writes or image changed. [fresh-ingestion.json](fresh-ingestion.json) records both exchanges 200 and uploads 201, safe input markers, request start/end, directly observed read exits, and before/after owned state. The supervisor [process record](fresh-ingestion-process.json) is actual exit 0.

After input, both owners advanced completed acquisitions 1→2 and checkpoints, retained runtime/generation identity, and declared future `slow:alarm-message` due work. External writes ended at 1794517026623; opportunity was established at 1794517027786. Bounded precondition inspection used 12 RPCs over the exact three evaluator listeners. It did not trigger work or alter strict collector policy.

Primary API-owned positive leaf: `reports/tenancy/evaluator-trusted-scheduling-2026-11-12/native-9db-d76-fresh-ingestion/README.md`, commit `739cb3111b1139503121019bedd82d0b196f4d2f`. Raw SHA256 `1e43a6c80f5924673f59d9b1881fb7c1623f4ed88aa546fed6db74aeccc934ab`; actual supervisor exit 0. The separate unchanged strict assay observed 38 successful time completions, minimum 19 per owner, no failed-completion delta, stable identities and unchanged foreign rows: nine RPCs/20130 encoded bytes over about 21.24 seconds. No extension or further write was used during that observation. Original UM artifacts were rehashed unchanged before export.

## Image custody

[image-export.json](image-export.json) binds the exported exact image only to the new positive experiment. Archive: `/tmp/ns-evaluator-binding-9db-d76-export/image.tar`, 284444672 bytes, SHA256 `4eb4e791f5c2fa0cce8ad135cf02cfa2723e869d2b465555681d657f92559461`. The archive config digest equals the image ID, source labels match core/deploy, and source-only Git archive build context plus image Env/history checks passed. Only expected build Env keys were present. No registry push occurred. [export driver](export-driver.py) and [export log](export.log) preserve the executed checks; private image inspection and archive stay local.

Before activation, the owned prior SOURCE15 roster was identity-verified and stopped, retaining containers/volumes/images/state. Only the specifically authorized two empty READY networks were removed after archival and canonical fail-closed checks; [custody.json](custody.json) records the final 15-container preservation comparison. Original network IDs cannot be restored; restarting that old project would require replacement networking. No foreign cleanup or global prune occurred. The current GUARD15 remain running and retained; this report authorizes no additional lifecycle action.

[capture-sources.json](capture-sources.json) identifies originals/derivations; [sha256.json](sha256.json) seals captured files. All data are synthetic. No credentials, private environment, raw request URLs or raw clinical message bodies are published.
