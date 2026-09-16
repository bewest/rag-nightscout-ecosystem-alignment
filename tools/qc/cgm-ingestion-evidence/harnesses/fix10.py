p='/home/bewest/src/rag-nightscout-ecosystem-alignment/docs/40-migration/legacy-cgm-ingestion-to-connect-2026-09-15.md'
s=open(p,encoding='utf-8').read(); orig=s
def rep(old,new):
    global s
    assert s.count(old)==1, ("count=%d for %r" % (s.count(old), old[:90]))
    s=s.replace(old,new,1)

rep("""goldens are described as *"captured from retired minimed-connect-to-nightscout 1.5.8"* and do not
contain the field; and the legacy implementation went to the trouble of *guessing* the offset, which
would be pointless if the payload carried it.""",
"""goldens are described as *"captured from retired minimed-connect-to-nightscout 1.5.8"* and do not
contain the field; and the legacy implementation went to the trouble of *guessing* the offset, which
would be pointless if the payload carried it.

**A third argument, added in review, and it undercuts the fixture's own provenance claim.**
`tests/fixtures/minimed-cutover.json` says `"capturedFrom": "minimed-connect-to-nightscout@1.5.8"`,
but its timestamps are `2026-09-01T12:00:00.000Z` while that package's own recorded CareLink
payloads (`test/_fixtures.js`, `test/_samples.js`) use `"Oct 12, 2015 03:12:10"` and
`"Oct 17, 2015 09:09:14"` — a zone-less, non-ISO format. The fixture is **synthesised in the shape
Connect happens to accept**, not captured from the vendor; and the shape it chose is precisely the
one in which the divergence is invisible. A reviewer should not read `capturedFrom` as provenance.""")

rep("""Connect emits `devicestatus[0].pump.clock` as a zone-offset string (`…T14:00:00.000+02:00`) where the
legacy path always emitted `Z`. The instant is the same; the *string* is not. `devicestatus.created_at`
is normalised by `moment.parseZone(...).toISOString()` in `lib/server/devicestatus.js`, but nested
`pump.clock` is not. Any client that compares `pump.clock` as a string sees a format change.
*(measured in the same harness run.)*""",
"""Connect does not parse `pump.clock` at all: `deviceStatusEntry` assigns
`'clock': data['sMedicalDeviceTime']` **verbatim**, and `reassign_zone('clock')` then rewrites only
the zone suffix if one is already there. The legacy path ran the same field through
`timestampAsString(parsePumpTime(...))` and always emitted a normalised `Z` string. So `pump.clock`
under Connect is **whatever the vendor sent** — `…T14:00:00.000+02:00` when a conduit offset was
applied, `…T14:00:00.000Z` when it was not, and a raw non-ISO string such as
`"Oct 12, 2015 03:12:10"` if that is what CareLink returns. *(Corrected and re-measured in review:
the previous revision described this as a format change; it is an unparsed passthrough, which is a
larger claim — a client doing `new Date(pump.clock)` can get `Invalid Date`.)*
`devicestatus.created_at` **is** normalised, by `moment.parseZone(...).toISOString()` at
`lib/server/devicestatus.js:59-60`, but nested `pump.clock` is not touched.""")
open(p,'w',encoding='utf-8').write(s)
print('ok delta', len(s)-len(orig))
