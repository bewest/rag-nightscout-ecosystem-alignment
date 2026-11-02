# Current-dev PostgreSQL transaction-pool proof

Run from the alignment repository with Docker available and the local
`externals/work/crm-multitenant-20261102` dependencies installed:

```sh
node tools/lab/postgres-foundation/harness.js
```

`WORKTREE` can select another owned integration worktree relative to the
alignment root. The lab uses the actual `postgres-connection.js`, the committed
generated entries DDL, pinned local images, synthetic documents and a random
isolated Docker network. It publishes only dynamic loopback ports. Credentials
are generated into a private temporary directory, never printed, and removed
with only the lab's own containers/network on completion.

Two independent application clients share exactly one PgBouncer backend in
transaction mode, without automatic per-transaction session reset. Checks
cover reads/writes, rollback, binding cleanup and generated-column handling of
dirty/missing/null fields. Controls disable RLS, grant BYPASSRLS and mutate the
actual connection module's binding to session-local in memory (no source-file
edits). The latter must leak a tenant to an unbound second client.

Nonzero exit means failure. Successful JSON is sanitized evidence, not production
acceptance. This exercises the existing DDL but does not refresh its historical
index catalogue, build the migration runner or implement the entries adapter.
The generated DDL still needs current v3/history/identifier-index reconciliation.

The same run also exercises the opt-in typed-key candidate generated with:

```sh
python -m tools.nsschema.emit.postgres_emit --collection entries --identity-kinds \
  --out tools/lab/postgres-foundation/generated
```

Four `identityChecks` use the actual integration worktree's identity codec.
`id_kind` is separate storage metadata; it never becomes a client field.
The key is `(tenant_id, id_kind, _id)`, so ObjectId, lower/upper-case strings
and custom string ids remain distinguishable. A kind-scoped delete preserves
the other kind and the other tenant. Invalid kinds/encodings refuse; mutating
the codec to flatten kinds recreates the key collision. This is not a complete
adapter or import/round-trip proof for arbitrary BSON values.

The report's `adapterBlockers` are **unsatisfied M1 properties**, not passing
adapter acceptance. The probe demonstrates that normal JSON serialization
collapses an ObjectId and the same-spelling string into one primary key; raw
Extended JSON fails the generated string-only `_id` constraint instead. It also
checks the actual emitted index inventory for missing current v3/identifier
requirements. These findings require a lossless identity representation and
operator-managed migrations before adapter promotion. The typed candidate
discharges the narrow identity representation proof, not those broader gates.
