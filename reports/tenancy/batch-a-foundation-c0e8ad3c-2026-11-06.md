# Batch A PgBouncer foundation continuation — 2026-11-06

Reproduced bounded proof on clean application `c0e8ad3c562f5d6df3652bf2ba8d161fc1f69cf6`.
This separately authorized continuation followed the stopped corpus attempt; its passing result
neither waives that failure nor completes final acceptance.

Existing `tools/lab/postgres-foundation/harness.js` ran once, unchanged, against the selected
worktree's actual PostgreSQL connection module and typed identity codec. Exit zero; empty stderr.
PostgreSQL 16.15 and PgBouncer 1.25.2 used the locally available pinned images recorded in the
JSON companion. No source fix, dependency replacement, alternate image or repeat was needed.

| Check group | Passing | Failing |
|---|---:|---:|
| Connection, RLS and transaction pooling | 9 | 0 |
| Typed identity candidate | 4 | 0 |

Two independent application clients reused exactly one backend in transaction-pooling mode,
`default_pool_size=1`, with `server_reset_query_always=0`. Checks cover tenant-isolated
reads/writes, unbound refusal, cross-tenant write/TRUNCATE refusal, rollback, binding cleanup,
and dirty/missing/null fields. Typed checks preserve ObjectId/string twins and case distinctions,
kind-scoped deletion, and invalid-kind/encoding refusal.

The controls demonstrated the intended broken states and restored comparators within this run:

- Disabling actual RLS exposed foreign rows through the same pooler; restoring RLS hid them.
- Granting BYPASSRLS caused the application's startup-role rejection.
- Mutating the actual connection binding to session scope leaked the tenant to an unbound pooled client; clearing it and restoring the original binding restored isolation.
- Flattening the actual codec's identity kind reproduced a uniqueness collision; the original codec stored both kinds.

## Command and ownership

From alignment root:

```bash
WORKTREE="$APP_WORKTREE" node tools/lab/postgres-foundation/harness.js > "$FRESH_JSON" 2> "$FRESH_STDERR"
```

The actual invocation was wrapped by the resource observer. It recorded two new containers and
one anonymous mounted volume, all independently verified absent after harness cleanup, with the
exact unique network absent. No audit volume removal was needed; the volume count stayed 462.
Unknown historical resources were preserved. Runtime released at 21:04:14Z.
The first exact-network audit helper expected Docker's alternate “no such network” diagnostic;
Docker returned “network … not found”. The corrected read-only audit accepted that observed
absence wording. No network or fixture was recreated.

## Limits

Historical generated entries DDL is a fixture here. Its two `adapterBlockers` describe that
historical fixture's untyped primary key and missing current indexes; they do not measure or
reverse current operator-migration/adapter evidence. The typed candidate discharges a bounded
identity check, without proving arbitrary BSON import fidelity. This is no complete migration,
HTTP, performance, HA, operational or milestone acceptance claim.

The failed corpus capture remains immutable. The coordinator owns runner repair, the next
expanded-corpus run, final prcheck, any criterion promotion and publication. No push occurred.

Machine record: [batch-a-foundation-c0e8ad3c-2026-11-06.json](batch-a-foundation-c0e8ad3c-2026-11-06.json).
