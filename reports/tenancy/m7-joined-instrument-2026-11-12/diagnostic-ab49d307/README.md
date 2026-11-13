# Explicit pre-acceptance diagnostic seam — 2026-11-12

Source `ab49d30770fe536513ec5793986c75178fcf0dd7`, own M7 instrument lane.
This immutable capture establishes instrument contracts, **not an actual fresh-app
or cloud diagnostic PASS**. No cloud action, full application deployment, image
build, capacity run or full-acceptance receipt was created by this agent.

**Reproduced:**16 focused contract checks pass. Diagnostic receipts have distinct
joined-diagnostic/AUTHORIZED_DIAGNOSTIC scope, exact source/instrument identity and
maximum10tenants/2APIs/180s traffic. They permit only diagnostic build/deploy/diagnose;
CAP run and pilot/full acceptance reject them. Diagnostic results cannot satisfy
pilot/ladder checkers. Every HTTP/prime/frame/restart/recovery/SQL criterion, exact
accepted/request counts, source/image/instrument/host identity and NOT_RUN full
acceptance are required. Common commissioning/publishing workflow is reused.

**Reproduced:**3 real Socket.IO/HTTP fixture cases pass using the owning agent's
private pinned core SDK dependencies (fixture-dependencies.json). Correct registered
hostname URL plus loopback-DNS Agent primes, publishes the new timestamp and recovers
unaided. Known-bad127URL/extraHeaders.Host fails rather than becoming a product
latency claim. HTTP ACK without a current frame also fails. These are instrument
controls against a synthetic server, not application authorization/clinical tests.
The fixture uses100ms server heartbeat solely to make connection loss deterministic
within its5s test bound. Initial default-heartbeat timeout was fixture setup, not
product failure; no latency figure from it is reported.

**Reproduced:**own tiny PostgreSQL/HTTP source-payload smoke accepts six synthetic
writes; independent stored oracle GREEN→row-marker RED→restored GREEN. Actual
PostgreSQL restart, intentionally skipped restart refusal, restored actual restart
also pass. No existing database or resource was used or stopped. This is the SQL/
restart instrument proof, not the full fresh-image diagnostic.

The coordinator relayed the fixed instrument/receipt for a separate authorized
fresh-image remote diagnostic. That remote execution/evidence belongs to its own
controller and source tuple, not this record. At capture, root reports a later human
budget policy superseding earlier$1 documentation; do not infer a new spend grant
from these immutable files. Future documentation should name the controller-selected
policy. Current ab49 code/docs remain frozen for the already authorized run.

Public contract: tools/mt-bench/m7-joined/DIAGNOSTIC-SEAM.md. Private source receipts,
credentials, host inventories and raw app state are excluded here. Full acceptance
and capacity remain UNMEASURED. The next lane action is read-only binding review;
root owns uncommitted sharding/helper integration and native Docker acceptance.
