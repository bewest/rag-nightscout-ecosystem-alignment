# Lifecycle wire transition — 2026-11-13

**Fixed on a branch; bounded source review approved.** Core
`b06106eb8748e975cbe651f6ab51a2b664bd34a1` versions the complete lifecycle identity
and scoped operation-census contract as wire version 3. [Selected evidence and
provenance](summary.json) retains the original failure and the repair controls.

The joined restore changes require ten catalogue identity fields. An earlier eight-field identity
response accepted by the old schema is refused by the new schema, although
both had still advertised wire version 2. The old schema did not enumerate an
exact eight-field identity; the new schema explicitly requires ten fields. The source's documented protocol rule
requires an explicit version change for this breaking response change.

Root reproduced that mismatch. After repair, actual temporary Unix-socket and
loopback-HTTP controls refuse earlier wire requests before handler dispatch and
accept the current named client. Restoring the old wire version makes both
controls fail: a request dispatches successfully instead of being refused.
Restored source passes, and 73 affected checks pass. An independent immutable
archive review also confirms the schema transition and transport controls.
These local checks used Node 22.23.4/npm 10.9.9. The earlier core7d campaign
preparation is retained NOT_RUN. A fresh full source campaign is being prepared
for the repaired source with its own pinned toolchain; its result is unmeasured.

Upgrade the operator and all cohort participants together before maintenance,
then acquire fresh pins. Operation-configuration and placement payload versions
remain unchanged. There is no fallback to an older lifecycle wire contract.

The source change touches only the service contract, its focused checks and
protocol documentation. Catalogue qualification remains at its [separate
record](../restore-catalogue-source-2026-11-13/README.md). Full joined source,
selected operator, clinical/native and capacity acceptance remain UNMEASURED.
The earlier core campaign remains attributed to its exact earlier source.
No resources, raw captures or credentials are part of this record; nothing was
pushed, merged to application dev or released.
