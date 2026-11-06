# Source-control runner continuation — 2026-11-06

**Reproduced candidate:** `83582e876dd193f4448f44c28e379fb5464a26c7`. Its complete diff from accepted `8713395992e07b4dd2cde61ee972e9a15c8ada8c` changes only `scripts/test-durable-replay-controls.js`: copy the two required fixture files into private scratch, create their parent directory, and reject Mocha's `Cannot find module` text as an invalid control. All other repository paths are identical, including application modules, tests/assertions, migration catalogues, CLI, build configuration, dependency manifests and corpus runner. [Machine identity/results/artifact capsule](control-recovery-runner-continuation-83582e87-2026-11-06.json).

The original runner was reproduced failing: its newly required `./fixtures/tenant-durable-replay` was absent in scratch, so even the restored positive failed. The missing-module result is preserved; the initial sandbox child-process `EPERM` is separate environment evidence. Neither is treated as a valid semantic control.

```bash
TZ=UTC node scripts/test-durable-replay-controls.js <fresh-private-output>
```

The repaired runner executed all five authored source breaks: advanced empty-cache bootstrap, typed identity, soft deletion, scan-row bound and repeatable-read transaction selection. Each produced its expected assertion, followed by a fresh **22-passing** restoration. Bootstrap also produced a downstream TypeError after the deliberately missing projection; that extra symptom is retained rather than counted as a second independent semantic guarantee. These are source/fake-connection checks, not PostgreSQL or process evidence. Changed-script lint reports zero errors and eight private-path warnings; whitespace check passes.

The required final prcheck ran last on the committed candidate: exit zero, `OK`, clean unchanged head, containing `official/dev 4a482627bfdafb1fef8dcbe0ac6c484811cae563`. No application tests ran afterward. Comprehensive full/browser/corpus/client/pooler results remain attributed to their actual executed 871 ancestor and are reused only by complete changed-path identity; no broad repeat was spent on this source-control-only repair. The separate archived policy/replay controls likewise retain their actual source and instrument versions. This record is local acceptance provenance, without a remote publication, default activation or full milestone-completion claim.
