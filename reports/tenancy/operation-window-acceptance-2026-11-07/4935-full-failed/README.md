# Joined 4935 full non-browser failure

*Contributor-facing measurement record, captured 2026-11-07. Reproduced;
immutable. [Machine-readable summary](summary.json) owns figures and artifact
hashes. This is a failed application campaign with verified physical closure.*

The full non-browser command ran on application
`4935aa77049c66793669a7be940e40ed6ba5b386`, tree
`5271a0f21ec07c30fc45532bcf761ac8215c4e1a`, with a private exact-source
verification worktree and newly built assets. Publishing and verification
worktrees remained clean at that exact commit through exit. The runner exited 2.

| Tier | Passing | Failing | Pending |
|---|---:|---:|---:|
| unit | 2801 | 2 | 0 |
| dom | 205 | 0 | 0 |
| dependency | 368 | 0 | 2 |
| core | 319 | 0 | 0 |
| harness | 99 | 0 | 0 |
| integration | 3977 | 2 | 172 |
| stress | 18 | 0 | 0 |

Two selected suppression read-scope protocol tests failed with
`NOTIFICATION_SCHEMA_UNSAFE`. Two executable PostgreSQL/Vault preview tests
returned HTTP500 where unknown-host and untrusted-immediate-peer refusals
required HTTP404 and HTTP400 respectively. These assertions establish observed
failures; they alone do not establish a source cause. Repairs and their focused
controls belong to their subsequent source records.

The independent observer reported cleanup verified and no observer errors. It
attributed 22 owned containers, 32 volumes and 166 process births. Separate fresh
readback verified exact baseline inventory, unchanged baseline metadata and
absence of every observed process birth. Supervisor and all retained births
were independently absent; no runtime grant remains active from this run.

Default-browser, entire enabled corpus, suspended-tenant restart, actual Compose
UI/restore, client and whole-M6 acceptance do not follow from this attempt.
Earlier accepted native evidence remains attributed to b029. Local immutable
captures and closure proofs are linked from
`externals/work/HANDOFF-m6-acceptance-continuation-20261107.md`.
