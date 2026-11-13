# Tenant operations fixture migration model repair

Reproduced on frozen core `d5e2e874659155c952b5b5deb862f12f982ac02e`; test-only repair `e8e6a39d48e86f310dc857358ed994981de2c15d` changes `tests/tenant-operations.test.js`. Product migration, backup, restore, inventory and authorization remain unchanged.

The fake database omitted `0002_management_session_issuance`. [Original focused run](original.txt) reproduced 7 passing / 25 failing. The fixture now models the issuance table's 14 columns, includes it in parent-first table ordering and asserts the migration creates the expected single table. Inventory and ACL expectations include the new relation. A new restore case seeds a management session and its issuance request, then checks the exact restored row and migration ledger. The fake model does not simulate PostgreSQL functions, row security or foreign keys; native database suites own those guarantees.

[Repaired suite](model-complete.txt): 33 passing. [Adjacent management session and logical restore checks](joined-focused.txt): 49 passing. Omitting the issuance relation from the model inventory makes the new restore check [fail](inventory-control.txt) with `OPERATIONS_RELATION_UNADMITTED: access.management_session_requests`; restoring the model returns green. This control demonstrates the fixture detects a missing relation rather than silently skipping its state.

Node v22.23.4 and coordinator-owned exact-lock dependencies were used locally, through the checked-in CI environment loader. [Artifact hashes](artifacts.json) refer to preserved original captures; published captures only replace the local workspace prefix. No native database, browser, capacity or full-suite result is claimed here. Full acceptance waits for the joined repair candidate.

Programme `make queue-check` passed after staging these records. `git diff --cached --check` reports preserved captured whitespace: 25 whitespace-only diagnostic lines and four capture files with blank lines at EOF. These are immutable test output, not product source changes.
