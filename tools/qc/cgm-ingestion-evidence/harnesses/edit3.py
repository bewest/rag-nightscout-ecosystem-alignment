import io,sys
p='docs/30-design/phase0-pr-sequencing-2026-09-15.md'
s=io.open(p,encoding='utf-8').read()
def rep(old,new):
    global s
    if s.count(old)!=1:
        sys.exit("NOT UNIQUE (%d): %r" % (s.count(old), old[:70]))
    s=s.replace(old,new)

# E2 bullet: restore the hazard that decides whether an alarm fires, and BF-45.
rep("""  that takes the whole site down (BF-61). One total break in legacy *is* proved: CareLink
  care-partner (follower) accounts cannot work through Nightscout at all, because
  `lib/plugins/mmconnect.js` `getOptions` never plumbs `patientId`.""",
"""  that takes the whole site down (BF-61). One total break in legacy *is* proved: CareLink
  care-partner (follower) accounts cannot work through Nightscout at all, because
  `lib/plugins/mmconnect.js` `getOptions` never plumbs `patientId`.
  **And the item E2 ranks above every other finding it made was missing from this section until the
  2026-09-16 review put it back.** Reproduced end to end through both shipping transforms and the
  shipping `lib/plugins/timeago.js`: with a payload whose timestamps carry **no zone designator** —
  the shape the retired package's own recorded fixtures use — and a pump **east of the server
  clock**, *legacy* files the reading at the true instant and raises the urgent stale-data alarm,
  while **Connect files it in the future** (a UTC+2 pump, a genuinely dead 40-minute feed, and the
  reading lands at age −80 minutes), `checkStatus` returns `current`, the browser alarm is false and
  **zero push alarms are sent**. That is BF-44 chaining into BF-41. Controls: at UTC+0 all three
  agree; at UTC−7 Connect alarms but is 7 h 40 m wrong; a zone-**bearing** payload inverts the roles.
  **So the retirement improves this hazard for some users and causes it for others**, and which is
  decided by a vendor payload property nobody in this programme has observed on a real account.
  A second detector goes quiet with it: `lib/plugins/pump.js` does `moment(pump.clock)`, which for an
  unparseable value makes `urgent.isAfter(...)` false, so the pump-stale warning cannot fire either.
  **Also: do not advise staging `CONNECT_*` settings alongside `MMCONNECT_*`.** BF-45, reproduced:
  `lib/plugins/mmconnect.js` `init` returns a live runner whether or not
  `connect.source === 'minimedcarelink'`, so both ingestion paths poll at once — and because the two
  paths compute different `sysTime` values the upsert does **not** absorb the duplicates. That
  advice is safe for Dexcom and unsafe for MiniMed.""")

