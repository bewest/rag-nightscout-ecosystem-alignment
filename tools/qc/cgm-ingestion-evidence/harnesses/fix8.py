p='/home/bewest/src/rag-nightscout-ecosystem-alignment/docs/40-migration/legacy-cgm-ingestion-to-connect-2026-09-15.md'
s=open(p,encoding='utf-8').read(); orig=s
def rep(old,new):
    global s
    assert s.count(old)==1, ("count=%d for %r" % (s.count(old), old[:90]))
    s=s.replace(old,new,1)

# ---- §8.1 monitoring table: alarm row + self-hoster signal ----
rep("""| Connect ingesting at the **wrong time** (§5.3) | **200, site fully normal, graph full of data** | **No** — and an arrival-rate check also passes |

The third row is the newest and the nastiest, and it is why the skew signal is listed above.""",
"""| Connect ingesting at the **wrong time** (§5.3) | **200, site fully normal, graph full of data** | **No** — and an arrival-rate check also passes |
| Connect ingesting at the wrong time **and then stopping**, pump east of UTC | **200, site fully normal** | **No** — and the deployment's **own stale-data alarm is suppressed** (§5.3.5), so the operator is not told either |

The third row is the newest and the nastiest, and it is why the skew signal is listed above. The
fourth row is worse still and is why clock skew is a **stop** signal rather than a warning: a
forward-shifted trace removes the last local detector an operator has.

**What a self-hoster can actually do — this document owed them a signal too.** The rolling-rate and
skew checks above are fleet-level and presuppose someone with visibility across deployments. A
single operator running Nightscout for themselves or a family member has exactly one built-in
continuous detector, and it is `timeago`:

- `ALARM_TIMEAGO_WARN` (default **on**, 15 minutes) and `ALARM_TIMEAGO_URGENT` (default **on**, 30
  minutes) fire *"Stale data, check rig?"* when readings stop arriving.
- They are the reason a silent ingestion failure is normally *not* silent for a self-hoster.
- **§5.3 turns them off for any pump east of UTC** (§5.3.5, measured). Until §5.3 is settled and
  fixed, a MiniMed operator on Connect has no local detector at all.

So for single-tenant deployments — which are and remain first-class — the migration's real
observability requirement is: confirm both alarm settings are on, and confirm the newest reading's
time is not in the future. That pair is in the runbook at §3.4 step 5.""")

# ---- §9.1 blocking items ----
rep("""- [ ] Guidance published for operators already on `CONNECT_SOURCE=minimedcarelink` on 15.0.8/15.0.9,
      including how to recognise a time-shifted trace and what (if anything) to do about stored rows.""",
"""- [ ] Determined **also** whether `sgs[].datetime`, `markers[].dateTime` and `sMedicalDeviceTime`
      carry a zone designator in real responses. `lastConduitDateTime` alone does **not** mitigate
      the divergence: `adjust_conduit_timezone` only rewrites a field that already ends in
      `[+-]HH:MM` or `Z` (measured — §5.3, correction 0.8). Both facts are needed before the
      "latent trap" reading can be accepted.
- [ ] A non-UTC case exists for the **other** legacy branch too. `parsePumpTime` forks on
      `MMCONNECT_SERVER === 'EU' || medicalDeviceFamily === 'GUARDIAN'`; the measured table covers
      only the EU/GUARDIAN branch, and on the other branch the legacy transform throws on
      `Z`-suffixed input (§5.3).
- [ ] **The stale-data alarm is confirmed to still fire after the cutover** (§5.3.5). Under a
      forward clock shift `timeago.checkNotifications` returns before requesting any alarm, so a
      MiniMed operator east of UTC loses their only local silent-failure detector. A regression test
      must assert that a deployment whose newest reading is future-dated is **flagged**, not
      silently accepted.
      `git show <ref>:lib/plugins/timeago.js | grep -n "mills >= sbx.time"` → today: present, no guard
- [ ] Guidance published for operators already on `CONNECT_SOURCE=minimedcarelink` on 15.0.8/15.0.9,
      including how to recognise a time-shifted trace, that their stale-data alarm may not have been
      firing, and what (if anything) to do about stored rows.""")

# ---- §10 Q1 ----
rep("""1. **Does a real CareLink payload contain `lastConduitDateTime`, with a real zone offset?** This is now
   the single highest-value unknown in the cut: it decides whether §5.3 is an active defect or a latent
   trap. **A maintainer with a real CareLink account**, in at least two countries, at least one not on
   UTC. Cannot be settled from fixtures, because the fixtures are the thing in doubt.""",
"""1. **Does a real CareLink payload contain `lastConduitDateTime` with a real zone offset, *and* do
   `sgs[].datetime` / `markers[].dateTime` / `sMedicalDeviceTime` carry zone designators of their
   own?** Both halves are needed, and the review established that the second half was missing from
   this question: the zone rewrite only touches a field that already ends in `[+-]HH:MM` or `Z`
   (measured — §5.3). Together they decide whether §5.3 is an active defect or a latent trap. **A
   maintainer with a real CareLink account**, in at least two countries, at least one not on UTC.
   Cannot be settled from fixtures, because the fixtures are the thing in doubt. Note also that the
   retired package's own recorded payloads use a **zone-less** format (`"Oct 12, 2015 03:12:10"`),
   which is the case where the divergence additionally depends on the server's `TZ`.""")

# ---- §11 reviewer checklist ----
rep("""- **R14.** Whether the 90-day window (§7.2) and the stage durations (§8.2) are right for this community.""",
"""- **R14.** Whether the 90-day window (§7.2) and the stage durations (§8.2) are right for this community.
- **R15. Added in review, and it changes §3.** §5.3.4: that `migrateBridgeToConnect()` runs
  unconditionally in `setupConnect` on **`origin/master`** as well as `origin/dev`, and that
  `BRIDGE_*` alone therefore already puts an operator on Nightscout Connect with the legacy bridge
  stood down. Re-run the three-row table including its control. If this is wrong, §3.1 and §3.3
  revert to the previous revision's wording and the Dexcom risk assessment gets larger again.
- **R16. Added in review, and it is the safety one.** §5.3.5: that `timeago.checkNotifications`
  returns before requesting an alarm when the newest reading is not in the past, and that
  `alarmTimeagoWarn`/`alarmTimeagoUrgent` are on by default. Confirm both controls fire before
  trusting the arms. If this is right, §5.3 is a safety defect and not only a data-quality one, and
  §9.1's new blocking item stands.
- **R17.** The three preconditions of §5.3's measured table — `MMCONNECT_SERVER=EU`, `TZ=UTC`, and
  `Z`-suffixed wall-clock strings. Vary each one separately; the divergence is not a clean function
  of the pump offset once the input format changes.""")
open(p,'w',encoding='utf-8').write(s)
print('ok delta', len(s)-len(orig))
