# D6 PostgreSQL native discriminators

Contributor-facing native proof instrument. It tests PostgreSQL SQL logical-decoding
privileges and transaction granularity, not a shipping D6 reader. Source attribution
comes from the required clean `--worktree`; the synthetic schema follows the tenant
binding/FORCE RLS pattern and deliberately omits application runtime behavior.

```bash
python3 tools/lab/d6-native-discriminators/proof.py \
  --worktree /absolute/path/to/clean/cgm-remote-monitor \
  --out /tmp/d6-native-proof-unique.json
```

Requires Python 3, Docker access and the pinned PostgreSQL image named in the script.
Each run creates a uniquely named container with no network and no published port,
uses only synthetic rows, and removes that container and its anonymous volume in
`finally`. Existing containers and databases are never selected or changed. An
existing output path is refused. The run normally takes seconds; timings include
`docker exec`/`psql` and are not performance measurements.

Expected outcome: `PASS`. The wrapper owner is NOLOGIN, NOSUPERUSER, NOBYPASSRLS and
REPLICATION. The reader login is NOREPLICATION with only EXECUTE on fixed-slot
functions; serving identities cannot invoke them. Native publication decoding can
expose both tenants' metadata while normal SQL retains tenant RLS. This is an
intentional privileged feed boundary, not proof that logical decoding enforces RLS.

Controls broaden an isolated RLS policy and publication, confirm the isolation/leak
assertion would fail, restore them, and check a newly written excluded row. Previously
published changes remain in slot history after publication membership is restored.

A 5,000-row transaction exceeds the `upto_nchanges=1` target. The wrapper records
its actual emitted row count, proving that outer `LIMIT 1` limits the client result
but does not bound this instrumented PL/pgSQL decode/materialization.

No runtime wrapper-body/publication/owner pinning, byte/memory hard cap, notification
commit/acknowledgement protocol or application restore acceptance is implemented here.
See the [captured evidence](../../../reports/tenancy/d6-native-discriminators-2026-11-11/README.md).
