# Evaluator inspection contract inventory — 2026-11-12

Reproduced Core D unit failure: the generic service inventory expected version1 for evaluator inspection, whose adopted scheduling-observation descriptor is version2. The production descriptor is unchanged. Local repair `ff5156b984424f1ef34bcef22d5bfa0071354cfa` changes only the existing assertion and its comment; original source is `2d0ae0354a38b4a88f43bc2ae5ec60c085058f64`.

Original focused run: eight passing/one failing, `2 !== 1`. Corrected inventory: nine passing. A disposable-process control changes only the loaded evaluator descriptor to version1 before contract compilation: eight passing/one failing, `1 !== 2`. Removing that preload restores sixteen passing across the contract and evaluator-inspection files, including actual private-UDS inspection without scheduled work or acquired authority. The check therefore still rejects descriptor regression.

Commands use Node22.23.4 and the read-only owned lockfile dependencies at their recorded historical install, not a fresh install on this source. Test files: `tests/internal-api-contracts.test.js tests/evaluator-inspection.test.js`; runner `node <owned-lockfile-dependencies>/node_modules/mocha/bin/mocha.js`. The negative run adds `--require <descriptor-downgrade-control.cjs>`; the published control uses explicit `M7_CORE` instead of the original local absolute path. Logs redact those paths only.

This is a focused fixture correction. Core D's first-tier failure and seven later tiers/unfiltered corpus NOT_RUN remain immutable; no comprehensive, clinical, native binding or capacity acceptance is claimed by these checks.
