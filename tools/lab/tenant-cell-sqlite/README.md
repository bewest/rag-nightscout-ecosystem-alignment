# Tenant cell + SQLite lab

Synthetic data only. Runs real **celld v0.6.3**, not an actor mock or an
in-memory SQLite substitute. Each authenticated fixture tenant is routed to a
Durable Object with its own SQLite database. SQLite is the **sole record
authority**: no MongoDB/PostgreSQL record copy or cross-system commit is involved.

This is a storage feasibility experiment, **not a Nightscout storage adapter,
API, deployment recipe, authentication system or third supported backend**.
The tiny `/lab/` protocol intentionally differs from NS and must not serve real
records. The shared-cell flag exists only to make the isolation test fail.

## Reproduce

Requires Linux, Node 22+ and the pinned celld binary. No npm dependencies,
bundler, Docker, credentials or cloud bucket are needed. Download and verify
celld using the project's release attestation:

```sh
mkdir -p /tmp/ns-celld-063
gh release download v0.6.3 --repo denoland/celld \
  --pattern celld-x86_64-unknown-linux-gnu.gz --dir /tmp/ns-celld-063
gh attestation verify /tmp/ns-celld-063/celld-x86_64-unknown-linux-gnu.gz \
  --repo denoland/celld
gzip -dk /tmp/ns-celld-063/celld-x86_64-unknown-linux-gnu.gz
chmod u+x /tmp/ns-celld-063/celld-x86_64-unknown-linux-gnu
CELLD_BIN=/tmp/ns-celld-063/celld-x86_64-unknown-linux-gnu \
  node tools/lab/tenant-cell-sqlite/run.mjs
```

Use a new empty download directory if that path already exists. The measured
compressed asset SHA-256 is
`5084a083472cf036551a7eac63fa24d22bb9a56323c517f63205724c12783047`;
the executable and source hashes are in `results/local.json`.

The runner creates uniquely named `.runs/` projects with generated synthetic
principal bindings. Public and operator listeners bind to loopback. It waits
for HTTP readiness, stops its own process trees, and retains local state and
logs for diagnosis. `.runs/` is ignored; the compact measured report is tracked
as `results/local.json` and overwritten on the next run. Do not copy real
dotenv files into a fixture project. Do not run `celld dev` directly on this
directory: bindings are supplied by the runner, not the template config.

## Checks

Twelve positive checks cover overlapping tenant IDs, read/write/delete routing,
missing/wrong principals, tenant-local operation receipts, 16 concurrent retries,
24 distinct concurrent writes, transactional batch rollback, JSON type brackets
and null/missing, indexed date pagination, tombstones, a 32-tenant batched ingest,
warm read/write latency, and SIGTERM/SIGKILL restart persistence.

The thirteenth result is a deliberate **negative control**: two valid tenant
principals route to one cell. The same isolation check reads tenant B's `200`
through tenant A where it expects `100`. An arbitrary HTTP error is not accepted
as evidence that this control worked.

The receipt ledger and record change commit in the same SQLite transaction.
Exact request-content retries replay the saved response; different content under
one operation ID conflicts. This uses JSON serialization, not semantic JSON
canonicalization. Receipts have no expiry in this short experiment.
The schema intentionally treats `identifier` as required, preserves immutable
identity, and refuses resurrection of tombstones. These are **lab rules**, not
claims about all existing NS endpoints.

## Measured result

See the [decision guide](../../../docs/10-domain/tenant-cell-sqlite-deep-dive.md)
for results, source references, comparison with PostgreSQL and both per-database
and shared-collection MongoDB, architecture tradeoffs, economics and promotion
gates. Four Mermaid figures illustrate the candidate architecture, local latency,
write/durability boundary and decision path. The report's restart timings include
stop/start and verification; they are not fleet failover latency or an availability
SLO. Historical backend timings are not a matched comparison with this lab.
