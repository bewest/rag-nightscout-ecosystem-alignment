p='/home/bewest/src/rag-nightscout-ecosystem-alignment/docs/40-migration/legacy-cgm-ingestion-to-connect-2026-09-15.md'
s=open(p,encoding='utf-8').read(); orig=s
def rep(old,new):
    global s
    assert s.count(old)==1, ("count=%d for %r" % (s.count(old), old[:90]))
    s=s.replace(old,new,1)

rep("""Their evidence quality is not
comparable, and this revision widened the gap. Dexcom has a real MongoDB cutover test, a transform
provably timestamp-identical to the legacy one, a dedup key already shipping on master, and a boot
stage that already stands down for Connect.""",
"""Their evidence quality is not
comparable, and this revision widened the gap. Dexcom has a real MongoDB cutover test, a transform
provably timestamp-identical to the legacy one, a dedup key already shipping on master, a boot
stage that already stands down for Connect — and, strongest of all and found only in review,
**a whole release cycle of production exposure already behind it**: on 15.0.8 `BRIDGE_*` operators
are auto-migrated onto Nightscout Connect at boot and the legacy plugin is already dormant (§5.3.4).
The Dexcom half of cut 4 deletes code that today runs only for the operators who explicitly opted
back into it.""")

# §7 asymmetry table: strengthen the Dexcom row with the auto-migration fact
rep("""| Boot stage stands down for Connect | **Yes** — `bootevent.js:369` | **No** — no guard at all, on `master` or on `dev` (§5.3.3) |""",
"""| Boot stage stands down for Connect | **Yes** — `bootevent.js:368-370`, and `setupConnect` auto-migrates `BRIDGE_*` unconditionally first, so this already happens for every Dexcom operator on 15.0.8 without them doing anything (§5.3.4, measured with controls) | **No** — no guard at all, and no auto-migration, on `master` or on `dev` (§5.3.3) |""")
open(p,'w',encoding='utf-8').write(s)
print('ok delta', len(s)-len(orig))
