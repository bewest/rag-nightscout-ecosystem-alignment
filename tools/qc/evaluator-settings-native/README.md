# Evaluator-owned settings: prepared native PostgreSQL acceptance

Status: **PREPARED; NATIVE RUN UNMEASURED; PENDING COORDINATOR REPIN**.
The fixture-only repair is awaiting a replacement frozen core head. Keep the
explicit X pin below until the coordinator supplies that exact head; do not
guess/rebind or activate this draft against a superseded cohort. This external instrument does not
change application source, test tiers, deployment source, the image, or the
primary baseline source pack. It is outside that pack's existing paths.

Frozen source anchors independently inspected during preparation:

- Core X: `df71c8e815d65d3abcdf6109664ea841bba17733`.
- Deployment Y: `8c27567186f7ede8b6c49674d9751f9e79e8d330`.
- Supplied, not independently inspected here: image
  `sha256:e58c3f616445618215810069a2c845c1df78e200f96facf20906f66a0e95f7bb`,
  binding prefix `56183`.

The existing native `postgres-secrets.integration.test.js` checks settings
persistence and unsafe tables; `registry-realtime-settings.integration.test.js`
checks persisted realtime/API presentation and finite configuration reads. They
do not exercise this evaluator boot-owned revalidating reader. This instrument
reuses the exact candidate's `tests/fixtures/evaluator-preview-lab.js`, its
clinical/replay migrations and teardown, and the owned settings/operator-policy
migration catalogues. It boots actual `evaluator-preview.boot` in process.
An external `readCurrent` observer captures the reader that boot supplies; it
forwards every call unchanged. Subsequent settings probes use that same owned
reader and actual `load.readCurrent`, with real PostgreSQL SQL and role checks.
No driver/module replacement or SQL delay is used.

This is a source fixture, **not a running image/full serve/operation-cohort
qualification**. It has no HTTP listener, registry provisioning, Vault, pool
membership partitioning or production operation-window composition. Static
A/B tenants are the existing fixture's synthetic roster. The coordinator still
owns image role gates, clinical/TIME checks, the eight tiers, enabled corpus and
browser acceptance. Cleanup-end uncertainty remains unit-mock coverage; this
instrument does not pretend PostgreSQL termination proves a failed Client.end.

## Preparation checks (no activation)

From this directory:

```bash
node --check run.cjs
node offline.test.cjs
node run.cjs --plan
```

These verify instrument guard/control behavior only. A plan is never acceptance.
The offline observer uses a synthetic EventEmitter to check forwarding and
accounting; it supplies no PostgreSQL or clinical evidence.

## Native recipe — only after the coordinator releases its exact window

Inputs: a **coordinator-owned disposable native PostgreSQL test database** and
admin URI in `NS_TEST_POSTGRES_ADMIN_URI`, frozen core with its installed local
read-only dependency cache, and a fresh absolute JSON output path in an existing
owned directory. No Docker/cloud/service startup or dependency installation is
performed. The fixture requires the database name to contain `test`; that name
check is only an accident guard, not proof of database ownership. The explicit
coordinator-approved URI is the ownership authority. The admin needs the same
schema/role creation, migration, grant and exact owned-backend termination
privileges used by the existing lab.

Use a clean process environment so unrelated role/pool configuration is absent.
The URI is passed through the environment, never printed or embedded in output.
Do not activate this command while another lane owns the native window.

```bash
# Run from the external artifact directory; OUT must not already exist.
CORE=/absolute/path/to/frozen-core
OUT=/tmp/COORDINATOR-OWNED-WINDOW/settings-native-result.json
# Parent directory is created/owned by the coordinator before release.
env -i PATH="$PATH" HOME="$HOME" NODE_ENV=test TZ=UTC \
  NS_TEST_POSTGRES_ADMIN_URI="$NS_TEST_POSTGRES_ADMIN_URI" \
  NS_SETTINGS_NATIVE_APPROVED=1 MULTITENANT_STATIC_TENANTS=lab \
  node run.cjs --run --core "$CORE" --output "$OUT"
```

The command checks exact core HEAD and tracked cleanliness before any database
connection. Base fixture `open()` sets tenancy mode to `multi`, remembers its
prior mode, and restores it at close. The instrument temporarily sets
`NS_TENANT_READINESS=all`, restores its prior value, and uses no external Mocha
hooks. Its generated config references in-memory credentials through explicit
source names; no credential is written into the config or measurement.

