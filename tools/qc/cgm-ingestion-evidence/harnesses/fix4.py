p='/home/bewest/src/rag-nightscout-ecosystem-alignment/docs/40-migration/legacy-cgm-ingestion-to-connect-2026-09-15.md'
s=open(p,encoding='utf-8').read(); orig=s
def rep(old,new):
    global s
    assert s.count(old)==1, ("count=%d for %r" % (s.count(old), old[:90]))
    s=s.replace(old,new,1)

# ---- §3.3 Dexcom safety net ----
rep("""**If you use the Dexcom bridge — you may safely add the new settings before you upgrade.** Add
these alongside your existing `BRIDGE_*` settings; do not delete the old ones yet, they are your
safety net.""",
"""**If you use the Dexcom bridge — you may safely add the new settings before you upgrade.** Add
these alongside your existing `BRIDGE_*` settings, and do not delete the old ones yet.

**Correction, added in review: on 15.0.8 and the 15.0.9 candidate your `BRIDGE_*` settings are not
a safety net.** They are already being handed to Nightscout Connect at startup, and the old bridge
stands down (§5.3.4, measured). The only thing that puts you back on the old Dexcom bridge on those
releases is setting `DEXCOM_BRIDGE_USE_LEGACY=true` — and even that stops working on the release
that retires the code (§2.1). **Your real safety net is the recorded previous version you can
redeploy (§3.2 step 1).**""")

# ---- §3.3 misquoted log string ----
rep("""On the current release this setting is inert on its own — Nightscout Connect only starts when
`CONNECT_SOURCE` is set (verified: `nightscout-connect/index.js` returns early with *"Skipping
disabled connector, no source driver"*). Setting it now means it is already correct at the moment
you upgrade, which is the moment it becomes mandatory.""",
"""On the current release this setting is inert on its own — Nightscout Connect only starts when
`CONNECT_SOURCE` is set (verified by execution: `nightscout-connect/index.js:30` returns early and
logs `Skipping disabled nightscout-connect, no source driver spec`). Setting it now means it is
already correct at the moment you upgrade, which is the moment it becomes mandatory.""")

# ---- §3.4 add the alarm and clock checks ----
rep("""**MiniMed only:** also check that the pump pill (battery, reservoir, insulin on board) still shows
sensible values.""",
"""5. **Your stale-data alarm still works.** This is the check people skip, and it is the one that
   protects you overnight. Nightscout's built-in *"stale data, check rig?"* alarm (settings
   `ALARM_TIMEAGO_WARN`, default on at 15 minutes, and `ALARM_TIMEAGO_URGENT`, default on at 30
   minutes) only fires when the newest reading is in the **past**. If §5.3 has filed your readings
   into the **future**, Nightscout thinks it just heard from your sensor and the alarm will never
   fire again — including later, when your data genuinely stops (measured; §5.3.5). So: confirm
   both settings are on, and confirm the newest reading's time is not ahead of now.
   A quick way to see it: the "minutes ago" pill should count *up*. If it reads `future`, or sits at
   `1m` and never moves, **stop and roll back (§2.1)**.

**MiniMed only:** also check that the pump pill (battery, reservoir, insulin on board) still shows
sensible values.

*None of the above is medical advice. If you are unsure whether it is safe to continue while your
data is uncertain, fall back to your CGM's own app and to fingersticks as your care team has
advised, and contact your care team.*""")

rep("""Upgrade. Then, within the first 15 minutes, check **all four** of these. One is not enough.""",
"""Upgrade. Then, within the first 15 minutes, check **all five** of these. One is not enough.""")
open(p,'w',encoding='utf-8').write(s)
print('ok delta', len(s)-len(orig))
