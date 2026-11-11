# nightscout-deploy Compose fixes from the 2026-11-11 capacity campaign

*Measurement record, captured 2026-11-11; not edited after capture. Contributor-facing. Synthetic
tenants only.*

| anchor | value |
|---|---|
| nightscout-deploy branch | `deploy/capacity-fixes-20261111`, head `4ebd7ef4eed282687592a6eb2d686e704b77c358` (worktree `/home/bewest/src/nightscout-deploy-capacity-fixes-wt`, not pushed) |
| base | `deploy/sync-0392acf9-20261111` `fe36212` |
| core | `0392acf97c720a7e121eea47a9d42a0c8dbe9e73` (#8898 batch join), unedited |
| Compose tree hash at head | `ee7927af16001e29100b9fdb8f9cab9ac4594d15` (recorded in `bindings/compose/SOURCE.md`) |
| image under test | `nsdeployfix:9fd2a81`, built by `demo.sh build` on the overlay; labels `org.opencontainers.image.revision=0392acf9…`, `org.nightscout.deploy.revision=9fd2a816…` (the commit before the SOURCE.md-only head; same Compose tree) |
| stack | project `nsdeployfix`, N=2 (demo default), port 18391; host 16 cores, other unrelated containers running |
| nginx | 1.27.5 at the pinned digest |

## Commits

| commit | fix |
|---|---|
| `8f9a97e` | 1 bootstrap failure detail; 2 compact role documents; optional config cap plumbing |
| `d3306bf` | 3 edge re-resolves upstreams (`nginx.compose.conf`); 4 start order; source checks and controls |
| `9fd2a81` | 5 overlay build path |
| `4ebd7ef` | `SOURCE.md` record |

## 1. Bootstrap failure detail (reproduced)

`bootstrap.js` printed `{"error":"COMPOSE_BOOTSTRAP_FAILED"}` for any error without a code. It now
prints one JSON line: the same `error` code, `detail` (the underlying message, `TypeError: ` prefix
for non-plain errors) and `at` (top three stack frames, `/opt/app/` stripped). Redacted from both:
URL userinfo, `password|secret|token=…` clauses, SQL `PASSWORD '…'`, Vault `hvs.`/`hvb.`/`hvr.`
tokens, JWT-shaped strings and hex runs of 32+ characters (the generated passwords). A unit test
feeds a synthetic connection string, password clause, Vault token and JWT and asserts none survives;
`duplicate key value …` is left intact.

Induced failure, real bootstrap container on a fresh stack (`NS_DEMO_TENANTS=0`, a deliberately
invalid input; project `nsdeployfixc`, torn down after each run):

| run | image | stderr |
|---|---|---|
| fix | `nsdeployfix:9fd2a81` | `{"error":"COMPOSE_BOOTSTRAP_FAILED","detail":"TypeError: NS_DEMO_TENANTS must be 1..10000","at":["tenantCount (deploy/multitenant/config.js:14:68)","Object.tenantIds (deploy/multitenant/config.js:17:24)","bootstrap (deploy/multitenant/bootstrap.js:101:20)"]}` |
| **control** (deploy `fe36212`, old bootstrap) | `nscap:0392acf9-fe36212` | `{"error":"COMPOSE_BOOTSTRAP_FAILED"}` (bare: red as expected) |
| restored | `nsdeployfix:9fd2a81` | identical to the fix row |

The over-cap case itself, offline (compact role files for N synthetic tenants run through
`plan.validateFiles`, the bootstrap's own validation, and printed with `bootstrap.report`): N=3000
gives `"detail":"cannot read valid preview JSON configuration","at":["invalid (…/lib/server/serve/preview-config.js:15:9)","load (…/preview-config.js:56:13)",…]`.
Core wraps its own "too large" message in that generic one, so the detail names the loader and the
frame, not the size; the size message is core's to improve.

## 2. Compact JSON (reproduced)

Role `config.json`, `env.json`, `operation.json`, `admission.json`, `evaluator-metadata.json` and
`ui/config.json` are written compact; `bootstrap/*` custody files and `ops/*` operator files stay
indented. The vault-agent overlay's rewrite of the api `config.json`/`env.json` is compact too.

- Live stack, N=2: every role file is 1 line; role files total 17,106 bytes against 23,283 if
  indented (26.5% smaller). `ops/config.json` stays 988 lines.
- Offline, synthetic documents with distinct keys (`plan.documents` → files → `plan.validateFiles`):

| N | indented total / api `config.json` | validate | compact total / api `config.json` | validate |
|---|---|---|---|---|
| 1000 | 2,457,591 / 639,124 | pass | 1,584,152 / 408,739 | pass |
| 2000 | 4,907,591 / 1,281,124 | refused | 3,165,152 / 820,739 | pass |
| 2500 | — | — | — | pass |
| 2600 | — | — | — | refused |
| 3000 | 7,357,591 / 1,923,124 | refused | 4,746,152 / 1,232,739 | refused |
| 5000 | 12,257,591 / 3,207,124 | refused | 7,908,152 / 2,056,739 | refused |

Reduction 35.5% from N=1000 up. With core's 1 MiB cap the limit moves from under 2,000 tenants to
between 2,500 and 2,600; 3,000 still needs a larger cap.

**Cap plumbing (off by default; read-derived, not run against a core that reads it):**
`NS_BOOTSTRAP_CONFIG_MAX_BYTES` on the bootstrap service (empty = off; integer up to 268435456,
otherwise `BOOTSTRAP_CONFIG_MAX_BYTES_INVALID`). When set, the bootstrap writes
`MULTITENANT_CONFIG_MAX_BYTES=<value>` into every role `env.json` and sets it for its own
`validateFiles`. **Variable name assumed** from the peer core lane; core `0392acf9` does not read it.
`load-env.js` (deploy tree) keeps its own fixed 1 MiB limit on `env.json`; at N=5000 the api
`env.json` is not among the four largest files (each > 800 KB compact), so it is not the binding
limit in this range (read from the size listing, not separately measured).

## 3. Edge after a role restart (reproduced)

nginx resolved `api`, `realtime`, `ui` once at startup. A role that comes back on a new backend
address got 502 until the edge restarted. The Compose edge now mounts `nginx.compose.conf`:
`nginx.conf` plus `resolver 127.0.0.11 valid=10s ipv6=off; resolver_timeout 5s;` and
`zone … 64k; server <name> resolve;` per upstream. `nginx.conf` is unchanged, because the
Kubernetes binding imports it byte for byte (`lib/ns/nightscout.libsonnet:509`) and 127.0.0.11
does not exist there; `check-compose.js` holds the two files equal apart from those lines (golden
render still current). Locations, header stripping, websocket upgrade and security headers are
unchanged: Socket.IO polling 200 and a Socket.IO client connected over `transport=websocket`
through the edge; same polling/upgrade/header results with the old and new edge.

Probe: one tenant, `GET /api/v1/entries.json?count=1` with its synthetic token through the edge every
100 ms, 3 s client timeout. Times from the restart command's start.

| case | address changed | back to 200 | after api healthy | non-200 seen |
|---|---|---|---|---|
| `compose restart api` alone | no | 1.3 s | before healthy event | one 503 |
| api stopped, old address held by a placeholder, api started (×5) | yes | 3.3, 6.4, 3.3, 6.4, 6.4 s | 0.07–3.2 s | 0–1 × 502, 1–2 transport errors |
| `compose restart api realtime evaluator tenant-admin` (campaign shape, ×2) | yes, shuffled | 3.4, 1.7 s | 0.8, −0.9 s | 22 / 4 × 502 |

The 3.2 s tail is one request in flight to the old address hitting the 3 s client timeout.

**Control** (old `nginx.conf` mounted through a scratch override, api on a new address): no 200 for
the whole 34 s window (3 × 502, 10 × client timeouts at 3 s, nginx dialing the vanished address);
three `curl`s after the window: `502 502 502`. `compose restart nginx` (0.5 s), then the edge
reached api again (401 without a token). Red as expected. **Restored** (`nginx.compose.conf`):
back to 200 at 6.4 s.

## 4. Start order (reproduced)

`depends_on: service_healthy`: api waits for postgres and vault; realtime for api; evaluator for
realtime; tenant-admin for postgres, vault and api; nginx for api, realtime, evaluator,
tenant-admin and ui. Events from `docker events` during `run --rm bootstrap` then `up --wait`
(seconds from the first start):

```
 0.00 postgres start      2.06 postgres healthy     0.01 vault start   2.10 vault healthy
 2.68 bootstrap start     5.86 bootstrap exit
 6.29 ui start            8.40 ui healthy
 6.80 api start           8.91 api healthy
 9.43 realtime start     11.53 realtime healthy
 9.44 tenant-admin start 11.53 tenant-admin healthy
12.05 evaluator start    14.16 evaluator healthy
14.69 nginx start
```

**Mismatch with the brief, resolved toward the existing design:** the bootstrap is not a
`depends_on` of the roles. It stays in profile `ops` as the explicit one-shot step (`check-compose.js`
asserts "Bootstrap must remain explicit"; the README calls it "not an application startup hook").
Making it a `service_completed_successfully` dependency would need it out of the profile, or would
activate the `demo` restore service with it. `demo.sh up` runs it first, as above. Trade-off taken
from the brief: the edge now also waits for the evaluator and tenant-admin, so an unhealthy
evaluator keeps the edge from starting. The ownership-admin and vault-agent overlays already order
their services (admin and ownership-grants on postgres; vault-agent on vault; api on vault-agent)
and are unchanged. The Kubernetes README gains a paragraph: readiness probes, startup probes and
Service names cover both concerns there; the binding is unchanged.

Source checks (`check-compose.js`): start order with a control (drop `nginx → evaluator`: "nginx must
wait for evaluator to be healthy"); a broken compose file (tenant-admin edge removed) went red with
"nginx must wait for tenant-admin to be healthy"; the old `nginx.conf` went red with "nginx must use
Docker DNS with a bounded validity"; edge drift control ("nginx.compose.conf must equal nginx.conf
apart from upstream re-resolution"). All restored green.

## 5. Overlay build path (reproduced)

Cause: `prepare.js`/`build.js` ran `git diff --quiet HEAD -- … deploy/multitenant` in the core
overlay, where `tools/compose-overlay.sh` replaces core's reduced fixture by design (`config.js` and
`README.md` modified, 16 files untracked). Every overlay was `BUILD_INPUTS_DIRTY`
(`./demo.sh prepare` on a fresh overlay of `fe36212`: `Preparation refused: BUILD_INPUTS_DIRTY`).
Even past the check, `build.js` archived core's own `deploy/multitenant`, which has no Dockerfile.
Not `node_modules` (ignored, not an input) and not a path comparison.

Fix: the overlay script copies the tree by `git archive` of HEAD (refusing uncommitted changes there)
and writes `deploy/multitenant/.overlay.json` (deploy checkout path and commit). With the marker,
core HEAD is checked for every other input, `deploy/multitenant` must equal the deploy commit's tree
byte for byte (`diff -r`, only `.env`, `.state` and the marker left out), the context is built from
the two commits, and `checkImage` also checks `org.nightscout.deploy.revision`. Without the marker,
behaviour is unchanged. The harness's `prepare-overlay.js`/`build.sh` workaround is no longer needed
(not edited).

Result: `./demo.sh prepare` passed, `./demo.sh build` built and labelled the image (29.7 s, cached
layers), `build.js --check-image` passed. Refusal controls on the overlay, each restored to clean:

| break | result |
|---|---|
| line appended to `nginx.compose.conf` in the overlay | `BUILD_INPUTS_DIRTY` |
| stray file added to `deploy/multitenant` | `BUILD_INPUTS_DIRTY` |
| tracked core file `lib/cli/commands/diagnose.js` modified | `BUILD_INPUTS_DIRTY` |
| marker names an unknown deploy commit | `BUILD_OVERLAY_COMMIT_UNAVAILABLE` |
| marker removed (old behaviour) | `BUILD_INPUTS_DIRTY` |

Untracked files elsewhere in core (an untracked `lib/cli.js` created by a mistyped first control)
pass, as before: they are not in the archive the image is built from. `diff -r` does not compare
file modes.

## Repository checks at the head

`npm test` (targets, identity check, ownership-grants): pass. `tools/compose-identity-check.sh
<core>`: tree, upstream tree and 5 fixture files equal. `check-compose.js`: pass with 7 controls
rejected. Kubernetes: golden render current, 31 manifests / 11 checks / 0 failures, 15 controls as
expected. In the overlay: `bootstrap.test.js` + `restore.test.js` 13/13; ownership-grants with
`NS_CORE_DIR` 2/2.

## Teardown

Projects `nsdeployfix` and `nsdeployfixc` brought down with `down -v` (no containers, volumes or
networks left with those prefixes); the placeholder container removed; private state directories
deleted; my two core overlay worktrees removed; image `nsdeployfix:9fd2a81` removed. The
`nscap:0392acf9-fe36212` image (used read-only for the control) is the capacity lane's and was kept.

## Left over

- Core's preview-config loader turns "too large" into "cannot read valid preview JSON configuration";
  the detail line names the loader and frame but not the size (core, peer lane).
- `MULTITENANT_CONFIG_MAX_BYTES` is an assumed name; confirm against the peer core lane and run the
  option at N ≥ 2,600 once core reads it. `load-env.js` keeps a fixed 1 MiB `env.json` limit.
- The realtime log showed `Tenant warm drained: ready 0 failed 1` after the four-role restarts at N=2
  (observed only; the peer lane's realtime warm retry).
- The capacity harness can switch to `tools/compose-overlay.sh` + `demo.sh prepare/build` (harness not
  edited here).

## Follow-up (same day): config bound through Compose, load-env.js bound, edge readiness

*Captured 2026-11-11 after the coordinator's follow-up. This supersedes the "cap plumbing" paragraph
in section 2 and the edge part of section 4.*

| anchor | value |
|---|---|
| nightscout-deploy head | `ab950a2384ba825dff14ebab0dd84778ac0c6a39` (`bf2f479` + `ab950a2` on top of `4ebd7ef`); Compose tree `85d27fb4fc970f599a87d92473a2ef76f3ebbdee` |
| core under test | lane `workspace/capacity-fixes-20261111` `5517cb6c74f2906383a436d034b86be86a0f743a` (`MULTITENANT_CONFIG_MAX_BYTES`, `lib/server/serve/config-file.js`, 65,536..67,108,864, default 1 MiB); its `deploy/multitenant` is the same as at `0392acf9` |
| image | `nsdeployfix:ab950a2`, built by `demo.sh build` on an overlay of core `5517cb6c` (marker written by hand, since `compose-overlay.sh` uses SOURCE.md's `0392acf9`); labels core `5517cb6c…`, deploy `ab950a2…`; removed afterwards |

**What changed.**
- `NS_BOOTSTRAP_CONFIG_MAX_BYTES` now reaches api, realtime, evaluator and tenant-admin (through the
  shared `x-app` environment) and the ownership overlay's admin as `MULTITENANT_CONFIG_MAX_BYTES` in
  the Compose `environment:` block. Measured with `compose config`: those four roles get the value;
  the bootstrap gets only the option; ui, nginx and demo get neither. It is no longer written into
  `env.json`, and `load-env.js` refuses an `env.json` that sets it. The bootstrap accepts only core's
  range and validates its written files against the value.
- `load-env.js` takes its `env.json` bound from core's `config-file.maxBytes(process.env)`, keeps the
  lstat, symlink and mode checks, and on refusal names `CONFIG_FILE_TOO_LARGE` with the size and the
  limit, or `CONFIG_FILE_LIMIT_INVALID`. With a core that has no `config-file.js` (the recorded
  `0392acf9`), it keeps the fixed 1 MiB bound and says so ("fixed: this core has no configurable
  bound"). It does not change behaviour at the recorded commit.
- nginx waits for api, realtime and ui only. `check-compose.js` asserts that nginx does not wait for
  evaluator or tenant-admin; the edge-gating control (evaluator added back) fails with "nginx must not
  wait for evaluator", and so did the same edit made to `compose.yaml` itself. The start-order control
  now drops `nginx → realtime`.

**3,000-tenant bootstrap on core `5517cb6c` (bootstrap only, then `down -v`; reproduced):**

| run | option | result | time |
|---|---|---|---|
| set | `NS_BOOTSTRAP_CONFIG_MAX_BYTES=4194304` | `{"state":"synthetic-demo-provisioned",…}`, exit 0 | 56 s |
| unset | empty | exit 1: `{"error":"CONFIG_FILE_TOO_LARGE","detail":"MULTITENANT_PREVIEW_CONFIG is too large: 1232739 bytes, over the limit of 1048576 bytes (MULTITENANT_CONFIG_MAX_BYTES)","at":["refuse (lib/server/serve/config-file.js:41:89)","tooLarge (lib/server/serve/config-file.js:63:10)","read (lib/server/serve/config-file.js:79:32)"]}` | 60 s |

Core now gives the error a code, so the stable `error` field carries `CONFIG_FILE_TOO_LARGE` itself.
Sizes written at N=3000 (compact), the same in both runs: api `config.json` 1,232,739,
`evaluator-metadata.json` 481,165, `env.json` 342,249, `admission.json` 280,952,
`operation.json` 196,183 bytes. `env.json` contains the variable 0 times.

**load-env.js, offline** (a synthetic 1,638,891-byte `env.json`; reproduced):

| case | result |
|---|---|
| core reader, bound unset | exit 78, `CONFIG_FILE_TOO_LARGE: 1638891 bytes, over the limit of 1048576 bytes` |
| core reader, bound 2097152 | loaded |
| core reader, bound 100 | exit 78, `CONFIG_FILE_LIMIT_INVALID` |
| `env.json` sets `MULTITENANT_CONFIG_MAX_BYTES` / mode 0644 / symlink | exit 78, refused (generic message, as before) |
| no core reader, bound 2097152 | exit 78, `… 1048576 bytes, fixed: this core has no configurable bound` |
| **control:** `fe36212` `load-env.js`, bound 2097152 | exit 78, "missing or invalid": the fixed 1 MiB limit, so red as expected |

**Edge readiness at runtime, N=2** (project `nsdeployfix-edge`; reproduced): with an override that
makes the evaluator healthcheck always fail, `up` started nginx while the evaluator was still
`health: starting`. Through the edge, an api request without a token answered 401, which shows the
edge reached api. Before this change, nginx would have waited for the evaluator to be healthy (that
case was not run).

**Checks at `ab950a2`:**
- `npm test` passes.
- The identity check passes: tree `85d27fb4…`.
- `check-compose.js` passes with 8 controls rejected.
- Kubernetes: the golden render is current; 11 checks, 0 failures; 15 controls as expected.
- `bootstrap.test.js` and `restore.test.js` on the `5517cb6c` overlay: 13/13.

**Teardown:**
- Projects `nsdeployfix-set`, `nsdeployfix-unset` and `nsdeployfix-edge` were brought down with `down -v`; no containers, volumes or networks with the `nsdeployfix` prefix are left.
- The private state directories are deleted, the `5517cb6c` overlay worktree is removed, and the image `nsdeployfix:ab950a2` is removed.
