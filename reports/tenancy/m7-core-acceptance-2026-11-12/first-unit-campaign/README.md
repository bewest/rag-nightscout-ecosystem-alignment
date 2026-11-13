# First frozen-core campaign: failed unit tier

Reproduced on core `d5e2e874659155c952b5b5deb862f12f982ac02e`, deployment metadata `bc7b8c56b19d7a87fea668e0adb8b939e580de1e`, remote instrument `3d8ca353f973433021ae2086cd643d03da5fb3a4`. [Extracted receipt](receipt.json) records source, instrument, command outcomes and SHA-256 of original private captures. This is a failed campaign, not an acceptance receipt.

Owned exact-lock dependencies, production bundle, tier inventory, pinned browser provisioning and database fixture preparation passed. Unit exited 29: **3478 passing, 1 pending, 29 failing**. The campaign stopped; subsequent tiers and enabled corpus were **NOT RUN**. Node v24.22.1/npm 11.19.1 ran on Linux 6.8.0-147-generic Ubuntu x86_64; unit uses checked-in environment loading (`env:true`), hooks, 5000 ms timeout and parallel setting 2. No deadline was reached.

| Failure group | Classification and next boundary |
|---|---|
| Three internal composition failures | Reproduced stale wire-version fixture; [repair and separate fence controls](../../m7-unit-repairs-2026-11-12/internal-api-composition/README.md) |
| Twenty-five tenant operations failures | Reproduced omitted issuance migration in fake database; [model repair and inventory control](../../m7-unit-repairs-2026-11-12/tenant-operations/README.md) |
| One realtime config cache failure | Unclassified at capture. Expected changed parsed value 2, returned 1. Targeted environment probe required before choosing a repair |

The coordinator joins all repairs before refreezing and repeating comprehensive acceptance. Focused repaired suites do not turn this failed campaign green. Original captures remain under local `externals/work/perf-cloud-core-20261112/core-acceptance-20261112-a/decoded/core-acceptance`; raw private environment and container connection details are not published. The worker verified its owned Mongo cleanup and zero fixture container/volume residuals; cloud resource teardown is independently recorded by the remote owner.
