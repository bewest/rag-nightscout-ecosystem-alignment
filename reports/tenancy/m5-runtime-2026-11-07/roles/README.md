# Joined M5 roles recorded evidence — review candidate

This gate validates an archived synthetic measurement: six ordinary phases, six distinct semantic controls, and six fresh restored phases at the source objects declared in `plan.json`. It replays the actual frozen physical predicates and timestamp/BSON oracle. It does **not** start PostgreSQL, MongoDB, Vault, API, realtime, evaluator or a browser.

The six phases cover recovery/connected storage, data compatibility, durable notification handoff and cold control clear, plugin snooze/ACK compatibility, authority/config epochs, and an unchanged client on a controlled same-origin browser fixture. Server handoff, recipient event and browser presentation are separate observations. The browser fixture does not claim an evaluator-to-device journey. External providers, device delivery, capacity/performance and whole-programme acceptance remain **UNMEASURED**.

The recorded PostgreSQL boundary has its separate sibling home. `m5-runtime-batch-recorded.js` validates both homes without inventing an aggregate application head. Its PostgreSQL portion requires the separately reviewed PG package to be joined by the coordinator. No queue, milestone or release status is changed by this candidate.

## Replay the record

Prerequisites: the declared application Git objects and an **already installed**, read-only app `node_modules` whose adjacent `package-lock.json` and actual `mongodb` version match the plan. Alignment's plain-checkout CI does not install these externals. The actual timestamp/type oracle uses `mongodb.ObjectId` and the committed `postgres-identity.js`; it cannot be replaced by a fake BSON model. Missing objects/dependencies are **NO-INSTRUMENT**, a failing result. The gate never installs or fetches them.

```bash
node tools/queue/gates/m5-roles-recorded.js \
  --repo "$APP_OBJECT_REPOSITORY" --deps "$APP_NODE_MODULES"

# After the coordinator joins the separate accepted PG record:
node tools/queue/gates/m5-runtime-batch-recorded.js \
  --repo "$APP_OBJECT_REPOSITORY" --deps "$APP_NODE_MODULES"
```

These commands validate recorded evidence, not current-HEAD or fresh native execution. Gates read committed app objects through Git into owned scratch and never change a peer checkout. Immutable source objects may be cached within one invocation; worktree/capture observations are not cached.

## Attribution and export boundary

`plan.json` pins actual head/tree, source archive, causal source files, native tools, controlled patches, image IDs, bundle/browser hashes, raw/observer indices, process results and exact phase configuration/observation hashes. Each projected phase retains its original kind/verdict, source, process result, applied-source hashes, raw SHA256 and projected semantic fields. Completed records cannot replace earlier stopped campaigns or independently regraded PG records.

This role record uses the fresh full campaign only; it reuses no earlier role phase. Earlier stopped role capsules retain their original verdicts in the coordinator's evidence history. The sibling PG record separately retains its stopped campaigns, invalid control and explicitly reviewed regrades.

The whitelist builder first verifies every indexed original file and independent cleanup. It replays original strict predicates on scratch copies **before** projecting fields or substituting private browser executable paths. It retains structured synthetic host/port origins, preserving their equality rather than replacing all origins by one constant. Original executable-path equality must pass; the public reference retains the reviewed artifact hash. Date/ObjectId type descriptors, physical rows, callback shapes, actual operation windows and server timestamps remain available to the original oracle.

The builder excludes credentials, environments, env-reference files, database/Vault URLs, ciphertext, private paths, arbitrary logs, stacks, browser storage and headers. The only log witness is an exact `ERR_ASSERTION` marker independently extracted from a hashed original. Unknown fields, malformed values and new fixture shapes stop export for review. Some redundant diagnostic snapshots are deliberately omitted; fields consumed by the physical predicates remain. Native verifiers with incidental output writes run only in scratch, leaving original capsules immutable.

Cleanup records retain exact per-cohort resource cardinality, normal shutdown, no forced child cleanup, endpoint/symlink absence and private-directory removal. The independent parent observer supplies baseline/identity/resource/birth checks; summaries are tied to its original index. The builder does not infer successful teardown from child success markers.

`observedBirths` counts all recorded process births, including Chromium; it is not a Node process count.

## Offline gate sensitivity

`--control NAME` corrupts a private clone and recomputes both projection hash layers. Controls cover exact phase/restoration/source/cleanup, all six native red predicates, timestamp evidence, browser urgent UI and unknown credential fields. Example:

```bash
node tools/queue/gates/m5-roles-recorded.js \
  --repo "$APP_OBJECT_REPOSITORY" --deps "$APP_NODE_MODULES" \
  --control retry-control-green
```

That command must fail the physical control oracle. Existing native controls are not rerun to package this record. Coordinator review, gate-control registration and coherent programme wiring remain pending.

## Reproduce the projection

Only a maintainer with the reviewed immutable private synthetic capsules can reproduce the public export. The private inputs remain local; the committed projection is sufficient for public semantic replay with the declared source/dependency prerequisites.

```bash
node tools/queue/gates/_m5-roles-recorded/build.cjs \
  --plan reports/tenancy/m5-runtime-2026-11-07/roles/plan.json \
  --capsule "$ROLES_CAPSULE" --observer "$ROLES_OBSERVER_CAPSULE" \
  --repo "$APP_OBJECT_REPOSITORY" --deps "$APP_NODE_MODULES" \
  --out "$NEW_PROJECTION_FILE"
```

The output must not already exist. Two independent exports must be byte-identical. No private native log or arbitrary raw file is copied into the public repository.
