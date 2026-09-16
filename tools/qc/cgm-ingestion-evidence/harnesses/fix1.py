p='/home/bewest/src/rag-nightscout-ecosystem-alignment/docs/40-migration/legacy-cgm-ingestion-to-connect-2026-09-15.md'
s=open(p,encoding='utf-8').read(); orig=s
def rep(old,new):
    global s
    assert s.count(old)==1, ("count=%d for %r" % (s.count(old), old[:80]))
    s=s.replace(old,new,1)

rep("marked *(inference)* were reasoned from code I read but did not execute.\n",
"""marked *(inference)* were reasoned from code I read but did not execute.

> **Line-number provenance, corrected by the adversarial review.** Behaviour claims about
> nightscout-connect were re-executed against `c962a13f` and hold there, but several *line
> citations* below were taken from the `externals/nightscout-connect` working tree, which is at
> `649a7de` (the prepared v0.0.14), not at `c962a13f`. Where the two differ this document now
> gives both. The code is equivalent in every case checked; only the line numbers move.
""")

rep("""| 0.6 | — | The `sysTime + type` entries upsert already ships on `origin/master` (15.0.8), not only in the modernization stack (§5.2). | The Dexcom cutover's safety mechanism is present in the code operators run **today**, which makes the Dexcom half stronger than the branch's own evidence claims. |

---""",
r"""| 0.6 | — | The `sysTime + type` entries upsert already ships on `origin/master` (15.0.8), not only in the modernization stack (§5.2). | The Dexcom cutover's safety mechanism is present in the code operators run **today**, which makes the Dexcom half stronger than the branch's own evidence claims. |

### 0b. Added by the adversarial review of this revision (2026-09-15)

An independent agent re-ran §5.1, §5.2, §5.3, §5.4, §5.5 and §5.6 from source and **reproduced every
one of them**, including all of their controls. What follows narrows two of those findings and adds
two the document did not have. Rows 0.9 and 0.10 change operator-facing text.

| # | This revision said | Re-measurement says | Consequence |
| --- | --- | --- | --- |
| 0.7 | "they diverge by **exactly the pump's UTC offset**"; and, when `lastConduitDateTime` is absent, Connect "treats the pump's wall clock **literally as UTC**". | True **only when the payload's timestamp strings carry a zone designator** (`Z` or `±HH:MM`). The retired package's own recorded payloads use a zone-**less** format (`"Oct 17, 2015 09:09:14"`). On those, Connect's `Date.parse` resolves against the **Nightscout process's local timezone**, so the divergence is (pump offset − server `TZ` offset). Measured: under `TZ=Europe/Berlin` the Berlin arm **agrees** and the **UTC control diverges by −2 h** (§5.3). | The defect is real and reproduces, but it is not a clean function of the pump's offset alone. Anyone re-testing it must control the payload's timestamp format **and** the container's `TZ`. |
| 0.8 | "If [`lastConduitDateTime`] is always present, and always with a real zone offset, the divergence never fires in production." | **Refuted.** `adjust_conduit_timezone` only rewrites a field that **already ends** in `([+-]\d{2}:\d{2}` or `Z)`. Measured: `lastConduitDateTime: …+02:00` present **and** a zone-less `datetime` → still **+2 h** divergence. | §10 Q1 and §9.1 were under-specified. Presence of `lastConduitDateTime` is **necessary but not sufficient**; the second condition is that `sgs[].datetime` itself carries a zone designator. Both must be settled together, or the "latent trap" reading is unsafe. |
| 0.9 | *(absent)* | **On `origin/master` (15.0.8) and `origin/dev`, the legacy Dexcom bridge already does not run.** `setupConnect` calls `migrateBridgeToConnect()` unconditionally; the shim sets `connect.source='dexcomshare'` from `BRIDGE_USER_NAME`/`BRIDGE_PASSWORD`, and `setupBridge` then stands down. Measured with controls (§5.3.4). | §3.1's "you are affected if `BRIDGE_*` is set" was wrong, and contradicted this document's own device-name table. §3.3's "keep the old settings, they are your safety net" was wrong: on 15.0.8/15.0.9 the only Dexcom safety net is `DEXCOM_BRIDGE_USE_LEGACY=true`. Both are rewritten. |
| 0.10 | §5.3 consequence 2 described the wrong-time trace as a charting problem. | **It also switches off the stale-data alarm.** `lib/plugins/timeago.js` `checkNotifications` returns before requesting any alarm when the newest reading is not in the past. For any pump **ahead** of UTC — which is most of Europe and Asia — a forward-shifted trace means the alarm that announces an ingestion outage **never fires**. Measured with two controls (§5.3.5). | This is the most serious consequence in the cut and it was missing. It is now in §1, §2.2, §3.4, §5.3.5, §8.1, and is a blocking checklist item (§9.1). |
| 0.11 | §7.1 D6: the "retired in Nightscout 15.0.9" strings are "four occurrences". | Neither reading is four. `git grep -n "retired in" origin/chore/mime-exposure-review -- lib/` returns **5** lines; the exact string `retired in Nightscout 15.0.9` occurs **3** times (bridge shim ×1, mmconnect shim ×2), and `bootevent.js:55` and `:339` add two more saying `retired in 15.0.9`. | D6's command and count are corrected in place. The item itself stands. |
| 0.12 | §3.3 and §5.3.3 quote Connect's early-return log as *"Skipping disabled connector, no source driver"*. | The actual string is **`Skipping disabled nightscout-connect, no source driver spec`** (`nightscout-connect/index.js:30`). An operator told to search their log for the wrong sentence finds nothing and concludes the wrong thing. | Corrected in both places. |

---""")
open(p,'w',encoding='utf-8').write(s)
print('ok delta', len(s)-len(orig))