## Native criteria and predicted outcomes

1. Boot the actual evaluator and capture one owned reader; A/B begin in default
   `mg/dl` with distinct synthetic SHOW_SECONDS. Owner updates change the next
   read/identity; a current operator pin makes A `mmol` while B stays `mg/dl`. Ambient tenant B requesting A must refuse, then valid A/B reads restore. Successful A/B values alone are not treated as RLS isolation proof.
2. Disable RLS on the owned settings table: the next read must refuse
   `SETTINGS_STORE_UNSAFE`. Restore, then fresh read succeeds. Revoked SELECT
   has the same prediction. A temporary UPDATE grant must refuse in readiness.
3. Corrupt one owned migration-ledger checksum: the next read must refuse
   `MIG_DRIFT`. Restore the exact captured value, then fresh read succeeds.
   These are native red/restored controls, not changes to guard cadence.
4. Hold ACCESS EXCLUSIVE on the owned settings `schema_migrations`. Four admitted
   refresh chains block in **real direct migration clients**; two calls queue
   (`maxTenants=2`), and overflow must refuse. Update B while waiting, then unlock:
   queued reads must see the new state and enter FIFO. Transparent Client
   connect/end observation is filtered to the unique settings reader role;
   pool versus direct clients use the actual pool application name. Native
   `pg_stat_activity` independently observes four blocked direct clients.
   Synthetic per-call job ALS and real tenant ALS must survive queuing.
5. Hold the owned settings table, start a tenant JOIN, then terminate only its
   exact owned role/database/PID/backend-start tuple. The termination SQL must
   return one true result; the read must refuse, the lock is released, and a
   new call through the same owner must recover freshly. No unrelated backend
   is terminated; there is no wildcard or shared-database termination.
6. Repeat the ledger lock with four admitted and two queued operations. Actual
   evaluator close must cancel the queued calls, remain pending while direct
   checks are blocked, then finish after unlock/drain. A post-close call must
   refuse without reopening. Both native session inspection and client
   observation must reach zero for the unique settings role.

The reused admin client is exposed synchronously before its connect completes. An
instance-only query wrapper sets its statement deadline to3s, lock deadline
to1.5s, idle-transaction deadline to10s, and per-query client deadline to3s before
its first query. This bounds its setup/mutation/restore/drop SQL; application
reader sessions and their reviewed timeouts are unchanged. Owned lock clients
have3s statement and10s idle-transaction deadlines. Settings setup migration
calls use5s statements/1.5s advisory waits. The reused clinical fixture's
separate migration clients retain their existing finite60s statement defaults.
The coordinator's outer window watchdog should allow initial clinical setup
and finally cleanup (for example5minutes), capture exit/error output, and
preserve the synthetic ownership names if an external interruption prevents
cleanup. A watchdog kill never counts as a clean result.

Condition polling uses a 1.5 second monotonic deadline and 20 ms intervals. It
must observe the held phase below the real 5 second settings/catalogue SQL
deadlines (migration connect also has a 10 second connection timeout). A condition timeout is a failing/unmeasured native outcome,
not permission to loosen application timeouts or substitute sleeps. Lock
transactions are rolled back in finally; mutation values/grants/RLS are restored
before fixture teardown, even when a criterion fails. Owned lock clients are
tracked before connect; rejected operations have immediate rejection handlers
while their assertions remain awaited. No cleanup force-kills database sessions.
A teardown failure is reported, never counted as clean acceptance.

Each run creates unique `esn_<random>` settings schemas and roles, plus the
existing lab's separately unique `clock_test_<random>` objects. Only successfully
created objects enter teardown ownership sets. The result contains synthetic
ownership names and failure phase/code, never a URI/password. Unexpected
remaining sessions make cleanup fail and require the coordinator's owned
recovery; the instrument will not terminate a shared database to make it green.

The proposed source budget is one max4 retained pool plus at most4 simultaneous
direct check clients (each chain runs its three check clients sequentially).
Client observer peaks and native blocked-client capture test this proposition;
no runtime/native ceiling, CPU saving, SQL QPS reduction or capacity result is
claimed before execution. Backend termination/recovery and real native timing
remain **UNMEASURED** during preparation.
