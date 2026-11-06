# Archived storage, management HTTP and nonresident replay checks

Contributor-facing synthetic integration instruments. Each suite archives an
explicit CRM commit into scratch and uses private dependencies with an identical
lockfile. No shipping checkout is changed. Source objects must be available
locally; an unpushed local head is not automatically restored by bootstrap.

```bash
node tools/queue/gates/multitenant-next-slices.js --suite port --ref <REST-commit>
node tools/queue/gates/multitenant-next-slices.js --suite management --ref <REST-commit>
node tools/queue/gates/multitenant-next-slices.js --suite profile --ref <profile-commit>
node tools/queue/gates/multitenant-next-slices.js --suite compose --ref <REST-commit>
node tools/queue/gates/multitenant-next-slices.js --suite identity --ref <REST-commit>
```

The port, management and composition process fixtures own their disposable
services. The identity gate owns PostgreSQL16 and MongoDB8 fixtures. The profile gate
creates and removes its own MongoDB 8.0.34 service with explicit descriptor limits
and a random loopback port/test database. All suites archive the complete committed tree and link matching private
dependencies only inside scratch, allowing actual CLI child execution.
The default profile dependency tree is
separate because its lockfile differs from the REST continuation. `NS_REST_GATE_REPO`
and `NS_REST_GATE_DEPENDENCIES` can select matching local inputs. Node/Git/tar/Docker,
the fixture images and installed private dependencies are prerequisites.

| Suite | What is measured | `--control` cases (each must fail) |
|---|---|---|
| `port` | Actual Mongo/PG lower and preview port capabilities, typed/shown IDs, query/projection/refusal, real outcomes, scope/transactions and logical events | `projection`: wrong projected value; `tenant`: foreign RLS binding; `outcome`: false changed count |
| `management` | Standalone authenticated subject HTTP, actual persistence/revocation, no data-plane mount, bounded request/error/header behavior and no egress | `auth`: bypass credential verification; `tenant`: bypass actor/host match; `exposure`: deliberately mount management before data in the fixture |
| `profile` | Separate #8891 actual-trigger/timer/property and actual HTTP mutation/resend replay, request-signature parity, selected live notification handoff and teardown; external-socket guard | `tick`, `write`, `http`, `window`, `freshness`: fixture trigger/window/freshness controls; `closed`: close the actual HTTP cohort service while preserving request recording, so live emission must fail |
| `compose` | Current domain/backend composition, real CLI startup/prebind refusal and API3 failure-provenance HTTP | `capability`: remove injected-intent guard; `catalogue`: bypass read-only catalogue check; `unavailable`: misclassify dependency outage, changing HTTP503 to500 |
| `identity` | Actual Mongo/PG API3 imported raw identities with absent/falsy identifiers through GET/mutations/deletes, typed persistence and foreign-tenant invariance | `lookup`: remove PG raw-ID fallback, making actual GET404 after Mongo200 |

Source mutations require exactly one match in scratch. Profile controls use
explicit options on the actual evaluator fixture; they do not change the
production subscriber. The exposure control tests bad application composition,
not a production mount that does not exist. Setup failures are not semantic
controls. Positive runs require nonzero passing tests and no pending cases.

These instruments do not establish a full management listener, human identity
policy, grant ceilings, every backend/HTTP shape, all alarm producers or complete notification-field
parity, actual
provider delivery, quiet-hardware cost or durable multitenant recovery. The
profile branch is independently tested; it is not automatically joined into
#8898 or admitted to the RC. Queue controls register one representative break
per suite; the other authored controls are recorded in the integration record.
