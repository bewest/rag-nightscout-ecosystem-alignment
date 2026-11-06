# Selected-owner actual-client preparation

This separate, unregistered instrument is prepared for frozen CRM `8713395992e07b4dd2cde61ee972e9a15c8ada8c`. Its database/client acceptance is **UNMEASURED**. It changes no application entry point, production configuration, registered gate or default M4 instrument. The accepted unselected default-client capture remains separate in evidence commit `1408dac5c39638cc7b5d261923e1bb0a2c0eda19`.

`bootstrap.js` is a lab-only copy of the source preview composition at that head. It uses the existing tenant app, data-access, secrets and PostgreSQL reader constructors. Its explicit `selected` boolean supplies `ownerPolicy` to the legacy subject reader; its readiness reads the provisioned subject snapshot and checks each initial admitted operation. It refuses access-token configuration because this bounded lab measures the existing legacy subject token carrier. The regular preview bootstrap is unchanged: its anonymous readiness probe cannot select this subject-only reader.

`server.js` verifies the existing SQL fixture has exactly `anonymous_roles=['denied']`, provisions a concrete viewer role and owner-policy row under the initial ceiling in actual PostgreSQL, then closes its operator connection before serving. The six reviewed catalogue terminals are read/create on entries, treatments and devicestatus. These concrete rows are existing supported policy grammar, also used by the source owner-clamping acceptance fixture. Anonymous, wildcard and default grants are outside this selection.

The future runtime measurement uses the pinned, unchanged oref0 binary through its supported `token=` argument. It runs three admitted upload workflows on separate unselected-reference and selected fixtures, compares replies and stored values with no classification exemptions, empties tenant A's ceiling, then invokes another real client upload. Selected mode must return the existing v1 denial status **401** and leave independent SQL snapshots of every domain on tenants A and B unchanged. Unselected reference must retain its grant and store the second synthetic input. Client exit codes remain separate because oref0 curl lacks `--fail`.

Pinned cgmsim always SHA1-hashes its input into an `api-secret` header (`src/setupParams.ts`); it cannot present an existing subject/token carrier. The instrument therefore measures its root-carrier boundary separately. Root exclusion is deliberate. The current source predicts **503** for the unmapped non-subject authority error; that status is read-derived until runtime observation and requires a separate compatibility disposition. It is not an adopted response contract or waiver. No credential translation or cgmsim modification is introduced, and admitted selected cgmsim compatibility cannot be claimed. Universal selected-mode activation remains blocked.

The `intersection` control changes only an archived scratch copy of `owner-policy.js`, replacing the catalogue-and-ceiling intersection with catalogue projection. This must allow the tightened real client write, producing both a wrong HTTP status and changed independent stored state in `tightening-oracle.json`; the run must fail. A fresh normal run then must pass. No source worktree or old capture is modified. The [contract tests](test-contract.js) independently reject HTTP corruption, stored-state corruption and admitted payload corruption; their ablation simulation checks source policy/oracle composition, not actual SQL or HTTP execution.

Preparation checks (no Docker or database):

```bash
SELECTED_OWNER_SOURCE="$CRM" node tools/lab/selected-owner-clients/test-contract.js
node --check tools/lab/selected-owner-clients/bootstrap.js
node --check tools/lab/selected-owner-clients/runner.js
node --check tools/lab/selected-owner-clients/server.js
node --check tools/lab/selected-owner-clients/gate.js
```

Only after explicit runtime coordination/release, invoke the standalone gate with absolute paths. Dependencies must be a private physical installation matching the frozen lock. Use the dedicated pinned client root; shared stale cgmsim output is refused by the canonical build-provenance checker, including all 94 compiled JavaScript files. Output paths must be fresh. Run the control first and preserve its exact red symptom; restoration uses another fresh output directory.

```bash
NS_M4_EXTERNALS="$PINNED_CLIENT_ROOT" TZ=UTC node tools/lab/selected-owner-clients/gate.js \
  --repo "$CRM" --dependencies "$PRIVATE_NODE_MODULES" --out "$FRESH_CONTROL_OUTPUT" \
  --ref 8713395992e07b4dd2cde61ee972e9a15c8ada8c --control intersection
NS_M4_EXTERNALS="$PINNED_CLIENT_ROOT" TZ=UTC node tools/lab/selected-owner-clients/gate.js \
  --repo "$CRM" --dependencies "$PRIVATE_NODE_MODULES" --out "$FRESH_POSITIVE_OUTPUT" \
  --ref 8713395992e07b4dd2cde61ee972e9a15c8ada8c
```

Expect control exit 1 with selected status 200 and both refusal predicates false; normal exit 0 with admitted parity and both selected tightening predicates true. Setup errors exit 2. Runtime owns random loopback ports and canonical uniquely named fixtures. Capture exact container IDs/mounted volumes independently before teardown; audit their absence and preserve pre-existing resources. This prepared instrument has not yet measured those predictions and must not delay the current batch publication.