# The "above all others" ranking and the over-generalised upsert claim.
rep("""**The one thing to carry into the deprecation notice above all others**, because its failure mode is
a person's glucose data quietly stopping: **"nothing is lost" is true of stored glucose history and
false of settings.** Entry records are field-for-field identical and the `{sysTime, type}` upsert
cannot duplicate readings — but five `BRIDGE_*` and five `MMCONNECT_*` controls are silently
dropped, the `device` label changes (`share2` → `nightscout-connect`, `connect-paradigm` →
`nightscout-connect://minimedcarelink/PARADIGM`) which splits chart history, and several
configurations legacy tolerated stop working — notably `BRIDGE_SERVER=US`, which becomes the
unresolvable host `https://US` while `validate()` returns `ok: true`.""",
"""**Two things to carry into the deprecation notice, in this order. The ranking was wrong here until
the 2026-09-16 review and the correction matters, because the two items have different failure
modes.**

**First, the timestamp hazard above**, because E2 states plainly that *of everything it studied,
only that section has a failure mode where a person's glucose data stops and the software does not
say so.* It is the item that should decide whether the retirement ships behind a fix or behind a
notice. This document previously gave that ranking to the settings item below, which is not what the
evidence says.

**Second, "nothing is lost" is true of stored glucose history and false of settings.** Five
`BRIDGE_*` and five `MMCONNECT_*` controls are silently dropped, the `device` label changes
(`share2` → `nightscout-connect`, `connect-paradigm` →
`nightscout-connect://minimedcarelink/PARADIGM`) which splits chart history, and several
configurations legacy tolerated stop working — notably `BRIDGE_SERVER=US`, which becomes the
unresolvable host `https://US` while `validate()` returns `ok: true`. That last one *is* a silent
stop, and it is why the `BRIDGE_SERVER` census below sets the length of the notice.

> **The "no duplicate readings" half is Dexcom-only and was stated too broadly here.** For **Dexcom**,
> E1 reproduced that entry records are field-for-field and value-for-value identical except `device`,
> and that `entries.create()` upserts on `{sysTime, type}` — which does not include `device` — so the
> cutover cannot duplicate history. For **MiniMed** that does not follow: E2 reproduced that legacy
> and Connect compute **different `sysTime` values** for the same reading whenever the payload
> carries no zone designator, so if both paths run (BF-45) the upsert absorbs nothing and the site
> gets two traces offset by the pump's UTC offset. Do not carry the Dexcom sentence into a MiniMed
> notice.

**What has NOT been retired, and belongs in the notice as the case *for* the change.** The
adversarial review found this section listing only corrections, which reads as a case against a
decision the evidence partly supports. E1 and E2 also **confirm**, by reproduction: legacy Dexcom
dies with an uncaught `TypeError: glucose.map is not a function` on a non-array body with HTTP <400,
and cgm-remote-monitor registers **no** `uncaughtException` handler, so that kills the Nightscout
process, where Connect's `Array.isArray` guard continues; legacy authenticates ~550 times a day
against Connect's ~1; legacy sets `rejectUnauthorized: false` on all four request types; legacy
prints every CGM reading to the server log on every poll; legacy has no backoff term anywhere and
its session-rejection path is an unbounded delay-free loop; and `BRIDGE_MAX_FAILURES`, documented as
"how many failures before giving up", is **unreachable at its default**. On MiniMed, legacy's entire
US login branch is dead code (`if (1 || CARELINK_EU)`), `MMCONNECT_MAX_RETRY_DURATION` does nothing
(`let maxRetry = 1; // No retry`), and follower accounts cannot work at all. **Those are a sufficient
case for retirement on their own and do not depend on the unproven claim that legacy MiniMed "does
not work".**""")

# Audience note: add "how to notice".
rep("""> advice, and state that it is not medical advice and that changes to how glucose data reaches
> Nightscout are worth mentioning to a care team. **The migration plan and both research documents
> are drafts requiring review by the maintainer before anything is published.**""",
"""> advice, and state that it is not medical advice and that changes to how glucose data reaches
> Nightscout are worth mentioning to a care team. **The migration plan and both research documents
> are drafts requiring review by the maintainer before anything is published.**
>
> **And it must tell people how to NOTICE a problem, not only how to fix one.** Every silent-stop
> mechanism measured here looks, from the outside, like a site that is working. The notice should
> tell an operator, in plain words, what to check in the first hours after switching over: that new
> glucose readings are still appearing on the graph and that the "time since last reading" indicator
> is counting in minutes rather than sitting still or showing a time that has not happened yet; that
> the reading shown matches the one on the phone or receiver; that the source label on the chart has
> changed from the old name to the new one, which is expected and is why older readings may look like
> a separate trace; and that alarms they rely on still arrive — a deliberate test of the
> missing-readings alarm is worth doing, because the hazard above is one where **no alarm is the
> symptom**. It should say where to look when something is wrong (the site's status page and the
> server log) and that a feed that stops is a reason to fall back to the receiver or phone app and to
> contact the community for help. **It is not medical advice, and anyone unsure should talk to their
> care team before changing how they get their glucose data.**""")
io.open(p,'w',encoding='utf-8').write(s)
print("ok")
