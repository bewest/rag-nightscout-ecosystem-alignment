# D6 native privilege and transaction-size discriminators

*Contributor-facing measurement record, captured 2026-11-11 (America/Los_Angeles).
Synthetic data only. Completed captures are retained unchanged. This qualifies
PostgreSQL behavior and a prototype wrapper shape; no shipping reader is implemented.*

The native proof supports a dedicated EXECUTE-only reader login without granting
that login REPLICATION, superuser or BYPASSRLS. Its privileged NOLOGIN wrapper owner
can decode cross-tenant metadata even though ordinary SQL remains constrained by
FORCE RLS. SQL polling is feasible, but its change-count target is not a hard batch,
byte or memory bound.

## Source and instrument

| Anchor | Captured value |
|---|---|
| D6 source head checked clean | `9179146638094fcf2b0f642a51d03a272098168e` |
| Alignment base | `7d3399ddc731b1719fceee49317476aeb6eec897` |
| Recovered decision source | alignment `7093dccda`, D6 paged backstop / SQL reader / activity control decisions |
| PostgreSQL | `16.15 (Debian 16.15-1.pgdg13+2)`, x86_64; `wal_level=logical` |
| Image | `postgres@sha256:5db6dac2ef5dcff512f4f00a009c3c332b9f2f28f24277175bf3e4a3d02ef83a` |
| Final harness SHA-256 | `c2aa02bebe72ae7f42689666334cadaff819a818cb4ddd35fe47ebc4b033d412` |
| Instrument | [proof.py](../../../tools/lab/d6-native-discriminators/proof.py) |
| Accepted capture | [run-4.json](run-4.json): reproduced `PASS`, 36 SQL cases, 22 assertions; owned-container cleanup exit 0 |

Run from the alignment repository:

```bash
python3 tools/lab/d6-native-discriminators/proof.py \
  --worktree /absolute/path/to/clean/cgm-remote-monitor \
  --out /tmp/d6-native-proof-unique.json
```

The script records the supplied source head and requires it clean. It tests native
SQL with a simplified synthetic clock/activity schema following the existing FORCE
RLS tenant-binding pattern; it does not import shipping modules or claim runtime
execution on that head. Each run creates only its uniquely named, network-isolated
container with no published port. Timings include client/container overhead and
are not a capacity result.

## Reproduced findings and controls

| Property | Native result | Control/restoration |
|---|---|---|
| Normal SQL retains tenant isolation | Tenant-A serving session sees A only; unbound serving session and unbound wrapper-owner SQL see zero clock rows. Both clock/activity tables retain FORCE RLS. | Broadened clock policy exposes A and B to bound A, so the original equality assertion is red. Restored policy returns A only. |
| Raw replication authority is unavailable to reader/serving logins | Direct slot calls fail with SQLSTATE `42501`; reader cannot assume privileged owner, alter wrapper owner, alter publication, or advance the other slot directly. | The same fixed-slot peek succeeds through the wrapper, distinguishing a privilege boundary from a broken database/slot setup. |
| Fixed wrapper can decode selected cross-tenant metadata | Owner is NOLOGIN/NOSUPERUSER/NOBYPASSRLS/REPLICATION; reader is NOREPLICATION. Decode contains A and B metadata, excludes the unrelated synthetic marker. | Wrong-slot/publication argument shapes do not exist; target outside the allowed range is refused. Reader has no SQL privilege to change publication or wrapper. These test signature/SQL privileges, not runtime tamper pinning. |
| Publication filtering is essential | Unrelated table initially excluded. | Adding it to publication and writing a marker makes the exclusion assertion red. After restoring membership, a **new** excluded marker is absent; the marker committed while published still replays from history. |
| SQL target permits transaction-sized overshoot | One transaction inserts 5,000 clock rows. `upto_nchanges=1` returns 5,003 messages and 289,012 binary data bytes: 5,000 INSERT messages, one COMMIT, plus relation/BEGIN metadata. Repeated peek returns identical counts/bytes. | The independent INSERT/COMMIT counts establish that the large transaction was actually decoded, rather than an unrelated setup/query result. |
| Outer LIMIT does not hard-bound this wrapper's decode | Outer `LIMIT 1` returns one message/21 bytes, while instrumented `GET DIAGNOSTICS ROW_COUNT` records 5,003 rows emitted by `RETURN QUERY`. | Same transaction remains replayable; full peek confirms the batch remains. Advancing through its maximum returned LSN makes the next peek return zero. |

`feed.advance` in this prototype accepts a caller-supplied LSN for the fixed slot.
It contains slot selection but does not prove safe acknowledgement ordering or
prevent a compromised reader from skipping its own feed. The production reader
must advance only through the last completely notified transaction after the
notification transaction commits; duplicate hints remain valid after a crash.

PostgreSQL documents transaction-granularity stopping and SQL binary output in
[replication management functions](https://www.postgresql.org/docs/16/functions-admin.html)
and [logical replication message formats](https://www.postgresql.org/docs/16/protocol-logicalrep-message-formats.html).
The native RLS observation above is specific to the tested SQL `pgoutput` path and
prototype wrapper. Do not generalize it to replication connections, serving reads
or a logical restore authority change.

## Retained failures and instrument repair

- [run-1.json](run-1.json): setup only, **NO-MEASUREMENT**. Socket `pg_isready`
  observed the image's temporary initialization server immediately before shutdown;
  subsequent psql calls saw shutdown/missing socket. The instrument now waits for
  final TCP loopback readiness. No semantic control claim attaches to this failure.
- [run-2.json](run-2.json): exploratory successful SQL calls before semantic assertions
  and planted controls were added. It is not the accepted assertion capture.
- [run-3.json](run-3.json): retained **FAIL**. The restoration assertion wrongly
  expected removal from publication to suppress a row committed while that table
  was published. The actual historical row remained visible on replay. Run 4 keeps
  that observation and tests restoration using a new row committed after removal.
- Earlier captures carry their own instrument hashes. Those exploratory instrument
  variants were not committed; only the final instrument is reproducible from this
  branch. They are diagnostic history, not alternative acceptance evidence.

## Remaining implementation/measurement boundary

UNMEASURED: runtime pinning/admission of exact wrapper body, owner attributes,
publication membership and slot/plugin identity; malformed/foreign pgoutput
relation rejection; notification-before-advance crash behavior; retained-WAL and
slot-invalidation recovery; true time/byte/memory bounds under large transactions;
reader/listener process integration; pause/suspend without data writes; paged
recovery latency; application restore/epoch/current-authority suites; capacity.
No RLS policy or restore authority change is proposed from this proof.
