# Frozen-head gate controls — repaired instrument continuation, 2026-11-06

**R58: bounded B4a gate evidence complete.** On unchanged application `65bb8456618df9816106692a32f0dd5c76e216d1`, the combined captures contain **12 positive instruments, 32 semantic-red controls and 12 restored positive instruments**. This is no milestone promotion or deployment admission. Queue ref moves and B5 cumulative acceptance remain their coordinator's work.

The [original R57 partial report](gate-controls-65bb8456-2026-11-06.md) and its failed instrument run remain immutable. This continuation uses authority instrument commit `3845b3a156e19fec77b9bb495117c12403a5a953`, including its sibling helper, directly from the repair worktree. The application was never modified. All other instruments are unchanged from alignment `88902eba2532c42bf83a91a8104f9ea64da2ca18`. Original accepted measurements were not rerun. Reproduced logs, complete assertion diffs, source hashes and artifact lengths/SHA-256 are in the [machine capture](gate-controls-65bb8456-continuation-2026-11-06.json).

| Continuation run | Passing / pending / failing | Result |
|---|---|---|
| next-slices-owner-policy-restored | 22 / 0 / 0 | PASS, exit 0 |
| next-slices-settings-restored | 12 / 0 / 0 | PASS, exit 0 |
| rest-authority-audience | 4 / 0 / 1 | SEMANTIC-RED, exit 1 |
| rest-authority-authority | 3 / 0 / 2 | SEMANTIC-RED, exit 1 |
| rest-authority-restored | 5 / 0 / 0 | PASS, exit 0 |
| subject-admin-atomic | 0 / 0 / 1 | SEMANTIC-RED, exit 1 |
| subject-admin-current | 0 / 0 / 1 | SEMANTIC-RED, exit 1 |
| subject-admin-positive | 13 / 0 / 0 | PASS, exit 0 |
| subject-admin-restored | 13 / 0 / 0 | PASS, exit 0 |
| subject-admin-tenant | 0 / 0 / 1 | SEMANTIC-RED, exit 1 |

## Exact red symptoms

### rest-authority-audience

```text
Error: expected 401 "Unauthorized", got 200 "OK"
```

### rest-authority-authority

```text
Error: expected 401 "Unauthorized", got 200 "OK"

Error: expected 503 "Service Unavailable", got 200 "OK"
```

### subject-admin-atomic

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly deep-equal:
+ actual - expected
... Skipped lines

  {
    'subject_admin.tenant_authorization_subject_roles': [
      {
        role_name: 'uploader',
        subject_id: '000000000000000000000001',
-       tenant_id: '11111111-1111-4111-8111-111111111111'
-     },
-     {
-       role_name: 'uploader',
-       subject_id: '000000000000000000000001',
        tenant_id: '22222222-2222-4222-8222-222222222222'
      }
    ],
    'subject_admin.tenant_authorization_subjects': [
      {
        created_at: '2026-01-01T00:00:00.000Z',
+       display_name: 'Rollback',
-       display_name: 'Original',
        notes: 'preserved',
        subject_id: '000000000000000000000001',
        tenant_id: '11111111-1111-4111-8111-111111111111'
      },
      {
...
        tenant_id: '11111111-1111-4111-8111-111111111111',
+       token_prefix: 'rollback'
-       token_prefix: 'original'
      },
      {
        subject_id: '000000000000000000000001',
        tenant_id: '22222222-2222-4222-8222-222222222222',
        token_prefix: 'foreign'

      + expected - actual

         "subject_admin.tenant_authorization_subject_roles": [
           {
             "role_name": "uploader"
             "subject_id": "000000000000000000000001"
      +      "tenant_id": "11111111-1111-4111-8111-111111111111"
      +    }
      +    {
      +      "role_name": "uploader"
      +      "subject_id": "000000000000000000000001"
             "tenant_id": "22222222-2222-4222-8222-222222222222"
           }
         ]
         "subject_admin.tenant_authorization_subjects": [
           {
             "created_at": "2026-01-01T00:00:00.000Z"
      -      "display_name": "Rollback"
      +      "display_name": "Original"
             "notes": "preserved"
             "subject_id": "000000000000000000000001"
             "tenant_id": "11111111-1111-4111-8111-111111111111"
           }
--
         "subject_identity.legacy_credential_subjects": [
           {
             "subject_id": "000000000000000000000001"
             "tenant_id": "11111111-1111-4111-8111-111111111111"
      -      "token_prefix": "rollback"
      +      "token_prefix": "original"
           }
           {
             "subject_id": "000000000000000000000001"
             "tenant_id": "22222222-2222-4222-8222-222222222222"
```

### subject-admin-current

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:

true !== false

      + expected - actual

      -true
      +false
```

### subject-admin-tenant

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly deep-equal:
+ actual - expected

  {
+   created_at: '2026-02-01T00:00:00.000Z',
-   created_at: '2026-01-01T00:00:00.000Z',
    name: 'Renamed Test_user',
+   notes: 'foreign notes',
-   notes: 'preserved',
    roles: [
      'uploader'
    ],
    subjectId: '000000000000000000000001'
  }

      + expected - actual

       {
      -  "created_at": "2026-02-01T00:00:00.000Z"
      +  "created_at": "2026-01-01T00:00:00.000Z"
         "name": "Renamed Test_user"
      -  "notes": "foreign notes"
      +  "notes": "preserved"
         "roles": [
           "uploader"
         ]
         "subjectId": "000000000000000000000001"
```

The repaired authority ablation now removes all four current-authority permission checks in archived scratch. It fails on current-grant refusal (expected401/got200) and unavailable-authority refusal (expected503/got200); its three other cases still pass. Audience removal fails expected401/got200. These are semantic HTTP assertion failures, not setup or mutation failures. The assertions fail before later effects-array checks, so mutated handler effects are not independently quantified by these logs. The unchanged positive/restored suite checks those effects. Subject current-authority bypass returns true instead of false; tenant mutation reads foreign metadata; atomicity mutation persists partial rename/role changes after the injected failure. All three fail assertions, with restored13 afterward.

## Execution, ownership and cleanup

M4 explicitly released its bounded fixtures before this continuation. After fresh host Docker/process checks, B4a claimed 19:45:35Z and released 19:46:46Z. Frozen application and repair worktrees were clean at entry and stop. Runs were serial, `TZ=UTC`, nofile64000, frozen private dependencies, Node22.23.4, PostgreSQL16.15, MongoDB8.0.34 and Vault where required. The repaired gate was invoked from its complete worktree, preserving its helper dependency. Continuation command records are in local logs; controls use `--control authority|audience`, restored omits it. No credentials/database URLs are published.

Host inspection found no remaining campaign fixtures/processes at release. Settings gate diagnostics record its three owned container mounts and audit their absence. Owner-policy owns its PostgreSQL and verifies ownership. Older authority/subject fixtures retain anonymous volumes: Docker volume count454 to462, /home83G available. All unknown resources preserved; no global leak-freedom or SIGKILL cleanup claim. R57 keeps its earlier count388 to454 and ownership limits unchanged.

Profile remains excluded because absent on the frozen head. Full/browser/corpus and B5 joined-head acceptance were not run here. Original sandbox failures and invalid-control captures are retained, not relabelled green. Local lane detail: `externals/work/HANDOFF-codex-b4a-20261106.md`; separate repair ownership: `externals/work/HANDOFF-codex-authority-control-repair-20261106.md`. No application push, default enablement or policy decision.
