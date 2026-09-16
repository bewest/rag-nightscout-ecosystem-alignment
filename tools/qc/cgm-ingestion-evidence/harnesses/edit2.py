import io,sys
p='docs/30-design/phase0-pr-sequencing-2026-09-15.md'
s=io.open(p,encoding='utf-8').read()
def rep(old,new):
    global s
    if s.count(old)!=1:
        sys.exit("NOT UNIQUE (%d): %r" % (s.count(old), old[:70]))
    s=s.replace(old,new)

rep("""> **`bf/connect-pin` should land before any operator is advised to migrate MiniMed.** See
> [E2](../60-research/e2-medtronic-path-comparison-2026-09-15.md).""",
"""> **`bf/connect-pin` should land before any operator is advised to migrate MiniMed.** See
> [E2](../60-research/e2-medtronic-path-comparison-2026-09-15.md).
>
> **But v0.0.14 is not a clean bill of health for MiniMed, and this document should not read as if
> it were (added 2026-09-16, adversarial review).** E2 reproduced, driving the connector's own
> `lib/builder.js` and `lib/machines/*` with only the network stubbed, that
> `lib/sources/minimedcarelink/index.js` guards `data.medicalDeviceFamily` and then does
> `data.markers.filter(...)` **unguarded**: a CareLink payload with no `markers` key throws a
> synchronous `TypeError` that escapes `transformService` before `Promise.resolve`, so `onError`
> never sees it — and cgm-remote-monitor registers no `uncaughtException` handler, so the Nightscout
> process dies. **Independently confirmed here, read-derived:** `var markers = data.markers` followed
> by `markers_to_treatment(markers)` is present at `v0.0.13`, `234d47c8`, `c962a13f` **and
> `v0.0.14`** (`git show <ref>:lib/sources/minimedcarelink/index.js`). Whether a real CareLink
> payload ever omits `markers` is one of the things no account on this machine can settle; the
> retired package's own recorded payloads have no `markers` key, and every occurrence in the
> connector's test suite is an injected `markers: []`, so the absence has **zero coverage**.
> `bf/connect-pin` fixes the gap-sentinel and `created_at` defects; it does **not** fix this one.""")
io.open(p,'w',encoding='utf-8').write(s)
print("ok")
