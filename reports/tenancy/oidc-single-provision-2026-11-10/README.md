# MT-OIDC-SINGLE-PROVISION: single-site OIDC identity list, fallback role, current subject roles, local signing (2026-11-10)

*Measured record, contributor-facing, captured 2026-11-10; not edited after capture.
Operator-facing summary in section 7.*

## 1. Anchors

| tree | ref | sha |
|---|---|---|
| base (draft PR #8898 head) | `workspace/multitenant-20261102` | `dc795bd1515f11808a8d0732f2be9925cb2ffcd1` |
| lane branch | `codex/oidc-single-provision-20261110`, worktree `externals/work/crm-oidc-single-provision-20261110` | head `4b81f59d3865b0bb649276b25cf51e402c3d1bc4` |
| `official/dev` | | `4a482627bfdafb1fef8dcbe0ac6c484811cae563` |
| alignment `main` at writing | | `3259787103b8a8d5a6ed4b193422dc868b127602` |

Lane commits on top of `dc795bd1` (18 files, +996/−97): `c2869b89` implementation and tests;
`61af8beb` README for `lib/human-session`; `4b81f59d` end-to-end `runtime.single` test (test file only).
Nothing pushed.

## 2. Criteria

| # | criterion | status | where |
|---|---|---|---|
| 1 | `OIDC_ACCESS_CONFIG` inline JSON or `OIDC_ACCESS_CONFIG_FILE` path; both set refuses at load; existing path form keeps working | fixed (branch) | `lib/human-session/private-setting.js`, `access-config.js` |
| 2 | single-site local Ed25519 signer from env/file; issuer, audiences, kid derived; Vault optional for single-site; multitenant unchanged | fixed (branch) | `lib/human-session/local-signing.js`, `provision.js` (key acceptance) |
| 3 | principal binds to an auth subject and takes its current roles; snapshot removed | fixed (branch) | `lib/human-session/mongo.js`, `subject-roles.js` |
| 4 | identity list keyed on issuer + provider subject; email only when the same issuer marks it verified; listed = exactly its roles; unlisted = fallback only; edit effective next request | fixed (branch) | `identity-list.js`, `provision.js`, `mongo.js`, `engine.js`, `provider.js` |

## 3. Design points settled in-lane

1. **Config sources.** `NAME` inline or `NAME_FILE` path, exclusive, for `OIDC_ACCESS_CONFIG`,
   `OIDC_ACCESS_SIGNING_KEY`, `OIDC_IDENTITIES`. An `OIDC_ACCESS_CONFIG` value not starting with `{` is
   the earlier path form and is still read. Local key and access JSON together refuse. Operator-written
   refusals carry `code: OIDC_CONFIGURATION_INVALID`; `bootevent.js` now shows those messages (they
   name settings and role names, never values, keys or file content) instead of the fixed string.
2. **Local signing.** One Ed25519 PKCS#8 PEM; data and management keys derived with HKDF-SHA256
   (salt `nightscout-human-access-local-v1`, info = purpose) because `createHumanAccess` requires distinct
   key material per purpose. `kid = local-<purpose>-<22 chars of sha256(spki)>`. Issuer
   `nightscout-human-access:<OIDC_ORIGIN>`, audiences `nightscout-human-{data,management}:<OIDC_ORIGIN>`.
   At start the kids are written as accepted keys (`source: 'local'`); a kid no longer configured is set
   inactive, so a key change ends existing access at the next request. Local key in multi mode refuses.
3. **Current roles.** A principal's `subject` is an auth subject `_id`; `roles.forSubject` reads
   `<prefix>subjects` and `<prefix>roles` (stored over shipped defaults) at every operation, in every
   process. A missing subject grants nothing. The role read is outside the authority-document CAS: a role
   edit racing one in-flight operation applies from the next (the PostgreSQL adapter reads both in one
   statement; this is a read-derived difference, not measured as a race).
4. **Migration.** `lib/human-session` is not in `official/dev` (preview only, #8898), so no operator
   database holds principals. A stored `permissionGroups` field is ignored; such a principal grants only
   through its subject (test "migration": a `[['*']]` copy grants nothing).
5. **List semantics: authoritative for what it manages** (Grafana/Kubernetes-style declarative
   provisioning). Each entry gets a deterministic subject `_id` (sha256 of the binding id, 24 hex) so
   concurrent starts write the same rows; roles re-applied at each start; an entry removed from the list
   has its subject deleted first, then its binding removed (an interrupted start finishes the removal next
   time, no orphan subject). Bindings not created by the list are untouched; a list entry colliding with
   one refuses at start. Unknown role names refuse at start before any write. Between starts the database
   governs. **Open for the maintainer, see section 6.**
6. **Email.** Email bindings are a separate id namespace `hash([tenant, issuer, 'verified-email', email])`.
   The provider returns `email` plus `emailVerified` only for a boolean `email_verified === true`; the
   session keeps the address only if verified; renewal replaces it with the issuer's current value.
   Case-insensitive compare. The `email` scope is requested only when an email entry exists.
7. **Fallback.** `OIDC_FALLBACK_ROLES` (unset = refuse, the pre-lane behaviour; not a changed default).
   Data purpose only; per-person derived subject `oidc-<40 hex>`; no binding stored. Fallback sessions
   share at most 32 of the 128 slots and the oldest is evicted, so strangers cannot exhaust capacity for
   listed people.

## 4. Measurements (reproduced, from tool output)

| check | tree | result |
|---|---|---|
| baseline human-session suites (`tests/human-*.test.js`, vault-token-file-sources) | `dc795bd1` | 163 passing |
| same after the lane, plus provision tests | `4b81f59d` | 188 passing, 0 failing |
| `tests/human-session-provision.test.js` (actual MongoDB 7.0.43, actual authorization storage) | `4b81f59d` | 24 passing |
| ESLint `lib` + changed tests | `4b81f59d` | 0 errors; 49 warnings, none in changed files |
| `test:all` tiers unit / dom / dependency / core / harness | `61af8beb` | 3073 / 205 / 368 (2 pending) / 319 / 99 passing, 0 failing |
| integration, stress (re-run after the MongoDB container hit EMFILE; see handoff traps) | `4b81f59d` | 3618 passing, 534 pending, 0 failing / 18 passing; exit 0 |
| OIDC nine-stage native matrix `tests/native/oidc-matrix/run.sh` | `61af8beb` | 9/9 PASS, complete, 15755 ms, zero leftovers (`matrix-stages/`) |
| harness controls `--control single:single-current-subject-resolution-bypass,browser:logout,consumer:consumer-current-data-authority-bypass` | `61af8beb` | 3/3 red then green (`matrix-controls/`) |
| gate `tools/queue/gates/oidc-native-recorded.js summary.json` (combined stages + controls, same commit) | | 13 checked, 0 failing |

Gate cases from the queue item, all in `tests/human-session-provision.test.js`:

| gate | test |
|---|---|
| listed identity gets exactly its roles | "binds issuer + provider subject…": permissionGroups deep-equal `[careportal, readable]` |
| unlisted gets only the fallback | "fallback readable…": `[readable]`, no create, management refused |
| edit takes effect next request | "an admin-UI role edit…", "a stored role overriding…", "a disabled binding…", "a restart with the entry removed…" |
| CONTROL second issuer, same email | "CONTROL: the same verified email from a second issuer…" |
| CONTROL unverified email | "CONTROL: an unverified email at the listed issuer…" (false and absent) |
| end to end through `runtime.single` + HTTP routes | "boots from settings alone…": listed, email-listed, `email_verified: "true"` string → fallback, stranger → fallback |

## 5. Break-it controls (lane, `lane-controls/controls.json`)

Each mutant applied to the committed tree, targeted test run, restored with `git checkout`, tree clean.

| control | mutant | red symptom | restored |
|---|---|---|---|
| C1 | email key without issuer (`mongo.js` `emailPrincipalId`) | second-issuer test: `strictEqual` at test:215, second-issuer sign-in got `api:treatments:create` | 1 passing |
| C2 | email matched without `emailVerified` | unverified test: `HUMAN_AUTHORITY_REFUSED` thrown (login bound the listed subject, token path then mismatched) | 1 passing |
| C3 | snapshot reintroduced (provision writes `permissionGroups`, store prefers it) | 4 of 8 "next request" tests red: role edit (:135), stored-role override (:144), removed subject still accepted, migration copy `[['*']]` granted | 8 passing |
| C4 | unmatched identity takes `principals[0]` | fallback test: deep-equal shows `api:treatments:create` group present | 1 passing |
| C5 | `NAME`/`NAME_FILE` exclusivity removed | "together refuse at load": validation returned false, got `Invalid explicit human access issuer configuration` | 1 passing |
| C6 | fallback session share removed | capacity test: fallback session count ≠ 32 at :122 | 1 passing |
| C7 | provider never requests `email` scope | e2e: `'openid'` !== `'openid email'` | 1 passing |

Harness controls (exact messages from the stage stderr): `single-current-subject-resolution-bypass`
FAIL 789 ms "single removed subject JWT: actual known route must refuse", restored PASS 2063 ms;
`browser:logout` FAIL 1603 ms "owner transport status oracle 200 !== 401", restored PASS 4726 ms;
`consumer-current-data-authority-bypass` FAIL 2519 ms "next DATA operation must read current role
authority", restored PASS 2581 ms.

## 6. Open decision for the maintainer

**List authoritative vs. database wins at start.** Mechanism: `lib/human-session/provision.js`
re-applies listed roles to the list's subjects and removes bindings (and their subjects) whose entries
left the list, at every start. Trade-off: chosen behaviour means editing the file always takes effect at
restart, and removing someone always removes access; the cost is that an admin-UI role edit on a
list-managed subject lasts only until the next restart (the subject's notes say so). The alternative,
"seed only what is missing" (closest to how default roles fill gaps), keeps admin edits but means a
role change or a removal in the file does nothing for an existing entry, which leaves access in place
after an operator thinks it is gone. Recommendation: keep list-authoritative (safety on removal,
predictability, matches declarative provisioning). Single-site only; multitenant is unaffected.

Smaller points for review, not blocking: each list subject has the derived legacy access token every
subject has (same roles, visible in the admin UI); a renewal whose fresh proof no longer matches returns
a token that the next request refuses, rather than refusing the renewal itself.

## 7. Operator summary (plain language)

When sign-in is turned on (`ENABLE=oidc`), a single Nightscout site can now:

- **Say who may sign in and what each person may do**, in one setting or one file. For example
  `OIDC_IDENTITIES=sub:248289761001=careportal+readable,email:carer@example.test=readable` lets the
  first person read and enter treatments, and the second only read. A person is matched by the
  account ID your sign-in provider gives them, or by their email address only when that same provider
  confirms the address is verified. The list can also be a CSV, TSV or JSON file
  (`OIDC_IDENTITIES_FILE`). Role names must already exist (for example `readable`, `careportal`).
- **Choose what anyone else who signs in can see** with `OIDC_FALLBACK_ROLES`, for example `readable`.
  Leave it unset to turn away people who are not on the list. Anyone with an account at your sign-in
  provider can reach the fallback, so choose it as carefully as `AUTH_DEFAULT_ROLES`.
- **Change access without restarting**: each listed person appears as a subject in the admin page, and
  changing that subject's roles there applies at their next request. At the next restart the list is
  applied again, and anyone removed from the list loses access.
- **Run without Vault**: set `OIDC_ACCESS_SIGNING_KEY` (or `OIDC_ACCESS_SIGNING_KEY_FILE`) to a private
  key made with `openssl genpkey -algorithm ed25519`. Keep it secret like `API_SECRET`. Replacing it signs
  everyone out. Multitenant sites keep using Vault.
- Settings are never both inline and as a file: setting `X` and `X_FILE` together stops sign-in from
  starting, with a message saying so.

Nightscout shows CGM and pump data as a secondary display; these settings only decide who can view or
enter data on your own site.

## 8. UNMEASURED / not established

- prcheck, `test:browser`, and the multitenant enabled corpus on this branch: not run (coordinator's
  frozen-candidate campaign).
- The harness Mongo stages (`mongo-sessions`, `mongo-http`) use an in-memory roles double for the
  bound subject; actual subject/role collections are exercised by `tests/human-session-provision.test.js`
  (actual MongoDB), not inside the harness.
- A role edit racing an in-flight operation (section 3.3): read-derived, not measured.
- Real OpenID provider interoperability (email claim placement in ID token vs userinfo, `email_verified`
  types): synthetic provider only. Providers that put `email` only in userinfo will not match email entries.
- Concurrent starts of several processes provisioning at once: deterministic ids and the revision CAS are
  read-derived as safe; not measured with parallel boots.
- Pre-existing, not changed: data sessions are never pruned, so a listed person who signs in 33 times
  without signing out is refused for capacity (`mongo.js` per-principal 32). Read-derived.
