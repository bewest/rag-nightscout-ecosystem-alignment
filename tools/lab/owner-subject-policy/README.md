# Owner subject-policy evidence instrument

This additive lab archives an exact cgm-remote-monitor commit and runs its actual
subject-policy tests. It never checks out or mutates another worktree. Source,
dependencies and a writable scratch root must be explicit. Use a scratch root on
a filesystem with capacity; this lab does not assume `/tmp` is available.

```bash
node tools/lab/owner-subject-policy/archive.js \
  --repository "$CRM_REPOSITORY" --dependencies "$CRM_DEPENDENCIES" \
  --ref "$CRM_COMMIT" --scratch-root "$OWNER_SCRATCH"
```

The default runs the pure catalogue/Shiro tests without services. Add `--database`
only after the shared test coordinator grants capacity. The database suite creates
its own synthetic PostgreSQL service, records its returned container and volume
identities, uses private roles, removes that exact service and its volumes, and
checks cleanup. It covers the selected existing subject-management update path;
it does not implement an owner login, issuer, listener or complete role platform.

`--control universe` replaces closed-universe membership with the prior literal
shape check in scratch and selects the namespace-prefix rejection test. Predicted
result: one missing expected TypeError. A successful instrument control exits zero
only after verifying the underlying test failed for its intended assertion.

With `--database`, `--control catalogue`, `ceiling`, `delegation` or `actor` removes
one source guard only in scratch and selects its independently bounded HTTP test.
Predicted result: one assertion sees an unauthorized HTTP 200 instead of 403.
The instrument accepts a control only for that semantic failure. A timeout, hook
failure, service setup error, pending test or unrelated assertion is invalid.
The original guard must pass again on a fresh restored archive.

The reviewed permission universe bounds the current REST surface. Shiro literals
still imply descendants outside it. Adding new authorization operations requires
reviewing the universe and implication tests; this lab does not prove arbitrary
wildcard/default semantics, complete owner management, throughput or deployment
readiness. Queue and release integration belong to the coordinating lane.
