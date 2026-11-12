# Cold replica precondition: source-only possible mechanism

Reproduced on exact clean core 2d0ae0354a38b4a88f43bc2ae5ec60c085058f64:
a valid registry-mode serve-then-warm API process can be globally ready while an
accepted tenant is not yet initialized on that process. This is a possible
mechanism, NOT the established cause of the [original stock failure](../original/README.md).
No original request timestamps/upstream identities exist to establish that cause.
No production or fixture file was edited; no retained resource, HTTP server,
PostgreSQL, Vault or restore operation was queried/executed.

## Exact mechanism

- `lib/server/serve/registry-tenants.js:72` exposes an empty binding-key iterator
  in registry mode; materialization happens through the resolver (`:59–62`)
  and per-tenant prepare (`:71`), independently in every API process.
- `preview-api.js:128–140` constructs startup from that iterator and uses
  `startup.admit` before request work. `pool-config.tenantReadiness({})` selects
  the adopted default `serve` (`preview-api.js:75–78`).
- `tenant-startup.js:111` snapshots initial keys. A newly accepted tenant gets
  its cell only at `:115–118`; cold `admit` queues initialization and immediately
  throws typed TENANT_WARMING/retryAfter at `:203–213`.
- `tenant-startup.js:234–235` reports configured cells, and global ready=true
  in serve mode, including when a tenant has no cell yet. It is not proof of
  every API×tenant tuple being warm.
- The HTTP mapping of that typed error to 503/Retry-After is read-derived from
  `lib/server/tenant-app/index.js:17,128–130`; the probe itself does not run HTTP.

## Reproduction/control

The unmodified actual startup component is instantiated twice with empty initial
iterators and accepted synthetic registry B. The initialization provider is a
controlled Promise; there is no operation-window/backend/authority substitute
claim. API1 B is initialized; API2 has not seen B. Both global health.ready values
are true. Repeated API2 health reads neither create B's cell nor initialize it.
API2's first accepted B admission throws TENANT_WARMING/retryAfter 5 BEFORE any
restore or invalidation exists in the probe.

Naive global-ready precondition: RED (it says ready but cold B refuses). Exact
per-instance/per-tenant barrier: GREEN after explicit API2 initialization. A
subsequent selected A invalidation preserves B ready/admitted on BOTH gates.
Three initialization calls occur: API1 B, API2 B, API1 A. Raw source hashes and
observed state are in [result.json](result.json). The coordinator independently
reproduced the same source-component result; no original-run replay is implied.

Run the archived probe only in an owned scratch copy after pointing its `core`
constant at a clean exact 2d0 tree. Node's child git check needs read permission.
The original sandbox attempt was blocked by spawnSync git EPERM; the scoped
read-only run succeeded. Node v22.23.4. Startup's owned timers are closed.
No source workaround, suppressed error, global eager warming, new authentication
policy or readiness semantic change is proposed.

## Fixture boundary, owned by RT

Before ANY strict cold-sensitive HTTP setup (including JWT exchange), establish
every exact API×configured synthetic tenant tuple through a supported real
authorized read. Edge-only requests or aggregate health cannot establish coverage.
Use deterministic direct exact-instance targets solely for that precondition;
keep the four original measured public-edge B readers unchanged with upstream
API identity UNKNOWN unless actually observed. The selected DATA credential/status
carrier must be tested through the actual handler; this source probe does not
prove carrier/auth acceptance.

Only explicit typed 503 TENANT_WARMING may be retried within a bounded, recorded
precondition. Other status/authority/transport failures terminate setup. After the
barrier retain strict zero measured 503 continuity; no retry/grace/fallback may
hide a response during the restore criterion. Retain stage start/end, exact target
CID/StartedAt/source-image identity, tuple, attempt start/end/status/bounded error,
barrier completion, reader start and restore-child spawn/exit times. Do not log
credentials, raw bodies or exchange URLs containing credentials. Setup read counts
and delay are separate from the unchanged measured workload.

The original shipping fixture (`dcc4` `shipping-sharding.integration.test.js:49–58`)
starts four reader tasks, waits only for aggregate settingsReads>=4, then spawns
the restore child; it checks settingsErrors only afterward. Consequently an early
pre-restore reader failure can remain in the array and appear at the later
assertion. This ordering is read-derived; absent request chronology prevents
attributing the original responses to that interval or a particular cold tenant.
RT owns the bounded fixture repair/control and any authorized new qualification;
this lane owns only independent source review and the unchanged native capture.
