# Failed e971 comprehensive diagnostic — 2026-11-07

**FAILED; runtime closed.** The acceptance lead reproduced a terminal exit **2** on application `e9713b6e8e1dd6c0546ab32944b1860d509d5c38`, tree `74b99d9ed43cd7b31e872ee6f195e7a2b63bafd5`. The frozen source stayed clean and unchanged. This projection independently read the retained raw output, execution metadata and closure evidence, and verified both capture indexes. No tests or services were rerun.

The command was `node tools/lab/multitenant-rest-preview/owned.js all`, against an explicitly selected frozen verification checkout with freshly built assets. Runtime versions were Node **v22.23.4**, PostgreSQL **16.15**, MongoDB **8.0.34** and Vault **2.2.1**; shuffle seed **41574423920**. [summary.json](summary.json) contains portable attribution hashes and the full structured disposition.

| Nonbrowser tier | Passing | Pending | Failing |
|---|---:|---:|---:|
| unit | 2769 | 0 | 2 |
| dom | 205 | 0 | 0 |
| dependency | 368 | 2 | 0 |
| core | 319 | 0 | 0 |
| harness | 99 | 0 | 0 |
| integration | 3849 | 172 | 6 |
| stress | 18 | 0 | 0 |
| Sum of raw summaries | 7627 | 174 | 8 |

Exit 2 is the command outcome, not the number of failing tests. Passing tier subtotals do not make this failed campaign accepted. Pending opt-in cases here do not establish all-enabled-corpus acceptance.

## Reproduced failures and source-derived diagnosis

| Failure | Observed symptom | Read-derived mechanism |
|---|---|---|
| Canonical profile wire fixture | Private handler returned 503 rather than 200. | The plain fixture response lacks the event methods needed by the handler's response-completion lifetime. Canonical ObjectId and wire parity remain required. |
| Socket migration prefix fixture | Catalogue length was 4 rather than the expected 2. | The expectation predates the two appended tenant-local conversion/binding migrations. The immutable prefix and original socket DDL still require exact checks. |
| Views equality before-all hook | Server boot refused an invalid/missing API secret. | A prior file can leave a nonempty short value; the fixture's fallback accepts that inherited value instead of isolating its own valid setting. |
| Four identifier-race cells | `TENANT_ORDINAL_BINDING_REQUIRED` before the intended race. | Foreign-row setup lacks the tenant context now required by the insertion trigger. Replace, merge-except-treatments, acknowledge and refuse cells all failed here. |
| Uniqueness-only clock alternative | The second insert timed out while the first remained held. | Tenant-local insertion state adds serialization to this authored alternative-design control. A valid late-commit experiment repair is still unmeasured in this capture; this report adopts no proposed fix. |

The symptoms are reproduced by the failed run. Mechanism attribution above comes from reading its pinned source and output; this capture establishes no repaired-source acceptance.

## Separate source-client refusal

A separate reproduced check on the same source called the actual private IPC client for `/cohort/status` and `/cohort/invalidate`. Both refused with `SOCKET_IPC_REQUEST_REFUSED`, with **0 transport calls**. This is a source-client pre-transport result, not a native cohort run or another full-suite failure.

## Cleanup and remaining boundary

The independent observer and acceptance lead confirmed **22 owned containers**, **32 owned volumes** and **166 observed process births** absent, exact inventory restored and selected baseline metadata unchanged. No observer errors, root readback problems, emergency cleanup or historical-residual allowance remained. Runtime release passed; **phase acceptance remained false**.

This immutable failure remains attributed to e971. Subsequent focused repairs and a new frozen candidate need their own acceptance. Default browser, all enabled multitenant corpus, actual separate-process cohort/controller/logical restore and final prcheck readiness are not established by this capture. It makes no complete-M6, production, default, provider or real-data admission claim. Raw logs, machine paths, random resource/role identities, process IDs, backend timestamps, credentials and connection URLs stay outside this public projection.
