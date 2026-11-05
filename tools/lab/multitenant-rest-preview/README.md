# Reproducible selected-domain REST preview acceptance

Contributor-facing synthetic lab. It runs committed CRM tests from an explicitly
selected, clean worktree against uniquely named disposable PostgreSQL, MongoDB
and development Vault services. It prints the CRM head and measured service
versions, overrides all database/provider connections and removes only its own
services. It refuses acceptance if the tracked tree or head changes during a run.

```bash
# Install locked CRM dependencies and build assets in that private worktree first.
export CRM_REST_WORKTREE=/absolute/path/to/clean/crm-worktree
ulimit -n 64000
node tools/lab/multitenant-rest-preview/owned.js focused
node tools/lab/multitenant-rest-preview/owned.js all
node tools/lab/multitenant-rest-preview/owned.js browser
node tools/lab/multitenant-rest-preview/owned.js migration
```

For a scoped authored source control, append Mocha options after `focused`, for
example `focused --require /absolute/path/to/control.cjs --grep <case>`. The hook
must be omitted for restored acceptance; setup errors are not semantic controls.

`focused` enables actual legacy/API3 domain, derived-read, source-pinned client
pattern, current-authority, subject-administration, legacy credential rename,
storage and backend-census tests. The subject-administration lab creates its own
additional disposable PostgreSQL service and does not expose an HTTP owner API.
Client replay uses
the real CLI and real Vault/PG; the separate derived Mongo differential uses a
synthetic signing provider. The executable composition test joins derived reads
with actual Vault authority, revocation and restart. These are extracted client
patterns, not execution of Swift client binaries.

`all` runs every nonbrowser tier with the relevant REST/credential/process opt-ins;
`browser` runs the complete browser tier on independent services. Disabled opt-in
labs remain pending, never passing. `migration` separately enables existing
migration and two-tenant HTTP suites. No mode promotes a milestone or establishes
full REST, production trust, provisioning/lifecycle, HA or operational readiness.
The current corpus includes `subject-admin` tests; select a CRM continuation
containing those files rather than the earlier published R40 head.

Prerequisites: Node/Git/Docker, privately installed matching CRM dependencies,
built browser assets, `postgres:16`, `mongo:8.0.34` and the exact Vault image digest
in the runner. CI defaults load before the runner's random loopback connection
overrides; timezone UTC, seed41574423920 and `TEST_ENV_FILE=/dev/null` are explicit.
No real site, data export, deployment credential or shared database is used.

This runner tests a clean owned worktree; it is not a read-only queue gate.
The bounded [authority gate](../multitenant-rest-authority/README.md) instead
archives the exact commit into scratch and carries registered negative controls.
Record red-control symptoms, restored runs, full-suite results and remaining
pending labs in the release integration record; counts from overlapping modes
must not be added.
