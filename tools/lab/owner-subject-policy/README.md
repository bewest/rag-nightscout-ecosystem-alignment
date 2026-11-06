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

## Optional nested-container audit

`docker-audit.js` can be symlinked as `docker` in a private per-campaign PATH
folder. Set `NS_OWNER_DOCKER_REAL` to the absolute real Docker executable and
`NS_OWNER_DOCKER_AUDIT` to a fresh private 0700 directory. The helper stores only
returned full container IDs, volume names and cleanup state in 0600 files, before
subsequent inspections can fail. It augments supported top-level `rm` calls only
when every current target ID is in that campaign's records, then removes by those
immutable IDs. A reused container name cannot redirect augmented removal.

Unsupported commands/flags and unknown/mixed targets pass through unchanged.
This is scoped test instrumentation, not a general Docker permission boundary.
The extra `--volumes` flag removes anonymous volumes; Docker preserves named
volumes ([Docker CLI contract](https://docs.docker.com/reference/cli/docker/container/rm/)).
It never issues a direct volume delete or global prune. Recorded removal success
is not proof of volume absence; the campaign must inspect the recorded IDs after
cleanup. Nonzero create/run outcomes without a returned ID cannot establish
ownership and are not claimed leak-free. Detached successful test services are
the supported creation path. A failed audit triggers exact-ID compensation;
failed compensation retains and reports the returned ID for private recovery.

Pure/fake-process checks run with `node docker-audit.test.js`; child-process
execution must be permitted. Fake checks do not start Docker or establish real
Docker behavior. Runtime smoke must wait for the coordinator's explicit slot.
