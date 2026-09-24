# iOS clients — join-step summary (from the agent's hand-back, saved by the main session)

Refs: NightscoutKit main 4ec9fd1; LoopWorkspace main f841285 (NightscoutService fe075ef, NightscoutRemoteCGM e2230e3, Loop c2fddb7, LoopKit 325bd82; next-dev differs: NightscoutService 5379bba, NightscoutKit ca8e2ce); Trio main c0160aeaf (dev e41c9db37 changes no Nightscout file); LoopCaregiver dev 2305718 (gestrich/NightscoutKit fork d63fb73, read from a clone outside externals/); LoopFollow main 4a74b781; nightguard master 75404bd; xdripswift master c268542e; DiaBLE main e6a909c; GlookoServiceKit (no Nightscout surface). All read-derived.

Clean: S1 counts are whole numbers >= 1 (24, 50, 100, 1000, 1152-5760, 1600, 2000; none on DELETE); S2 all on the allowlist, `$exists` only `true` (Trio); no `$expr`/pipeline; S9 no food; S12 max `$in` 50 (xdripswift DELETE); S13 v3 only nightguard, limit 1-500.

Data stops arriving:
1. Loop override DELETE `/api/v1/treatments/<UPPER-UUID>` — on error NightscoutService.swift:167-185 never calls completion; override queue hangs until relaunch. Join: 200 under the candidate (server-injected count=10 vs the new DELETE count check; non-hex uppercase `_id`, UUID_HANDLING on/off; #8758's non-hex 400 on "other v1 routes").
2. 400 on POST stalls Loop (batch <=1000, response length must equal request), Trio (<=100, debug log only), xdripswift (<=300; treats 500 with body code 66 as success). Join: nothing newly refuses Loop UUID `_id`/syncIdentifier, profile `mills` as string, Trio `id` field and fractional-second `created_at`, xdripswift random 24-char alphanumeric `_id`.
3. Trio `GET entries/sgv.json?count=1600&find[dateString][$gte]=…` — errors become "no new data". Join: still 200.
4. Trio `find[eventType]=Temporary+Target` — join: `+` still decodes to space under qs 6.16.
5. LoopFollow creates a subject {name, roles:[readable]} via POST /api/v2/authorization/subjects and derives the token from returned `_id`. Join: #8754 keeps `_id` in the reply and the token formula.
6. xdripswift `GET /api/v1/treatments?find[_id]=<X>&count=1`; empty answer marks the treatment deleted locally. Join: every id form (24-hex ObjectId, UUID with UUID_HANDLING on/off, case mismatch).
7. Loop caches `_id` from treatments POST response 24 h and PUT/DELETEs with it. Join: every element carries lowercase 24-hex string `_id`; PUT updates in place.
8. Socket under AUTH_DEFAULT_ROLES=denied: LoopFollow sends `authorize {secret: <access token>}`, treats `connected` as authenticated and slows REST polling. Join: token accepted in `secret`; what a denied socket receives. DiaBLE embeds the web page with `?token=`.

Wrong numbers:
9. nightguard shows Nightscout COB/IOB from /api/v2/properties. Join: does the COB-source change reach that endpoint?
10. New server COB reads loop.cob.cob (Loop) and openaps.suggested.COB / enacted (Trio). Join: both shapes read and dated correctly.

Cosmetic/setup: Loop setup check /api/v1/experiments/test (200 valid, 401 wrong); LoopCaregiver needs exactly 200 from /api/v2/notifications/loop (candidate returns 500 with fixed body on failure) and its opt-in /api/v2/remotecommands does not exist on the server (pre-existing); nightguard v3 `fields=` and sort tie-break; Loop/Trio accept only API secret (pre-existing).

Not analysed: LoopFollow EIO version (no Package.resolved); Loop next-dev override-delete path; server answers to joins.
