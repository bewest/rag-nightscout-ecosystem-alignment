p='/home/bewest/src/rag-nightscout-ecosystem-alignment/docs/40-migration/legacy-cgm-ingestion-to-connect-2026-09-15.md'
s=open(p,encoding='utf-8').read(); orig=s
def rep(old,new):
    global s
    assert s.count(old)==1, ("count=%d for %r" % (s.count(old), old[:90]))
    s=s.replace(old,new,1)

rep("Measured: diverges by exactly the pump's UTC offset (§5.3).",
    "Measured: diverges by exactly the pump's UTC offset under the preconditions in §5.3 — **narrowed by row 0.7 below, read both**.")

# §5.3 consequence 2: add the alarm
rep("""2. **The trace is plotted at the wrong time.** For a UTC+2 operator, readings land two hours in the
   future — visible as a gap at "now" plus points past the right edge of the chart. For a UTC−7
   operator they land seven hours in the past, quietly ageing out of the visible window. Either way
   the chart is wrong, and it is wrong in a way that looks like data rather than like an outage.""",
"""2. **The trace is plotted at the wrong time, and — east of UTC — the stale-data alarm stops
   firing.** For a UTC+2 operator, readings land two hours in the future — visible as a gap at "now"
   plus points past the right edge of the chart — **and `timeago.checkNotifications` then refuses to
   raise "Stale data, check rig?" at all, because the newest reading is not in the past** (measured;
   §5.3.5). For a UTC−7 operator readings land seven hours in the past, quietly ageing out of the
   visible window while the urgent alarm fires continuously. Either way the chart is wrong, and it is
   wrong in a way that looks like data rather than like an outage; east of UTC it is also wrong in a
   way that removes the alarm that would have said so.""")

# §5.3.2 add the alarm
rep("""If both paths run at once — which, per §5.3.3, is what a MiniMed operator gets if they follow the
usual "stage the new settings first" advice — the divergence produces a **doubled and time-shifted**
trace, not a seamless handover.""",
"""If both paths run at once — which, per §5.3.3, is what a MiniMed operator gets if they follow the
usual "stage the new settings first" advice — the divergence produces a **doubled and time-shifted**
trace, not a seamless handover. East of UTC, the Connect half of that doubled trace is future-dated,
which per §5.3.5 also suppresses the stale-data alarm for as long as it keeps arriving.""")

# §6.1 arm matrix: add the format dimension
rep("""| `lastConduitDateTime` | absent; present with offset; present as `Z`; present malformed |""",
"""| `lastConduitDateTime` | absent; present with offset; present as `Z`; present malformed |
| Payload timestamp format | `Z`-suffixed ISO; offset-suffixed ISO; **zone-less** (`"Oct 12, 2015 03:12:10"` — the retired package's own recorded format, where the rewrite regex does not match and `Date.parse` falls back to the process's local time) |
| Legacy branch | `MMCONNECT_SERVER=EU`; `MMCONNECT_SERVER` unset; `medicalDeviceFamily=GUARDIAN` — `parsePumpTime` forks on these and the two branches fail differently |
| Process `TZ` | `UTC`; a non-UTC zone — required, because a zone-less payload's parsed instant depends on it |""")

# §6.1 pass criteria: add the alarm assertion
rep("""**Expected initial result.** The MiniMed non-UTC rows **fail today**, by §5.3. That is the arm's
first job: turn the §5.3 measurement into a standing gate.""",
"""**Expected initial result.** The MiniMed non-UTC rows **fail today**, by §5.3. That is the arm's
first job: turn the §5.3 measurement into a standing gate.

**Additional assertion (§5.3.5).** For every row, assert that the newest stored reading is **not
future-dated relative to the harness clock**. A future-dated newest reading is a failure in its own
right, because `timeago.checkNotifications` silently stops raising the stale-data alarm once it
happens. The break-it control for this assertion is to shift one Connect timestamp +2 h and confirm
the arm reports it.""")

# §8.2 stage stop conditions: alarm
rep("""| **1. Maintainer dogfood** | ≥ 2 maintainers, real accounts, non-production instances, both vendors, **at least one account not on UTC** | ≥ 14 days | Zero silent-gap events; zero clock-skew events; every §9 item green | Any silent gap; any clock skew; any vendor auth anomaly; any duplicate growth beyond the legacy baseline |""",
"""| **1. Maintainer dogfood** | ≥ 2 maintainers, real accounts, non-production instances, both vendors, **at least one account not on UTC**, and **at least one east of UTC** (so a forward shift, and therefore the §5.3.5 alarm suppression, would be visible) | ≥ 14 days | Zero silent-gap events; zero clock-skew events; the stale-data alarm demonstrably still fires when ingestion is stopped deliberately; every §9 item green | Any silent gap; any clock skew; **any failure of the stale-data alarm to fire on a deliberately stopped feed**; any vendor auth anomaly; any duplicate growth beyond the legacy baseline |""")
open(p,'w',encoding='utf-8').write(s)
print('ok delta', len(s)-len(orig))
