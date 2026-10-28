# Writing to storage through `write(intent)`

*Contributor-facing guide for cgm-remote-monitor's write step (queue `WC-STEP-PATCH`). Drafted 2026-10-27
against local branch `feat/write-intent` `a0e7fcac` (slices 1-3). It moves into the cgm-remote-monitor
repository with the step's first pull request. Design:
[write-contract spec §2](../../tenancy/write-contract-spec-2026-10-07.md),
[design note](../wc-step-design-note-2026-10-27.md).*

## The rule

**A write rule goes into `lib/storage/write-intent.js`, not into a route.** A write rule is anything
that decides what gets stored for a write: the form of `_id`, which stored record a write targets,
whether a match merges, replaces or is refused, server dates (`srvCreated`, `srvModified`), unit
conversion, validation, removal of duplicates. Routes (API v1, API v3, the socket, in-process
callers) say what they want written and pass it to the step; they do not call the storage adapter's
write methods.

Why: when the same rule lives in each route, a fix lands on one path and misses another. BF-194's unit
conversion had to be added in four places, and WRITE_VALIDATION sits in five. The step puts each rule
in one place.

## How a route writes

```js
const writeIntent = require('../storage/write-intent');
const step = writeIntent.forCollection(storage, 'food', 'v1/internal');

const result = await step.write({ op: 'create', docs: [doc] });
// result.items: one per document, in order:
//   { index, outcome, _id, identifier, reason }
//   outcome is one of: inserted, merged, replaced, unchanged, deleted, not-found, refused
```

Operations today: `create` and `update` (with `docs`), and `delete` (with `target: { _id }`). The
source name (`'v1/internal'`, `'socket'`) selects that path's rules.

## How rules are written

Each collection has a row in `COLLECTION_RULES`, keyed by source and operation. A row is data, built
from a small vocabulary defined in the same file:

| field | what it says | values today |
|---|---|---|
| `id` | the `_id` form to write under | `stored-or-new`, `objectid-or-new`, `stored-string-or-objectid` |
| `target` | the filter that names an existing record | `id-eq`, `id-plain`, `none` |
| `onMatch` | what happens when a record matches | `replaced` (release 1) |
| `twins` | removing a record stored under the other spelling of the same id | `remove-string-forms`, `remove-string-forms-after` |
| `dates` | server dates | `carry`, `stamp-created`, `none` |
| `write` | the storage call | default bulk replace, `replace-one`, `insert-one` |
| delete `target` | which stored forms a delete removes | `every-form`, `id-match` |

To change a rule, change the row. To add a rule the vocabulary lacks, add a named entry to the vocabulary
and use it from the row, rather than writing code in a route.

**Release-2 variants.** Release 1 changes no behaviour, so where two paths do the same job differently
today, the table keeps both, for example `remove-string-forms` and `remove-string-forms-after`. Each
such variant carries a comment `// release-2: Q-x`, naming the queue item (`WC-R2-QA` ... `WC-R2-QH`)
that will unify it. Do not "tidy" a variant without that item's decision.

## Enrolling a module

1. Route the module's writes through `forCollection(...).write(...)`.
2. Add the module (or, in a file that still has other writers, the functions) to `ENROLLED` in
   `scripts/check-write-intent.js` (G2). G2 then fails if the module calls a write method directly.
3. Prove nothing changed (below).

## Proving nothing changed

From the alignment repository, with a MongoDB the worktree's tests use:

```sh
WC_WORKTREE=<your worktree> WC_MONGO=mongodb://127.0.0.1:<port> \
  node tools/qc/write-contract-matrix.js --out after.json
node tools/qc/write-contract-matrix.js --compare tools/qc/results/write-contract-matrix/dev-db3b9e4e-v2.json after.json
```

**G1** must report 0 differing cells, setting aside the `cache` field, which is racy (more so for records seeded straight into MongoDB). The v2 pin (456 cells) adds forms for an update over a stored string twin, a failed `_id` read on the socket, and deletes by a custom or numeric `_id`; its 360 older cells equal the first pin. A differing cell is a behaviour change: stop and find out why,
and never edit the pin to make it pass. Then:

- break each rule you moved and show the matrix (or, where no matrix form reaches it, a test) goes red
  only where you expect;
- run `npm test` and `node scripts/test-tiers.js check`;
- run `node tools/queue/gates/write-rule-copies.js --ref <your branch>` in the alignment repository.
  The count of write-rule copies outside the step may only go down.

## What the step does not do

- It does not emit or change `storage-write-committed`. That event belongs to the persistence boundary
  below the storage interface (`lib/storage/write-step.js`), and its contents are an open decision
  (D-EVENT).
- It does not call the driver. It calls the storage interface.
- Routes keep authorization, request parsing and reply shaping.
