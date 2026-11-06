# Completion-batch source checks — 2026-11-06

Immutable contributor-facing capture. These reproduced checks support local
incorporation and research, not integrated acceptance or milestone promotion.

## Batch A application candidate

Tree `863c8a2b3fa7ac3e13ecb5f7dca90de6766bb7e0` incorporates the repaired
multitenant corpus inventory, typed role table and narrow M4 identity/literal-slash
repairs. Matching dependency lockfiles were compared equal before verification.

```bash
NODE_ENV=test TZ=UTC node node_modules/mocha/bin/mocha.js --exit --timeout 5000 \
  --require ./tests/hooks.js tests/serve-listeners.test.js \
  tests/nightscout-cli.test.js tests/runtime-policy.test.js \
  tests/serve-roles.test.js tests/postgres-filter.test.js \
  tests/write-intent.v1-collections.test.js
node scripts/test-tiers.js check
node scripts/test-multitenant.js --list
```

Reproduced: 201 passing, no failing or pending cases in the selected files;
tier registry 512 files / 8 tiers; corpus inventory 34 opt-in suites, of which
20 start their own containers. The inventory command starts no fixture. The
combined source diff check passes. A prior sandbox run failed child-process
checks; the same focused selection was repeated outside that sandbox. Sandbox
failure logs remain local and are not counted as semantic control evidence.

Actual client execution on this candidate, PostgreSQL/MongoDB parity, full suite,
browser, enabled corpus, current upstream fetch/merge and final prcheck were
**not run**. The previous M4 captures are on another application tree. This
candidate is not application-ready. The remaining malformed-token response
difference remains open; no authorization policy or classification exception was
introduced to hide it.

## M5 isolated research

Tree `25c8441a861fb3d8f9aff3f559d833f2db8ab448` contains an isolated prototype
under `research/m5-replay/`, without runtime imports, migrations or a listener.

```bash
node research/m5-replay/prototype.test.js
```

Independently reproduced: 8 passing, 0 failing, 0 skipped. Its child-process
SIGKILL case uses an atomic synthetic fixture file, not PostgreSQL. Typed
cohorts, restart, duplicate delivery and rollback are model checks. RLS,
concurrent PostgreSQL replay, current-row overwrites and real consumer recovery
remain **UNMEASURED**.

The prototype evaluates recovering a projection together with its checkpoint.
A checkpoint alone does not restore an empty cache. Durable projection versus
verified full bootstrap remains a production contract decision; neither is
adopted by this capture. The durable-delivery contract remains draft, and role
bookkeeping authority remains unresolved. Decision deferred, research continuing.

## Programme integration

The isolated alignment coordination branch incorporates the authority instrument
repair, immutable partial R57 and completed R58 captures, and the approved larger
completion-batch plan. After combining these records, `make queue-check` passed
and `make docs-links` reported 26 checked / 0 failing. No queue refs, milestone
claims, serving defaults or public branches changed. No application full campaign
was spent on this source-incorporation step.

Local raw outputs: `/tmp/codex-batch-a-combined-focused.log`,
`/tmp/codex-batch-a-final-tier.log`, `/tmp/codex-batch-a-final-corpus.log`,
`/tmp/codex-m5-replay-root-verification.log`,
`/tmp/codex-completion-final-queue-check.log` and
`/tmp/codex-completion-final-docs-links.log`. Lane ownership and exact local
worktrees are recorded separately in the untracked coordinator handoff.
