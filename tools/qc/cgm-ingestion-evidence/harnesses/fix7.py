p='/home/bewest/src/rag-nightscout-ecosystem-alignment/docs/40-migration/legacy-cgm-ingestion-to-connect-2026-09-15.md'
s=open(p,encoding='utf-8').read(); orig=s
def rep(old,new):
    global s
    assert s.count(old)==1, ("count=%d for %r" % (s.count(old), old[:90]))
    s=s.replace(old,new,1)

# ---- §5.4 line provenance ----
rep("""`nightscout-connect/lib/machines/fetch.js:87` initialises `last_known: null`, and the only
assignments (`fetch.js:173,183`; `cycle.js:192`) set it from freshly fetched data.""",
"""`nightscout-connect/lib/machines/fetch.js` initialises `last_known: null`, and the only assignments
set it from data fetched or persisted **in this process**. *(Line numbers corrected in review: those
are `fetch.js:85`, `fetch.js:171,181` and `cycle.js:160` at cut 4's pin `c962a13f`, and
`fetch.js:87`, `fetch.js:173,183` and `cycle.js:192` in the v0.0.14 working tree the previous
revision actually read. The code is the same; the citation was.)* The `cycle.js` assignment is fed
by a `PERSISTED_DATA` event carrying the result of the persist step, so the watermark advances
within a run and is discarded with the process.""")

# ---- §5.5 quotation fix ----
rep("""`lib/plugins/mmconnect.js:49-73` builds two of them
and comments, in the shipping code:

```js
// The devicestatus collection doesn't upsert, so we need to avoid
var filteredStatus = filterDevicestatus(transformed.devicestatus);
```""",
"""`lib/plugins/mmconnect.js:48-73` builds two of them
and comments, in the shipping code (`:70-72`, quoted in full — the previous revision dropped the
comment's second line):

```js
// The devicestatus collection doesn't upsert, so we need to avoid
// duplicates here
var filteredStatus = filterDevicestatus(transformed.devicestatus);
```""")

rep("""an in-process `makeRecencyFilter` whose `lastTime` starts at `0` on every restart, with a comment in `lib/plugins/mmconnect.js:71-73` saying *\"The devicestatus collection doesn't upsert, so we need to avoid\"* duplicates.""",
"""an in-process `makeRecencyFilter` whose `lastTime` starts at `0` on every restart, with a comment at `lib/plugins/mmconnect.js:70-71` saying *\"The devicestatus collection doesn't upsert, so we need to avoid duplicates here\"*.""")

# ---- §7.1 D6 count ----
rep("""**D6. Fix the version strings.** Both cut-4 shims emit operator-facing error text saying *"retired in
Nightscout 15.0.9"* (four occurrences, verified by `git grep -n "retired in"`).""",
"""**D6. Fix the version strings.** Both cut-4 shims emit operator-facing error text saying *"retired in
Nightscout 15.0.9"*. *(Count corrected in review: `git grep -n "retired in" origin/chore/mime-exposure-review -- lib/`
returns **5** lines, not four — the exact string `retired in Nightscout 15.0.9` appears **3** times,
once in `bridge-connect-compat.js:14` and twice in `mmconnect-connect-compat.js:8,19`, and
`bootevent.js:55` and `:339` add two `console.log` lines saying `retired in 15.0.9`. All five need
changing.)*""")
open(p,'w',encoding='utf-8').write(s)
print('ok delta', len(s)-len(orig))
