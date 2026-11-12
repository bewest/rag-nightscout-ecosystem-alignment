# Admin secrets permissions fixture — 2026-11-12

**Reproduced fixture defect; fixed on branch.** The original refusal fixture asked
for creation mode 0644 but inherited runner umask 077, producing a private 0600 file.
The actual CLI correctly accepted it. The fixture now explicitly chmods 0644 and
asserts the effective mode before testing refusal. The runtime guard is unchanged.

Core commit `9db0ce94f072c8f34aab889f0181afa4269a6758` contains exactly three added
fixture lines in `tests/admin-provisioning.integration.test.js`.
[Attribution](captures/attribution.json) explicitly distinguishes execution from
incorporation: original execution used archived 761 source; repaired execution used
that same archived runtime plus the exact fixture patch. The repaired bytes are
now in 9db, but this is not a claimed clean 9db test execution. Raw process records'
`source` field names that base commit, not an unpatched repaired run.

## Actual native evidence

Both focused runs used the shipping CLI and admin REST role on uniquely owned,
disposable PostgreSQL and Vault, with the requested exact-lock dependencies.
[Identity](captures/identity.json) records actual image IDs, Node 22.23.4 and package
lock SHA. No source15 project, image or comprehensive campaign was operated on.

| Execution under umask 077 | Direct Mocha return code | Actual CLI/mode observation |
|---|---:|---|
| Original refusal case | 1 (0pass/0pending/1fail) | Requested 0644 created 0600; CLI accepted with 0; fixture expected 64. |
| Repaired refusal plus existing JSON-seed case | 0 (2pass/0pending/0fail) | Explicit chmod 0644; CLI refused 64. Existing 0600 secret output accepted 0, including retry. |

The actual numeric modes are384=0600 and420=0644 in the original
[events](captures/original077-events.jsonl) and repaired
[events](captures/repaired077-events.jsonl). Direct subprocess returns are retained
in the corresponding [original](captures/original077-process.json) and
[repaired](captures/repaired077-process.json) process records. Logs retain the
original failing assertion and repaired results, without secret values.

The bounded [observer](captures/observe.cjs) records parent fixture write/chmod
modes and CLI child exit events. It changes neither arguments nor return values;
CLI children use their existing explicit environment and are not preloaded with
the observer. Actual `lib/cli/commands/admin.js` bytes match before/after, SHA256
`adb7da9437e67f460e41987fa095afc52e0dc4c4f0f8e7af67d6edb8e25ccbb4`.
This is a real 600-accept/644-reject discriminator, not a mocked guard or assertion
inferred from a success marker. [fixture.patch](captures/fixture.patch) and the
original/patched/observer hashes bind the change.

## Cleanup and scope

[Cleanup](captures/cleanup.json) directly observed zero remaining fixture schemas
and roles, then verified nonce labels/full IDs/images and removed only the two
owned disposable containers; both removals returned 0 and absence was verified.
A first read-only cleanup observer did not terminate and was interrupted before
any removal; [its interruption](captures/cleanup-first-interruption.json) remains
recorded. Corrected bounded cleanup passed. No native testcase was replayed for
that instrumentation issue, and no retained qualification data was removed.

This closes the fixture-mode problem only. It adds no runtime security change,
capacity, browser or broad acceptance claim. No private environment, credentials,
Vault token or raw fixture database state is published. All tenants and hosts were
synthetic. [sha256.json](sha256.json) pins the sanitized captures. The coordinator
owns deployment pinning, the next exact image and comprehensive acceptance.
