# Internal service contracts and private transports — 2026-11-09

The internal API refactor is **fixed on a local branch**. It separates service
contracts from transport and keeps private operations on independently bound
listeners. Incorporation and release-candidate acceptance remain with the source
integration owner under `MT-M6A-JOIN`; this report does not promote that item.

## Source and scope

| Anchor | Measured value |
|---|---|
| Application branch | `codex/internal-service-api-20261109` |
| Application commit | `dc795bd1515f11808a8d0732f2be9925cb2ffcd1` |
| Parent candidate | `0fc5abf99ec34b80eba9f482c5cc197c51c737f9` |
| Fetched `official/dev` | `4a482627bfdafb1fef8dcbe0ac6c484811cae563` |
| Alignment source before this record | `928a2d43ef7379a86aca2ac762941e7ea7c5abc2` |

**Read-derived architecture:** `lib/server/internal-api/transport.js` replaces
`lib/server/realtime/ipc.js`. Separate executable service descriptions enumerate
`socket-authority`, `alarm-delivery` and `lifecycle-participant` operations, JSON
Schema requests/responses and named clients. The listener requires exactly its
contract's named handlers. Only exact contract paths dispatch; the request URL
cannot choose another service or arbitrary property. No raw HTTP request is
passed to domain handlers.

Unix sockets retain the protected directory, same-UID and owned-inode model.
HTTP accepts explicitly configured origins, including DNS, link-local and private
addresses, with a separate optional bind address and explicit `trust: network`.
Deployment owns HTTP reachability. No bearer credential convention was added;
service/version headers identify contracts and are not credentials. Existing
public routers do not mount these private operations. Each internal contract
opens its own server/socket or HTTP port.

Existing UDS configuration remains valid. Environment-reference endpoint
alternatives are available for API socket forwarding, realtime API/alarm
endpoints, evaluator notification routes and lifecycle participant endpoints.
Application documentation and curl examples are in `docs/internal-service-api.md`
on the application branch. Communicating processes require a coordinated upgrade
because missing or mismatched service/version headers are refused.

## Focused measurements (reproduced)

Tests ran on the unchanged working tree subsequently committed as the application
anchor above. The UDS capture's causal-file hashes were compared with `git show
HEAD:<path>` after committing; every captured causal file matched.

```bash
node_modules/.bin/mocha tests/internal-api-*.test.js tests/realtime*.test.js \
  tests/operation-cohort*.test.js tests/profile-wire-response.test.js \
  tests/human-session-stream.test.js tests/tenant-startup-admission.test.js \
  tests/evaluator-consumer*.test.js tests/evaluator-control-readiness.test.js \
  tests/compose-deployment-protocol.test.js tests/multitenant-inventory.test.js \
  --timeout 10000 --reporter dot
```

Result: **204 passing, 5 pending, no failing tests**. The pending tests did not
execute and are not counted as passes. Coverage includes current socket
authority, canonical mutation/ACK paths, human session streams, tenant startup,
operation-window lifetimes and restore participant identity checks, plus the new
service/schema/endpoint and public/private mounting controls. Storage/domain
preparation is mocked in the public-listener isolation test; that test establishes
router separation, not database authorization.

| Check | Result and limits |
|---|---|
| Actual UDS and HTTP listeners | Named calls succeed; raw foreign-service, unknown/query/encoded/prototype paths, bad versions and malformed bodies refuse before effects. Response validation is also exercised against an independently implemented peer. |
| Public/private isolation | Actual `preview-api` boot and tenant router: internal paths return 404 without private effects on the public port; the named authorization call succeeds on a distinct private port. |
| Existing `early.js --execute uds-ownership` fixture | Pass: preexisting file/symlink/socket refusal, publication replacement refusal, ordinary owned cleanup, replacement-inode preservation and disposable-directory cleanup. Only generated scratch endpoints used. |
| Changed-code ESLint | Exit 0: 0 errors, 24 warnings (filesystem calls and checked-in schema regular expressions). |
| `git diff --check` | Pass. |
| `node scripts/test-tiers.js check` | Pass: 609 files across 8 tiers. |
| `node scripts/test-multitenant.js --list` | Inventory/list validation only; execution of the enabled corpus remains unmeasured here. |

Alignment record validation: `make queue-check` passes manifest validation,
register coverage and generated-view/packet freshness, then fails its link gate;
`make docs-links` reports the same six failing references. Each points to the
existing missing `claimed-public-names-and-deploy-companion-2026-11-09.md` document.
Those references are present in the alignment source commit above. The document
exists only as another lane's untracked file in the shared checkout and was not
copied or staged by this lane. Integration must include its owner's record before
these whole-repository checks can pass.

The sandbox initially refused listener creation and git subprocesses with
`EPERM`; those setup failures did not exercise product behavior. Permitted runs
with disposable listeners produced the results above. An earlier default Mocha
timeout failed the renderer diagnostics test; the repository-scale
`--timeout 10000` campaign passed without a renderer change.

## Meaningful controls (reproduced)

The committed tests retain scratch-VM mutations and exercise the real guards:

| Disabled property | Exact observed symptom | Restored result |
|---|---|---|
| Unknown-field schema rejection | The schema assertion throws `Missing expected exception.` when the additional-property guard is disabled. | The original schema rejects the extra field. |
| Service identity fence | A raw request naming another service returns HTTP 200 instead of required 503. | The original listener refuses the request. |
| Public/private router separation | A deliberately injected public `/authorize` route returns HTTP 200 instead of required 404. | The original public app returns 404 and the private listener remains callable. |

These are semantic reds: each mutation reaches the intended branch and changes
its response. They do not modify any shared checkout. Existing authorization and
lifecycle controls remain in their migrated suites rather than being replaced by
schema checks.

## Integration boundary

Full database/nonbrowser tiers, default-browser, enabled multitenant corpus,
pinned-client/native application acceptance and remote CodeQL are **UNMEASURED
for this refactor**. Run the applicable affected acceptance on the coherent
joined candidate before treating it as ready. Local HTTP tests establish
transport behavior, not Kubernetes deployment or multi-host restore admission;
the existing lifecycle datastore/backend and pinning rules still apply.

The source integration owner should merge the original lane history into the
existing candidate for draft #8898, preserving the current authorization,
isolation, clinical and compatibility acceptance matrix. No push, PR creation,
merge to `dev`, release or default enablement occurred in this lane.

Local detailed handoff: `externals/work/HANDOFF-internal-service-api-2026-11-09.md`.
