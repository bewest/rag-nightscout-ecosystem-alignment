# PostgreSQL transaction final-floor component — 2026-11-06

Reproduced on instrument `f0e53977ae2bad89c0402f722d203c499bede65f`, archiving
candidate `1acb4eee76adf229bfa04f0e9c1fbc51ba3edcc9`. This is bounded component
evidence using synthetic physical markers through the actual PostgreSQL
connection, date allocator, clock decorator and logical event wrapper. It does
not establish every canonical intent/no-op allocation policy or whole-roadmap
completion. Broad acceptance remains separate.

| phase | passing | failing | pending | exit | result |
|---|---:|---:|---:|---:|---|
| ordinary | 6 | 0 | 0 | 0 | reproduced |
| final-argument omission control | 0 | 1 | 0 | 1 | expected semantic failure |
| fresh restoration | 6 | 0 | 0 | 0 | reproduced |

The six ordinary cases cover nested allocation/no-op/settle/later outer
allocation, fresh no-op, rollback, A/B/A on one actual backend, postcommit and
closed-context behavior, and clock-off behavior. Restoration repeats those six
cases; it adds no unique coverage.

Independent restricted observer confirms physical rows with own allocations
s1/s2 and final durable transaction floor s3. Ordinary committed event stamps
are s3/s3/null/s3. The control removes only the final callback argument; event
stamps become s1/s1/null/s2. It fails exactly one named
`EVENT_FINAL_FLOOR_MISMATCH` `ERR_ASSERTION`, actual matching stored s1, expected
matching independently stored s3. Precommit rows remain invisible, all deliveries
follow driver COMMIT acknowledgement and foreign tenant rows remain empty.
Setup errors, pending cases or unrelated assertions are rejected by the runner.
No premature-publication or stale-tenant native control was dispatched here.

Runtime: Node v22.23.4, PostgreSQL 16.15. Image digest
`postgres@sha256:9e2cf6287f25c3151f4c9421ccce2b17f3e60061c111a29165e0d2cdd9ff0a97`.
Exactly one disposable loopback PostgreSQL container and one volume were owned.
Independent post-run inspection confirms both absent, all eight observed Node
descendants absent, all 159 baseline containers preserved, no new container,
volume or network remaining, and zero observer errors. Existing bridge network
was reused; no network was created or removed. Temporary module-resolution link
was removed; candidate/instrument tracked source is unchanged.

Earlier preflight stopped before creating services because source-unit processes
were visible. The coordinator confirmed their scope and explicitly cleared the
bounded nonperformance phase; fresh preflight found no other test campaign.
Raw initial stop and all runtime captures remain separate and immutable.

No public credential values, connection URLs, physical row objects or raw traces
are included. Raw captures have a 27-artifact private hash index. Reporter
actual/expected scalars use decimal strings; the strict runner and normalized
aggregate compare those with numeric independent storage values. An initial
strict-type aggregate extraction was preserved separately; no execution or
source retry occurred.

## Capture hashes (SHA256)

| artifact | hash |
|---|---|
| artifact-index.json | `8f2dccb2a2e5c42388ff0169505b4c70cb4e0464b2bf099754cf885fcd737d6e` |
| sanitized-aggregate-normalized.json | `b241f0719d188312843f258aadb0dc1a479427745e1827dc0451e4aaf03f1036` |
| independent-cleanup-audit.json | `e57a41e15f53abbbdb0d9cebe07575be5a4d356fae8cb919c49a7581f33dba52` |
| ordinary/mocha.json | `3d77576e1a48d95e2fd8a5852623c6f180b30e1b5261a49a4909afc5dfcf4ddb` |
| stamp-omission/mocha.json | `88a10f27068e188d334a95ece108ecc79c606a7f04c7390ef5cce59a2b4351fe` |
| restored/mocha.json | `7c3d0c40aebf14c963b46b925fffa8b0e80f29013af4a2a7b9ba1bf3211c2437` |

Reuse against a later candidate requires explicit relevant source/fixture/core
identity review. These results belong to the exact archived candidate above and
must not be labeled broad acceptance of a subsequent reader-policy removal.

The [exact instrument snapshot](instrument/) preserves the five added files from the instrument commit. Reproduction uses a new isolated application archive at the named candidate, those five files and a local instrument commit; the snapshot itself is not an active alignment-runtime entry point. [Sanitized aggregate](summary.json) and [source/raw hash references](artifact-index.json) accompany this record.
