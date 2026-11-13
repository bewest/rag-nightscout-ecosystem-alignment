# Independent readiness-fixture review

APPROVE final deployment 8f92e63c3bb4041325428763b4caccba62f4c404, original
history dcc4→91781fe→85cc173→3235c287→8f92e63. Reviewed immutable Git archives;
peer source stayed untouched. Actual carrier tests used owned exact core
ff5156b984424f1ef34bcef22d5bfa0071354cfa with this lane's prior same-lock
dependencies (not a new install). No live project, Docker command, database,
Vault, source edit, native activation or original-run retry occurred.

The exact API×seed-tenant precondition precedes sockets, JWT exchange and other
strict cold-sensitive HTTP. It uses the actual opaque DATA api-secret/status
carrier, not a credential/authority bypass. Only explicit typed 503 TENANT_WARMING
is retried in the shared 20 s request phase; other failures terminate. Metadata and
cleanup commands have separate explicit bounds. The bare private client receives
three read-only fixture/input mounts and a short-lived 0600 credential file, with
no operator/DB/Vault/IPC configuration. Artifact fields exclude credentials, raw
request URLs and response bodies. Source/current running/project/service/workdir
identity is checked before and after readiness; post-checks occur after client
cleanup awaits, comparing CID, StartedAt and image and retaining partial evidence
on change. This is identity bookending, not a continuous uptime guarantee.

The original four public-edge B readers remain eager and strict, without retries
or an extra pacing interval. Each must succeed before restore begins; accumulated
errors are checked before spawn and afterward. Upstream API identity remains
explicitly UNKNOWN for measured edge traffic. Request tails/failures/stages are
bounded and redacted. Failed transports and HTTP refusals each retain exactly one
attempt per worker, with stage/start/end/duration/status/code.

## Reproduced review findings and controls

1. Original 917 private read mapped every parsed 200 JSON to success. Actual
   read→precondition with 200 error JSON passed incorrectly; the owned control
   fails INVALID_STATUS_200_FALSE_PASS. 85cc now requires a nonarray status-ok
   object with no error field. Its real read→engine invalid-body controls refuse.
2. Original 917 host inspected targets only before requests. A recording replacement
   during readiness returned an old CID/StartedAt with a success matrix; the owned
   control fails STALE_TARGET_IDENTITY_FALSE_PASS. 3235 post-cleanup inspections
   refuse replacement/restart/image/source/stopped targets. The coordinator also
   independently replayed both original false-passes and corrected refusals.
3. 3235 measured transports failed strictly but lost attempt chronology (four errors,
   zero request rows). Final 8f92 catch-only recording adds one safe row when no
   HTTP response was already recorded. The new test is RED on original 3235
   (MISSING_TYPED_MEASURED_REQUEST; 10 pass/1 fail), restored 11 pass; HTTP 503 remains
   one row rather than duplicate catch logging. No failure was changed to success.

Own focused3235 carrier/host/engine/order union: 23 PASS, 0 skip, including the actual
source credential derivation, tenant middleware/status handler, invalid/wrong-
tenant/current-authority refusal and warming-before-handler cases. Final 8f92
narrow engine: 11 PASS, 0 skip. No comprehensive campaign was repeated. Node v22.23.4.
All Docker operations in host controls were recording fakes; actual carrier checks
used disposable local HTTP listeners, not the retained native stack.

The [original failure](../original/README.md) remains unclassified as to its exact
request timing/upstream/cold tenant. The [source-only cold precondition](../cold-precondition/README.md)
proves a possible mechanism, not that original cause. The original first quiet
capture stays attributed to 2d/dcc/b16/c33 and is not relabelled by this fixture
repair. A new final-image stock/settings/clinical qualification and strict native
TIME witness remain required under coordinator authorization.

Reproduce focused controls from owned binding/source archives with
NS_UI_TEST_CORE pointing at an exact ff515 source/dependency tree. Run the four
api-readiness test files directly or through node --test with local-listener
permission. The archived false-pass probes expect the reviewed binding917 tree at
`<owned-review>/binding`; the transport control pairs the final test with original
3235 observer bytes, then restores final observer bytes. Captures normalize only
owned absolute path prefixes. No source patch was authored by this reviewer.
