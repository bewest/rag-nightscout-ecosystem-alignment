p='/home/bewest/src/rag-nightscout-ecosystem-alignment/docs/40-migration/legacy-cgm-ingestion-to-connect-2026-09-15.md'
s=open(p,encoding='utf-8').read(); orig=s
def rep(old,new):
    global s
    assert s.count(old)==1, ("count=%d for %r" % (s.count(old), old[:90]))
    s=s.replace(old,new,1)

rep("""**Legacy** (`minimed-connect-to-nightscout/transform.js:57-85`) *guesses* the pump's UTC offset:
`sMedicalDeviceTime` is CareLink's pump clock expressed as though it were UTC, and the difference
from `currentServerTime`, rounded to whole hours, is taken as the offset. The code comments say so
explicitly. `parsePumpTime()` then subtracts it.

**Connect** (`nightscout-connect/lib/sources/minimedcarelink/index.js:691-715`) instead reads the zone
designator off `data.lastConduitDateTime` and rewrites each timestamp's zone suffix to match. If
`lastConduitDateTime` is **absent**, `reassign_zone()` returns the identity function `id` and the
pump's wall-clock string is taken **literally as UTC**.""",
"""**Legacy** (`minimed-connect-to-nightscout/transform.js:57-85`) *guesses* the pump's UTC offset:
`sMedicalDeviceTime` is CareLink's pump clock expressed as though it were UTC, and the difference
from `currentServerTime`, rounded to whole hours, is taken as the offset. The code comments say so
explicitly. `parsePumpTime()` then applies it.

**Two legacy branches, and only one of them was measured — stated here because the review found it
omitted.** `parsePumpTime()` (`transform.js:40-46`) forks: when `MMCONNECT_SERVER === 'EU'` **or**
`medicalDeviceFamily === 'GUARDIAN'` it *subtracts* the guessed offset in milliseconds; otherwise it
appends the offset string and re-parses. The measured table below exercises the **EU/GUARDIAN
branch**, which is the branch cut 4's own fixture declares (`"region": "EU"`). On the other branch,
fed the same ISO `Z`-suffixed payload, `Date.parse('…T14:00:00.000Z +0200')` is `NaN` and the legacy
transform **throws `RangeError: Invalid time value`** instead of producing a timestamp — so the
table's `legacy dateString` column is not reproducible there. Re-measured by execution.

**Connect** (`nightscout-connect/lib/sources/minimedcarelink/index.js:709-717` at cut 4's pin
`c962a13f`; the same code is at `:691-699` in the v0.0.14 working tree) instead reads the zone
designator off `data.lastConduitDateTime` and rewrites each timestamp's zone suffix to match. If
`lastConduitDateTime` is **absent**, `reassign_zone()` returns the identity function `id` and the
pump's wall-clock string is passed straight to `Date.parse`.

**What `Date.parse` then does depends on the string, and the document previously got this wrong.**
If the wall-clock string carries a `Z` (as cut 4's fixture and Connect's own test payloads do), it
is taken literally as UTC. If it is **zone-less** — which is the format in the retired package's own
recorded CareLink payloads, e.g. `"Oct 17, 2015 09:09:14"` — `Date.parse` resolves it against the
**Nightscout process's local timezone**. So the divergence is (pump offset − server `TZ` offset),
not the pump offset alone. Measured: with zone-less input under `TZ=Europe/Berlin`, the Berlin arm
**agrees** (Δ 0) and the **UTC control diverges by −2 h**. Under `TZ=UTC` — which is what a stock
Docker or Heroku deployment runs — the two forms behave the same and the table below holds.""")

# --- the measured table caption: state the preconditions ---
rep("""`pump.clock` inside `devicestatus` diverges identically. Two controls agree and three arms diverge by
exactly the pump's UTC offset, so the harness distinguishes the branches — this is not a harness
artefact.""",
"""**Preconditions of that table, added in review:** `MMCONNECT_SERVER=EU` (the legacy EU/GUARDIAN
branch — see above), `TZ=UTC`, and `Z`-suffixed wall-clock strings. All three were re-established
and the table reproduced exactly, arm for arm and control for control.

`pump.clock` inside `devicestatus` diverges identically. Two controls agree and three arms diverge by
exactly the pump's UTC offset **under those preconditions**, so the harness distinguishes the
branches — this is not a harness artefact.""")

# --- the "could not settle" paragraph ---
rep("""**What I could not settle.** Whether real CareLink responses carry `lastConduitDateTime`. If they
always do, and always with a real zone offset, the divergence never fires in production and this is a
latent trap rather than an active defect.""",
"""**What I could not settle.** Whether real CareLink responses carry `lastConduitDateTime`.

**Correction, added in review: presence of `lastConduitDateTime` is not sufficient.**
`adjust_conduit_timezone` only rewrites a field whose value **already ends** in
`[+-]HH:MM` or `Z` — the regex is `/([+-]\\d{2}:\\d{2}|Z)$/g` and it is tested against the *item's*
field, not against `lastConduitDateTime`. Measured: with `lastConduitDateTime: 2026-09-01T14:00:00.000+02:00`
present **and** a zone-less `datetime`, Connect still emits `…T14:00:00.000Z` against legacy's
`…T12:00:00.000Z` — **+2 h, unmitigated**. So the escape hatch requires *two* facts about real
payloads, not one: that `lastConduitDateTime` is present with a real offset, **and** that
`sgs[].datetime` (and `markers[].dateTime`, and `sMedicalDeviceTime` for `pump.clock`) carry a zone
designator of their own. If only the first holds, the divergence fires anyway.

If both hold, the divergence never fires in production and this is a
latent trap rather than an active defect.""")
open(p,'w',encoding='utf-8').write(s)
print('ok delta', len(s)-len(orig))
