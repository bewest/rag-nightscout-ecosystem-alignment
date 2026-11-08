# Complete enabled multitenant corpus — accepted

**Reproduced:** all 47 enabled suites completed on frozen application `39f4afb17f8ffeea2e672fdc2423a585f652e61d`, tree `42c8bc392edfd0dd3f6c235b8b7834b273c05aa7`: 537 passing, one pending, zero failing. [Machine summary](summary.json).

The actual command was `node scripts/test-multitenant.js --record <fresh owned record>` with no `--only` filter and benchmark mode `0`. The unchanged full-corpus guard checked actual complete inventory and raw results; the one disabled clock-benchmark test remained pending. This is one complete run, not a sum of focused or incomplete attempts. The [earlier c23 failure](../c23-corpus-failed/README.md) remains immutable. The original operations and clinical test-only repairs were joined before this freeze.

The runner completed in 271.2673489660956 seconds. The independent durable observer accepted 41 containers, 58 volumes and 125 observed births with no errors; every declared owned container/volume was verified absent. All three supervisor steps passed, with host processes closed and direct children reaped. Root independently captured exact baseline inventory/selected static metadata and verified all 265 retained supervisor/owner births absent. Global host quiescence and database concurrency were not measured.

Private copied dependencies and c23-built host assets passed existing source/lock/asset guards. [Measured source equivalence](../39f4-source-equivalence.json) retains c23 attribution for earlier native/full/browser results. Raw immutable captures are `externals/work/m6-final-corpus-39f4-20261107` and its observer/supervisor siblings; exact finite grants, pins, commands and independent release are in the local lane handoff. Cold Compose and actual client acceptance remain separate.
