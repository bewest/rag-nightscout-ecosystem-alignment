# Headless owner native request fixture — 2026-11-06

Reproduced; [measurement and private artifact hashes](owner-preview-wire-native-2026-11-06.json).

| Executed source | Outcome | Interpretation |
|---|---|---|
| `f07804b33c057c693335eb353757df60691b22fa` | Combined owner/evaluator invocation 9 passing, 0 pending, 7 failing. | Evaluator7 and owner startup/lifecycle2 passed. Owner request cases reached tenant refusal before intended checks; no combined-listener canary or SQL-refusal acceptance. |
| `4cd95d069675b650e1173779057a7927f4873702` | Affected owner invocation 9 passing, 0 pending, 0 failing. | Only the owner request fixture changed: explicit Host is preserved through node:http. Product, resolver, policy, schema, defaults and all other tests are identical to f078. |

An owned loopback wire diagnostic reproduced Node fetch replacing the synthetic tenant Host with its connection host. The fixture correction introduces no resolver or authorization bypass. The affected followup executes actual PostgreSQL/Vault, same-process separate OWNER/DATA listeners, DATA management refusal405, OWNER update200/audit+1, and a real201 DATA canary. Two workers refuse exact-owned reader SELECT privilege loss with sanitized503 and no owner mutation; restored privilege permits the next update200/audit+1. This is SQL permission refusal, not network-outage certification.

Both invocations independently removed their three owned containers, four mounted volumes and eight observed Node identities; baseline462 volumes preserved, observer errors0. The initial evaluator producer's transient PID was missed by the external observer; its native kill/exit assertion remains the narrower evidence. Raw failures, diagnostic and followup are immutable private captures indexed by hash. Evaluator7 executes on f078 only. Separate owner semantic controls and whole-candidate acceptance have their own records. No human issuer/refresh, production trust or M2 promotion is established.
