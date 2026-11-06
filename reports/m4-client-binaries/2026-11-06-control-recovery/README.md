# Control/recovery default-client compatibility — 2026-11-06

Reproduced on archived application `8713395992e07b4dd2cde61ee972e9a15c8ada8c`: registered default cgmsim and oref0 passed **82/82 checks**, with **19 paired cells**, zero differing or unexplained cells, and no missing cells. Independent Mongo/PostgreSQL stored-value assertions and wrong-tenant, revoked, absent-credential and unknown-alias refusal/no-effect controls passed. The positive default gate exited zero; all seven gate findings passed.

This measures existing unselected behavior across the single-site Mongo baseline and explicit multitenant PostgreSQL/Vault preview at the same source commit. Dormant owner-policy reader options remain unselected. Selected-mode actual clients, connector clients, mobile/v3 binaries, sockets, TLS, retry soak and performance remain unmeasured by this capture. No milestone promotion or application-wide acceptance is claimed.

The unchanged canonical [gate](../../../tools/queue/gates/m4-client-binaries.js) archives source, verifies the matching private dependency lock, and invokes the [runner](../../../tools/lab/m4-client-binaries/README.md). This fresh capture used alignment `09bfcde7984aa7b3964dccd889114e262ec30076`; exact instrument SHA256 values, environment versions and image identities are in [summary.json](summary.json). The pinned client root supplied cgmsim `c09f9c039007a80a431baec6dbf852c52e3669db` and oref0 `d219baf9559d62a8bb0bd42014192a2d7c0839ef`. Fresh source compilation matched all **94** cgmsim runtime JavaScript files with locked TypeScript 4.9.5. Connector metadata in the summary identifies an installed pin, not an executed client.

[Baseline cells](cells-baseline.json), [preview cells](cells-preview.json) and [classification](classified.json) retain synthetic payload comparisons. No classifier exceptions were added. This run exercised the embedded negative controls; deliberate wrong-oracle and classifier-corruption instrument campaigns were not repeated. Their earlier instrument evidence is separate in the [preceding capture](../2026-11-06-revised-freeze/README.md).

Runtime was claimed at 21:46:46Z and released at **21:48:00Z**. Independent Docker inspection verified all **54** owned containers absent and all **5** exact captured mounted volumes absent; no deletion was needed. The observer captured 28 containers and zero errors; the run manifest supplied identities for additional short-lived clients. The volume inventory returned to **462**. [Cleanup evidence](cleanup.json) contains exact owned identities. Capacity at claim was 80G available and 100 readable inotify instances (limits 128 instances / 1048576 watches); pre-existing host resources were preserved.

Local private capture and runtime handoff are retained under `externals/work/control-recovery-client-scratch-20261106` and `externals/work/HANDOFF-codex-control-recovery-client-20261106.md`. No source edits, activation, full/browser/corpus campaign or final prcheck were performed in this lane. Comprehensive acceptance follows under its own ownership and capture.

Capture command used the unchanged gate with `TZ=UTC`, `NS_M4_GATE_REPO` selecting the frozen integration worktree, `NS_M4_GATE_DEPENDENCIES` selecting the acceptance lane's matching private physical dependency installation, `NS_M4_EXTERNALS` selecting the dedicated pinned-client root, and `NS_M4_GATE_OUT` selecting a fresh private output directory. No client-selection override was set:

```bash
node tools/queue/gates/m4-client-binaries.js --ref 8713395992e07b4dd2cde61ee972e9a15c8ada8c
```

Record verification: `make queue-check` and `make docs-links` passed with host execution after linking the existing ignored local external paths into the isolated evidence worktree. Initial queue validation refused the absent local `nc-jitter` path; initial sandbox documentation checking refused `spawnSync git` with `EPERM`. These were environment setup failures, preserved privately; neither altered the gate result or source. No generated queue view, runtime code or site page changed.
