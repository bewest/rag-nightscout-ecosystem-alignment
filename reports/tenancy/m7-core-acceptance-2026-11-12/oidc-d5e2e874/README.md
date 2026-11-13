# Frozen M7 core: native identity and client matrix

Source `d5e2e874659155c952b5b5deb862f12f982ac02e`, clean before/after. The refreshed
`official/dev` `4a482627bfdafb1fef8dcbe0ac6c484811cae563` was already an ancestor;
merging it reported already up to date. This is a partial comprehensive acceptance
record, not a full paired release or capacity verdict.

The coordinator rebuilt the [production bundle](production-bundle.txt) on this
source in its owned dependency tree. Compilation succeeds with three webpack
performance warnings. Node is v22.23.4, Chrome is 154.0.8037.57; the native harness
checks the exact oref0 companion `d219baf9559d62a8bb0bd42014192a2d7c0839ef`.
[Summary](summary.json) records executed source, image/runtime/tool identities and
all stage cleanup witnesses. [Capture hashes](artifacts.json).

`tests/native/oidc-matrix/run.sh --out <private-output>`: **9 stages PASS, complete**.
The matrix covers the real PG/Mongo/Vault identity/owner/issued-DATA and native
browser/client paths selected by the source harness. No settings, role or authority
guard was relaxed to obtain this result.

Three source-bound semantic controls also pass their red/restored criterion:

| Control | Deliberate break: observed failure | Restored |
|---|---|---|
| Shipping single subject exchange lifetime | Independent eight-hour compatibility oracle fails on the shortened lifetime. | PASS |
| Owner browser CSRF guard | Cookie mutation incorrectly reaches 200; oracle requires 403. | PASS |
| Current DATA authority | Next DATA operation no longer reads current role authority; oracle fails. | PASS |

[Control records](controls.json) retain source hashes, expected symptoms and exact
FAIL/PASS observations. [Matrix](matrix.txt) and [control](controls.txt) transcripts
are path-sanitized copies of the private original captures. Product source was
never mutated; controls use owned archived scratch trees.

The source overlap checks after joining diagnostics and sharding pass
[44 checks](joined-focused.txt); [tier inventory](tiers.txt) is current at 699 files
across eight tiers. These are not substitutes for the full tier/corpus campaign.
The coordinator independently verified [zero remaining containers, volumes and
networks](resources.json) for both native harness projects. Retained prototype and
unrelated services were untouched.

Still open: the comprehensive eight-tier/enabled-corpus run (its first attempt stopped in unit; a repaired candidate must be refrozen),
final shipping binding move/recovery proof, and final prcheck. Clinical trace
comparison has its [own record](../../m7-clinical-equivalence-2026-11-12/README.md)
with its memory-projection/database coverage limits. Capacity and performance
claims require the subsequent accepted profile measurements.
