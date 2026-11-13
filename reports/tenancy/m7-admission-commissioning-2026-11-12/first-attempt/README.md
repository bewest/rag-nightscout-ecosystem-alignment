# First admission commissioning attempt

**Reproduced: commissioning failed during infrastructure bootstrap, before any worker started.** The source-qualified image and reviewed runner did not establish runtime acceptance. Exact source, instrument and plan pins are in [the selected summary](summary.json).

Bootstrap exited with `CONNECTION_BUDGET_PRIVATE_DIRECTORY`. A separate mount-only fixture reproduced the mechanism: binding only the profile file leaves its container parent owned by root with mode 0755. The private reader rejects that directory. Binding a new private copied directory preserves owner 1000 and mode 0700 and succeeds. The guard remained unchanged. Worker plan mounts need the same private-parent property; the deployment owner is joining that repair with the later count-oracle source before a new freeze.

The original run retains its failure and uncertainty. Its two exact PostgreSQL/Vault containers are stopped and retained, verified by an independent full nonce-project census and image/birth comparison. No normal worker retirement is claimed. Both mount-only fixture containers were independently confirmed absent; the original prepared profile was unchanged. Raw captures, private state and identifiers remain outside Git.

The runner’s ten focused host/model checks pass, including sticky uncertainty after command/receipt failure and exact image custody before worker start. Those source checks do not override the real bootstrap failure. The [stored-count source/compiler proof](../../m7-stored-count-oracle-2026-11-12/README.md) remains a separate capability. No clinical, native-capacity or production acceptance is granted.
