# Archived storage, management HTTP and nonresident replay checks

Contributor-facing synthetic integration instruments. Each suite archives an
explicit CRM commit into scratch and uses private dependencies with an identical
lockfile. No shipping checkout is changed. Source objects must be available
locally; an unpushed local head is not automatically restored by bootstrap.

```bash
node tools/queue/gates/multitenant-next-slices.js --suite port --ref <REST-commit>
node tools/queue/gates/multitenant-next-slices.js --suite management --ref <REST-commit>
node tools/queue/gates/multitenant-next-slices.js --suite profile --ref <profile-commit>
```

The port and management files own their disposable services. The profile gate
creates and removes its own MongoDB 8.0.34 service with explicit descriptor limits
and a random loopback port/test database. The default profile dependency tree is
separate because its lockfile differs from the REST continuation. `NS_REST_GATE_REPO`
and `NS_REST_GATE_DEPENDENCIES` can select matching local inputs. Node/Git/tar/Docker,
the fixture images and installed private dependencies are prerequisites.

| Suite | What is measured | `--control` cases (each must fail) |
|---|---|---|
| `port` | Actual Mongo/PG lower and preview port capabilities, typed/shown IDs, query/projection/refusal, real outcomes, scope/transactions and logical events | `projection`: wrong projected value; `tenant`: foreign RLS binding; `outcome`: false changed count |
| `management` | Standalone authenticated subject HTTP, actual persistence/revocation, no data-plane mount, bounded request/error/header behavior and no egress | `auth`: bypass credential verification; `tenant`: bypass actor/host match; `exposure`: deliberately mount management before data in the fixture |
| `profile` | Separate #8891 actual-trigger/timer/alarm/properties/coalescing/teardown replay using fake delivery and an external-socket guard | `tick`, `write`, `window`, `freshness`: existing fixture options suppress triggers, narrow device acquisition or substitute request-time properties |

Source mutations require exactly one match in scratch. Profile controls use
explicit options on the actual evaluator fixture; they do not change the
production subscriber. The exposure control tests bad application composition,
not a production mount that does not exist. Setup failures are not semantic
controls. Positive runs require nonzero passing tests and no pending cases.

These instruments do not establish a full management listener, human identity
policy, grant ceilings, every backend/HTTP shape, all alarm producers, actual
provider delivery, quiet-hardware cost or durable multitenant recovery. The
profile branch is independently tested; it is not automatically joined into
#8898 or admitted to the RC. Queue controls register one representative break
per suite; the other authored controls are recorded in the integration record.
