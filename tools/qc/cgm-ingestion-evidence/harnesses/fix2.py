p='/home/bewest/src/rag-nightscout-ecosystem-alignment/docs/40-migration/legacy-cgm-ingestion-to-connect-2026-09-15.md'
s=open(p,encoding='utf-8').read(); orig=s
def rep(old,new):
    global s
    assert s.count(old)==1, ("count=%d for %r" % (s.count(old), old[:90]))
    s=s.replace(old,new,1)

# ---- §1 : add the alarm consequence and the fourth measured fact ----
rep("""There is a second failure mode, and this revision found it: data that arrives **at the wrong time**.
A glucose trace shifted by the operator's UTC offset is worse than no trace, because it looks like
data. It will be read, and it will be read as current.""",
"""There is a second failure mode, and this revision found it: data that arrives **at the wrong time**.
A glucose trace shifted by the operator's UTC offset is worse than no trace, because it looks like
data. It will be read, and it will be read as current.

And it is worse than that. If the shift puts readings **into the future** — which is what happens
for any pump east of UTC, so most of Europe and Asia — Nightscout's built-in "stale data, check
rig?" alarm **stops firing altogether**. Measured: `lib/plugins/timeago.js` returns before
requesting any alarm when the newest stored reading is not in the past (§5.3.5). So the one
mechanism that would otherwise announce an ingestion outage is switched off by the same defect,
and it stays off afterwards. A silent failure and a disabled alarm arrive together.""")

rep("""3. The operator-facing error message that would tell someone how to fix (1) **crashes the page that
   is supposed to display it** (§5.6). Reproduced, with three controls that render correctly.""",
"""3. The operator-facing error message that would tell someone how to fix (1) **crashes the page that
   is supposed to display it** (§5.6). Reproduced, with three controls that render correctly.
4. A forward clock shift **suppresses the stale-data alarm** (§5.3.5). Reproduced, with two
   controls that do fire.

**One measured fact cuts the other way, and it is why §8.4 recommends splitting the cut.** On the
release operators run today, the legacy Dexcom bridge is *already* not running: `BRIDGE_*`
credentials are auto-migrated to Nightscout Connect at boot and the old plugin stands down unless
`DEXCOM_BRIDGE_USE_LEGACY=true` is set (§5.3.4, reproduced with controls). Deleting the Dexcom half
therefore removes a code path that today runs only for operators who asked for it explicitly. The
MiniMed half has no such head start.""")

# ---- §2.2 recoverability table: alarm row ----
rep("""| Your alarms during the outage | **Not recoverable.** Alarms fire on data as it arrives. An alarm that did not fire because no data arrived does not fire later. |""",
"""| Your alarms during the outage | **Not recoverable.** Alarms fire on data as it arrives. An alarm that did not fire because no data arrived does not fire later. |
| Your "stale data" alarm, if your readings are being stored **ahead of** the real time (§5.3) | **It will not fire at all.** Nightscout only raises "stale data, check rig?" when the newest reading is in the *past*. If your readings are being filed hours into the future, Nightscout believes it has just heard from your sensor, so it stays quiet — even after the data really does stop. Measured in `lib/plugins/timeago.js`. **This is why §3.4 asks you to check the clock, not only the graph.** |""")

# ---- §2.3 : the setupBridge log line is not proof ----
rep("""1. Look at your Nightscout server log for lines containing `DEPRECATION WARNING`, `Executing
   setupBridge`, or `Executing setupMMConnect`. If those lines are absent, the old ingestion did not
   start, and your settings were probably changed during the upgrade. Restore the settings you
   recorded.""",
"""1. Look at your Nightscout server log for lines containing `DEPRECATION WARNING`, `Executing
   setupBridge`, or `Executing setupMMConnect`. If those lines are absent, the old ingestion did not
   start, and your settings were probably changed during the upgrade. Restore the settings you
   recorded.
   **Careful — `Executing setupBridge` on its own proves nothing.** That line is printed every time
   Nightscout starts, including when it then decides *not* to run the old Dexcom bridge. The line
   that tells you it actually ran is `DEPRECATION WARNING PLEASE CONSIDER nightscout-connect
   instead.`; the line that tells you it stood down is `DEPRECATION WARNING Skipping legacy
   share2nightscout-bridge because nightscout-connect is handling Dexcom Share.` (Verified on
   `origin/master` and `origin/dev`, `lib/server/bootevent.js:362` and `:369`.)""")
open(p,'w',encoding='utf-8').write(s)
print('ok delta', len(s)-len(orig))
