# ID-FIRST-MATCH: cell-by-cell impact (appendix)

*Generated 2026-10-29 by a classification script (session scratch, not committed; its rules are in the note, section 2) from the pin `tools/qc/results/write-contract-matrix/dev-e1f7ac41-idfirst.json` (1,929 cells: 456 earlier, 1,473 new). The design note is [`id-first-match-design-note-2026-10-29.md`](id-first-match-design-note-2026-10-29.md). "Today" columns are **[M]**, the pin. Every "predicted" column is **[R, prediction]**: read from code at crm `e8224807` and the rule in the note §1, not run. The implementation slice measures each one.*

Rule options used: socket treatments merge on an identifier match (**option M**, decision 1 as written); shared-identifier pick **P1** (each path keeps today's pick; a path new to identifier matching picks the first stored record). Option K (socket treatments keep the stored record on an identifier match) differs only where listed at the end.

Format of "today": reply · stored records (`n=`, one label per record: `OID`/`str*` the `_id` form, `:v2` the re-send's fields are on it, `:inv` soft-deleted) · `shape` · `srv`. Predicted: stored records · `shape` · note. A reply is predicted unchanged unless the note says otherwise.

## Counts

| group | cells | per collection / path (`A>B` = seeded through A, re-sent through B) |
|---|---:|---|
| (a) The write changes, no recorded value is predicted to change | 62 | activity inproc 5, activity v1 4, devicestatus inproc>ws 1, devicestatus v1>ws 1, devicestatus v3>ws 1, devicestatus ws 2, entries inproc>v3 1, entries v1>v3 1, entries v3 1, entries ws>v3 1, food inproc 5, food v1 4, food v3 1, food ws>v3 1, profile inproc>v3 1, profile inproc>ws 1, profile v1>v3 1, profile v1>ws 1, profile v3 1, profile v3>ws 1, profile ws 5, profile ws>v3 1, settings v3 1, treatments inproc 6, treatments inproc>v1 1, treatments inproc>v3 1, treatments v1 6, treatments v1>inproc 1, treatments v1>v3 1, treatments v3 1, treatments ws>inproc 1, treatments ws>v1 1, treatments ws>v3 1 |
| (b) Identifier now matches where a second record was stored | 88 | activity inproc 3, activity inproc>v1 2, activity inproc>ws 2, activity v1 3, activity v1>inproc 2, activity v1>ws 2, activity ws 3, activity ws>inproc 2, activity ws>v1 2, devicestatus inproc>ws 1, devicestatus v1>ws 1, devicestatus v3>ws 1, devicestatus ws 1, entries inproc>ws 2, entries v1>ws 2, entries v3>ws 2, entries ws 3, food inproc 3, food inproc>v1 2, food inproc>ws 2, food v1 3, food v1>inproc 2, food v1>ws 2, food v3>inproc 2, food v3>v1 2, food v3>ws 2, food ws 3, food ws>inproc 2, food ws>v1 2, profile inproc 3, profile inproc>v1 2, profile inproc>ws 1, profile v1 3, profile v1>inproc 2, profile v1>ws 1, profile v3>inproc 2, profile v3>v1 2, profile v3>ws 1, profile ws 1, profile ws>inproc 2, profile ws>v1 2, treatments inproc>ws 1, treatments v1>ws 1, treatments v3>ws 1, treatments ws 2 |
| (c1) Replace becomes merge (same record) | 216 | activity inproc 3, activity ws>inproc 2, entries inproc>v3 5, entries v1>v3 5, entries v3 10, entries ws>v3 5, food inproc 3, food inproc>v3 1, food v1>v3 1, food v3 10, food ws>inproc 2, food ws>v3 5, profile inproc>v3 5, profile inproc>ws 7, profile v1>v3 5, profile v1>ws 6, profile v3 10, profile v3>ws 6, profile ws 13, profile ws>v3 5, settings v3 10, treatments inproc 14, treatments inproc>v1 8, treatments inproc>v3 5, treatments v1 14, treatments v1>inproc 8, treatments v1>v3 5, treatments v3 10, treatments v3>inproc 6, treatments v3>v1 6, treatments ws>inproc 8, treatments ws>v1 8, treatments ws>v3 5 |
| (c2) Kept becomes merge: socket treatments, option M only | 4 | treatments inproc>ws 1, treatments v1>ws 1, treatments v3>ws 1, treatments ws 1 |
| (d1) Revived becomes "acknowledged, stays deleted" | 36 | entries inproc 2, entries v1 2, entries v3 4, food v3 4, profile v3 4, profile ws 4, settings v3 4, treatments inproc 4, treatments v1 4, treatments v3 4 |
| (d2) A new record beside a deleted one becomes "acknowledged, stays deleted" | 23 | activity inproc 1, activity v1 1, activity ws 1, devicestatus ws 4, entries ws 2, food inproc 2, food v1 2, food ws 2, profile inproc 2, profile v1 2, treatments ws 4 |
| (g) Two stored records share one identifier (the split family, BF-212), pick rule P1 | 50 | activity inproc 3, activity v1 3, activity ws 3, devicestatus ws 1, entries v3 2, entries ws 3, food inproc 3, food v1 3, food v3 2, food ws 3, profile inproc 3, profile v1 3, profile v3 2, profile ws 3, settings v3 2, treatments inproc 3, treatments v1 3, treatments v3 2, treatments ws 3 |
| (g, not visible) Same matrix values, the reply names another record | 1 | devicestatus ws 1 |
| (h) Unchanged as read, but in question: devicestatus API v3 fallback replace | 12 | devicestatus inproc>v3 4, devicestatus v1>v3 4, devicestatus ws>v3 4 |

## (a) The write changes, no recorded value is predicted to change: 62 cells

| cell | today [M] | predicted [R, prediction] |
|---|---|---|
| `activity inproc legacy-lower` | cb [1 _id=sent] · n=1 OID · None · srv noCnoM | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `activity inproc legacy-upper` | cb [1 _id] · n=1 OID · None · srv noCnoM | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `activity inproc resend-hex` | cb [1 _id=sent] · n=1 OID · None · srv noCnoM | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `activity inproc resend-oid` | cb [1 _id=sent] · n=1 OID · None · srv noCnoM | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `activity inproc resend-upper` | cb [1 _id] · n=1 OID · None · srv noCnoM | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `activity v1 legacy-lower` | 200 [1 _id=sent] · n=1 OID · None · srv noCnoM | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `activity v1 legacy-upper` | 200 [1 _id] · n=1 OID · None · srv noCnoM | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `activity v1 resend-hex` | 200 [1 _id=sent] · n=1 OID · None · srv noCnoM | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `activity v1 resend-upper` | 200 [1 _id] · n=1 OID · None · srv noCnoM | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `devicestatus ws idf-identifier-amt` | ack [1 _id] · n=1 OID · not-written · srv C=M= | n=1 OID · not-written · match key changes to identifier; values as today |
| `devicestatus ws idf-identifier-same` | ack [1 _id] · n=1 OID · not-written · srv C=M= | n=1 OID · not-written · match key changes to identifier; values as today |
| `devicestatus x inproc x ws idf-identifier-same` | ack [1 _id] · n=1 OID · not-written · srv C=M= | n=1 OID · not-written · match key changes to identifier; values as today |
| `devicestatus x v1 x ws idf-identifier-same` | ack [1 _id] · n=1 OID · not-written · srv C=M= | n=1 OID · not-written · match key changes to identifier; values as today |
| `devicestatus x v3 x ws idf-identifier-same` | ack [1 _id] · n=1 OID · not-written · srv C=M= | n=1 OID · not-written · match key changes to identifier; values as today |
| `entries v3 resend-identity` | 200 {..} · n=1 OID · None · srv C=M+ | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `entries x inproc x v3` | 200 {..} · n=1 OID · None · srv None | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `entries x v1 x v3` | 200 {..} · n=1 OID · None · srv None | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `entries x ws x v3` | 200 {..} · n=1 OID · None · srv None | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `food inproc legacy-lower` | cb [1 _id=sent] · n=1 OID · None · srv CM | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `food inproc legacy-upper` | cb [1 _id] · n=1 OID · None · srv CM | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `food inproc resend-hex` | cb [1 _id=sent] · n=1 OID · None · srv C=M+ | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `food inproc resend-oid` | cb [1 _id=sent] · n=1 OID · None · srv C=M+ | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `food inproc resend-upper` | cb [1 _id] · n=1 OID · None · srv C=M+ | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `food v1 legacy-lower` | 200 [1 _id=sent] · n=1 OID · None · srv CM | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `food v1 legacy-upper` | 200 [1 _id] · n=1 OID · None · srv CM | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `food v1 resend-hex` | 200 [1 _id=sent] · n=1 OID · None · srv C=M+ | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `food v1 resend-upper` | 200 [1 _id] · n=1 OID · None · srv C=M+ | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `food v3 resend-identity` | 200 {..} · n=1 OID · None · srv C=M+ | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `food x ws x v3` | 200 {..} · n=1 OID · None · srv None | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `profile v3 resend-identity` | 200 {..} · n=1 OID · None · srv C=M+ | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `profile ws legacy-lower` | ack [1 _id=sent] · n=1 str · None · srv noCM+ | n=1 str · replace -> merge of an identical body: no recorded value predicted to change |
| `profile ws legacy-upper` | ack [1 _id] · n=1 str · None · srv noCM+ | n=1 str · replace -> merge of an identical body: no recorded value predicted to change |
| `profile ws resend-hex` | ack [1 _id=sent] · n=1 OID · None · srv C=M+ | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `profile ws resend-identity` | ack [1 _id] · n=1 OID · None · srv C=M+ | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `profile ws resend-upper` | ack [1 _id] · n=1 OID · None · srv C=M+ | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `profile x inproc x v3` | 200 {..} · n=1 OID · None · srv None | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `profile x inproc x ws` | ack [1 _id] · n=1 OID · None · srv None | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `profile x v1 x v3` | 200 {..} · n=1 OID · None · srv None | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `profile x v1 x ws` | ack [1 _id] · n=1 OID · None · srv None | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `profile x v3 x ws` | ack [1 _id] · n=1 OID · None · srv None | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `profile x ws x v3` | 200 {..} · n=1 OID · None · srv None | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `settings v3 resend-identity` | 200 {..} · n=1 OID · None · srv C=M+ | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `treatments inproc legacy-lower` | cb [1 _id=sent] · n=1 OID · None · srv CM | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `treatments inproc legacy-upper` | cb [1 _id] · n=1 OID · None · srv CM | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `treatments inproc resend-hex` | cb [1 _id=sent] · n=1 OID · None · srv C=M+ | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `treatments inproc resend-identity` | cb [1 _id] · n=1 OID · None · srv C=M+ | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `treatments inproc resend-oid` | cb [1 _id=sent] · n=1 OID · None · srv C=M+ | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `treatments inproc resend-upper` | cb [1 _id] · n=1 OID · None · srv C=M+ | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `treatments v1 legacy-lower` | 200 [1 _id=sent] · n=1 OID · None · srv CM | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `treatments v1 legacy-upper` | 200 [1 _id] · n=1 OID · None · srv CM | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `treatments v1 resend-hex` | 200 [1 _id=sent] · n=1 OID · None · srv C=M+ | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `treatments v1 resend-identity` | 200 [1 _id] · n=1 OID · None · srv C=M+ | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `treatments v1 resend-oid` | 200 [1 _id] · n=1 OID · None · srv C=M+ | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `treatments v1 resend-upper` | 200 [1 _id] · n=1 OID · None · srv C=M+ | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `treatments v3 resend-identity` | 200 {..} · n=1 OID · None · srv C=M+ | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `treatments x inproc x v1` | 200 [1 _id] · n=1 OID · None · srv None | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `treatments x inproc x v3` | 200 {..} · n=1 OID · None · srv None | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `treatments x v1 x inproc` | cb [1 _id] · n=1 OID · None · srv None | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `treatments x v1 x v3` | 200 {..} · n=1 OID · None · srv None | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `treatments x ws x inproc` | cb [1 _id] · n=1 OID · None · srv None | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `treatments x ws x v1` | 200 [1 _id] · n=1 OID · None · srv None | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |
| `treatments x ws x v3` | 200 {..} · n=1 OID · None · srv None | n=1 OID · replace -> merge of an identical body: no recorded value predicted to change |

## (b) Identifier now matches where a second record was stored: 88 cells

| cell | today [M] | predicted [R, prediction] |
|---|---|---|
| `activity inproc idf-identifier-amt` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:v2 · merge |
| `activity inproc idf-identifier-same` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:v2 · merge |
| `activity inproc idf-identifier-time` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:v2 · merge |
| `activity v1 idf-identifier-amt` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:v2 · merge |
| `activity v1 idf-identifier-same` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:v2 · merge |
| `activity v1 idf-identifier-time` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:v2 · merge |
| `activity ws idf-identifier-amt` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:v2 · merge |
| `activity ws idf-identifier-same` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:v2 · merge |
| `activity ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:v2 · merge |
| `activity x inproc x v1 idf-identifier-same` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:v2 · merge |
| `activity x inproc x v1 idf-identifier-time` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:v2 · merge |
| `activity x inproc x ws idf-identifier-same` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:v2 · merge |
| `activity x inproc x ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:v2 · merge |
| `activity x v1 x inproc idf-identifier-same` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:v2 · merge |
| `activity x v1 x inproc idf-identifier-time` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:v2 · merge |
| `activity x v1 x ws idf-identifier-same` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:v2 · merge |
| `activity x v1 x ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:v2 · merge |
| `activity x ws x inproc idf-identifier-same` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:v2 · merge |
| `activity x ws x inproc idf-identifier-time` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:v2 · merge |
| `activity x ws x v1 idf-identifier-same` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:v2 · merge |
| `activity x ws x v1 idf-identifier-time` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:v2 · merge |
| `devicestatus ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID · not-written |
| `devicestatus x inproc x ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID · not-written |
| `devicestatus x v1 x ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID · not-written |
| `devicestatus x v3 x ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID · not-written |
| `entries ws idf-identifier-amt` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `entries ws idf-identifier-same` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `entries ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `entries x inproc x ws idf-identifier-same` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `entries x inproc x ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `entries x v1 x ws idf-identifier-same` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `entries x v1 x ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `entries x v3 x ws idf-identifier-same` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `entries x v3 x ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food inproc idf-identifier-amt` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food inproc idf-identifier-same` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food inproc idf-identifier-time` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food v1 idf-identifier-amt` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food v1 idf-identifier-same` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food v1 idf-identifier-time` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food ws idf-identifier-amt` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food ws idf-identifier-same` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food x inproc x v1 idf-identifier-same` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food x inproc x v1 idf-identifier-time` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food x inproc x ws idf-identifier-same` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food x inproc x ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food x v1 x inproc idf-identifier-same` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food x v1 x inproc idf-identifier-time` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food x v1 x ws idf-identifier-same` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food x v1 x ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food x v3 x inproc idf-identifier-same` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food x v3 x inproc idf-identifier-time` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food x v3 x v1 idf-identifier-same` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food x v3 x v1 idf-identifier-time` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food x v3 x ws idf-identifier-same` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food x v3 x ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food x ws x inproc idf-identifier-same` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food x ws x inproc idf-identifier-time` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food x ws x v1 idf-identifier-same` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `food x ws x v1 idf-identifier-time` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile inproc idf-identifier-amt` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile inproc idf-identifier-same` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile inproc idf-identifier-time` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile v1 idf-identifier-amt` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile v1 idf-identifier-same` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile v1 idf-identifier-time` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile x inproc x v1 idf-identifier-same` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile x inproc x v1 idf-identifier-time` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile x inproc x ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile x v1 x inproc idf-identifier-same` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile x v1 x inproc idf-identifier-time` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile x v1 x ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile x v3 x inproc idf-identifier-same` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile x v3 x inproc idf-identifier-time` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile x v3 x v1 idf-identifier-same` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile x v3 x v1 idf-identifier-time` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile x v3 x ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile x ws x inproc idf-identifier-same` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile x ws x inproc idf-identifier-time` | cb [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile x ws x v1 idf-identifier-same` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `profile x ws x v1 idf-identifier-time` | 200 [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `treatments ws idf-identifier-amt` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `treatments ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `treatments x inproc x ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `treatments x v1 x ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |
| `treatments x v3 x ws idf-identifier-time` | ack [1 _id] · n=2 OID,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:v2 · merge |

## (c1) Replace becomes merge (same record): 216 cells

| cell | today [M] | predicted [R, prediction] |
|---|---|---|
| `activity inproc idf-uuidid-amt` | cb [1 _id=sent] · n=1 str*:v2 · replace · srv noCnoM | n=1 str*:v2 · merge |
| `activity inproc idf-uuidid-same` | cb [1 _id=sent] · n=1 str*:v2 · replace · srv noCnoM | n=1 str*:v2 · merge |
| `activity inproc idf-uuidid-time` | cb [1 _id=sent] · n=1 str*:v2 · replace · srv noCnoM | n=1 str*:v2 · merge |
| `activity x ws x inproc idf-uuidid-same` | cb [1 _id=sent] · n=1 str*:v2 · replace · srv noCnoM | n=1 str*:v2 · merge |
| `activity x ws x inproc idf-uuidid-time` | cb [1 _id=sent] · n=1 str*:v2 · replace · srv noCnoM | n=1 str*:v2 · merge |
| `entries v3 idf-NSCLIENT_ID-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries v3 idf-NSCLIENT_ID-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries v3 idf-id-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries v3 idf-id-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries v3 idf-identifier-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries v3 idf-identifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries v3 idf-syncIdentifier-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries v3 idf-syncIdentifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries v3 idf-uuid-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries v3 idf-uuid-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries x inproc x v3 idf-NSCLIENT_ID-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries x inproc x v3 idf-id-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries x inproc x v3 idf-identifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries x inproc x v3 idf-syncIdentifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries x inproc x v3 idf-uuid-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries x v1 x v3 idf-NSCLIENT_ID-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries x v1 x v3 idf-id-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries x v1 x v3 idf-identifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries x v1 x v3 idf-syncIdentifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries x v1 x v3 idf-uuid-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries x ws x v3 idf-NSCLIENT_ID-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries x ws x v3 idf-id-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries x ws x v3 idf-identifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries x ws x v3 idf-syncIdentifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `entries x ws x v3 idf-uuid-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `food inproc idf-uuidid-amt` | cb [1 _id=sent] · n=1 str*:v2 · replace · srv C=M+ | n=1 str*:v2 · merge |
| `food inproc idf-uuidid-same` | cb [1 _id=sent] · n=1 str*:v2 · replace · srv C=M+ | n=1 str*:v2 · merge |
| `food inproc idf-uuidid-time` | cb [1 _id=sent] · n=1 str*:v2 · replace · srv C=M+ | n=1 str*:v2 · merge |
| `food v3 idf-NSCLIENT_ID-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `food v3 idf-NSCLIENT_ID-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `food v3 idf-id-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `food v3 idf-id-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `food v3 idf-identifier-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `food v3 idf-identifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `food v3 idf-syncIdentifier-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `food v3 idf-syncIdentifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `food v3 idf-uuid-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `food v3 idf-uuid-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `food x inproc x v3 idf-identifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `food x v1 x v3 idf-identifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `food x ws x inproc idf-uuidid-same` | cb [1 _id=sent] · n=1 str*:v2 · replace · srv C=M+ | n=1 str*:v2 · merge |
| `food x ws x inproc idf-uuidid-time` | cb [1 _id=sent] · n=1 str*:v2 · replace · srv C=M+ | n=1 str*:v2 · merge |
| `food x ws x v3 idf-NSCLIENT_ID-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `food x ws x v3 idf-id-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `food x ws x v3 idf-identifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `food x ws x v3 idf-syncIdentifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `food x ws x v3 idf-uuid-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile v3 idf-NSCLIENT_ID-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile v3 idf-NSCLIENT_ID-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile v3 idf-id-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile v3 idf-id-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile v3 idf-identifier-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile v3 idf-identifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile v3 idf-syncIdentifier-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile v3 idf-syncIdentifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile v3 idf-uuid-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile v3 idf-uuid-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile ws idf-NSCLIENT_ID-amt` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile ws idf-NSCLIENT_ID-same` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile ws idf-NSCLIENT_ID-time` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile ws idf-id-amt` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile ws idf-id-same` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile ws idf-identifier-amt` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile ws idf-identifier-same` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile ws idf-syncIdentifier-amt` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile ws idf-syncIdentifier-same` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile ws idf-uuid-amt` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile ws idf-uuid-same` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile ws idf-uuidid-amt` | ack [1 _id=sent] · n=1 str*:v2 · replace · srv C=M+ | n=1 str*:v2 · merge |
| `profile ws idf-uuidid-same` | ack [1 _id=sent] · n=1 str*:v2 · replace · srv C=M+ | n=1 str*:v2 · merge |
| `profile x inproc x v3 idf-NSCLIENT_ID-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x inproc x v3 idf-id-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x inproc x v3 idf-identifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x inproc x v3 idf-syncIdentifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x inproc x v3 idf-uuid-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x inproc x ws idf-NSCLIENT_ID-same` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x inproc x ws idf-NSCLIENT_ID-time` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x inproc x ws idf-id-same` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x inproc x ws idf-identifier-same` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x inproc x ws idf-syncIdentifier-same` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x inproc x ws idf-uuid-same` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x inproc x ws idf-uuidid-same` | ack [1 _id=sent] · n=1 str*:v2 · replace · srv C=M+ | n=1 str*:v2 · merge |
| `profile x v1 x v3 idf-NSCLIENT_ID-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x v1 x v3 idf-id-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x v1 x v3 idf-identifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x v1 x v3 idf-syncIdentifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x v1 x v3 idf-uuid-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x v1 x ws idf-NSCLIENT_ID-same` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x v1 x ws idf-NSCLIENT_ID-time` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x v1 x ws idf-id-same` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x v1 x ws idf-identifier-same` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x v1 x ws idf-syncIdentifier-same` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x v1 x ws idf-uuid-same` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x v3 x ws idf-NSCLIENT_ID-same` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x v3 x ws idf-NSCLIENT_ID-time` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x v3 x ws idf-id-same` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x v3 x ws idf-identifier-same` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x v3 x ws idf-syncIdentifier-same` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x v3 x ws idf-uuid-same` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x ws x v3 idf-NSCLIENT_ID-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x ws x v3 idf-id-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x ws x v3 idf-identifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x ws x v3 idf-syncIdentifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `profile x ws x v3 idf-uuid-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `settings v3 idf-NSCLIENT_ID-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `settings v3 idf-NSCLIENT_ID-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `settings v3 idf-id-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `settings v3 idf-id-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `settings v3 idf-identifier-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `settings v3 idf-identifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `settings v3 idf-syncIdentifier-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `settings v3 idf-syncIdentifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `settings v3 idf-uuid-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `settings v3 idf-uuid-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments inproc idf-NSCLIENT_ID-amt` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments inproc idf-NSCLIENT_ID-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments inproc idf-id-amt` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments inproc idf-id-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments inproc idf-identifier-amt` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments inproc idf-identifier-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments inproc idf-identifier-time` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments inproc idf-syncIdentifier-amt` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments inproc idf-syncIdentifier-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments inproc idf-uuid-amt` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments inproc idf-uuid-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments inproc idf-uuidid-amt` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments inproc idf-uuidid-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments inproc idf-uuidid-time` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v1 idf-NSCLIENT_ID-amt` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v1 idf-NSCLIENT_ID-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v1 idf-id-amt` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v1 idf-id-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v1 idf-identifier-amt` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v1 idf-identifier-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v1 idf-identifier-time` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v1 idf-syncIdentifier-amt` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v1 idf-syncIdentifier-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v1 idf-uuid-amt` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v1 idf-uuid-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v1 idf-uuidid-amt` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v1 idf-uuidid-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v1 idf-uuidid-time` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v3 idf-NSCLIENT_ID-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v3 idf-NSCLIENT_ID-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v3 idf-id-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v3 idf-id-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v3 idf-identifier-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v3 idf-identifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v3 idf-syncIdentifier-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v3 idf-syncIdentifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v3 idf-uuid-amt` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments v3 idf-uuid-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x inproc x v1 idf-NSCLIENT_ID-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x inproc x v1 idf-id-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x inproc x v1 idf-identifier-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x inproc x v1 idf-identifier-time` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x inproc x v1 idf-syncIdentifier-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x inproc x v1 idf-uuid-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x inproc x v1 idf-uuidid-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x inproc x v1 idf-uuidid-time` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x inproc x v3 idf-NSCLIENT_ID-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x inproc x v3 idf-id-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x inproc x v3 idf-identifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x inproc x v3 idf-syncIdentifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x inproc x v3 idf-uuid-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v1 x inproc idf-NSCLIENT_ID-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v1 x inproc idf-id-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v1 x inproc idf-identifier-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v1 x inproc idf-identifier-time` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v1 x inproc idf-syncIdentifier-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v1 x inproc idf-uuid-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v1 x inproc idf-uuidid-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v1 x inproc idf-uuidid-time` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v1 x v3 idf-NSCLIENT_ID-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v1 x v3 idf-id-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v1 x v3 idf-identifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v1 x v3 idf-syncIdentifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v1 x v3 idf-uuid-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v3 x inproc idf-NSCLIENT_ID-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v3 x inproc idf-id-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v3 x inproc idf-identifier-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v3 x inproc idf-identifier-time` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v3 x inproc idf-syncIdentifier-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v3 x inproc idf-uuid-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v3 x v1 idf-NSCLIENT_ID-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v3 x v1 idf-id-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v3 x v1 idf-identifier-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v3 x v1 idf-identifier-time` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v3 x v1 idf-syncIdentifier-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v3 x v1 idf-uuid-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x ws x inproc idf-NSCLIENT_ID-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x ws x inproc idf-id-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x ws x inproc idf-identifier-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x ws x inproc idf-identifier-time` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x ws x inproc idf-syncIdentifier-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x ws x inproc idf-uuid-same` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x ws x inproc idf-uuidid-same` | cb [1 _id=sent] · n=1 str*:v2 · replace · srv C=M+ | n=1 str*:v2 · merge |
| `treatments x ws x inproc idf-uuidid-time` | cb [1 _id=sent] · n=1 str*:v2 · replace · srv C=M+ | n=1 str*:v2 · merge |
| `treatments x ws x v1 idf-NSCLIENT_ID-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x ws x v1 idf-id-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x ws x v1 idf-identifier-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x ws x v1 idf-identifier-time` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x ws x v1 idf-syncIdentifier-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x ws x v1 idf-uuid-same` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x ws x v1 idf-uuidid-same` | 200 [1 _id=sent] · n=1 str*:v2 · replace · srv C=M+ | n=1 str*:v2 · merge |
| `treatments x ws x v1 idf-uuidid-time` | 200 [1 _id=sent] · n=1 str*:v2 · replace · srv C=M+ | n=1 str*:v2 · merge |
| `treatments x ws x v3 idf-NSCLIENT_ID-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x ws x v3 idf-id-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x ws x v3 idf-identifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x ws x v3 idf-syncIdentifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x ws x v3 idf-uuid-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge |

## (c2) Kept becomes merge: socket treatments, option M only: 4 cells

| cell | today [M] | predicted [R, prediction] |
|---|---|---|
| `treatments ws idf-identifier-same` | ack [1 _id] · n=1 OID · not-written · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x inproc x ws idf-identifier-same` | ack [1 _id] · n=1 OID · not-written · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v1 x ws idf-identifier-same` | ack [1 _id] · n=1 OID · not-written · srv C=M+ | n=1 OID:v2 · merge |
| `treatments x v3 x ws idf-identifier-same` | ack [1 _id] · n=1 OID · not-written · srv C=M+ | n=1 OID:v2 · merge |

## (d1) Revived becomes "acknowledged, stays deleted": 36 cells

| cell | today [M] | predicted [R, prediction] |
|---|---|---|
| `entries inproc idf-v3del-identifier` | cb [1 _id] · n=1 OID:v2 · merge · srv C=M+ | n=1 OID:inv · not-written |
| `entries inproc idf-v3del-plain` | cb [1 _id] · n=1 OID:v2 · merge · srv C=M+ | n=1 OID:inv · not-written |
| `entries v1 idf-v3del-identifier` | 200 [1 _id] · n=1 OID:v2 · merge · srv C=M+ | n=1 OID:inv · not-written |
| `entries v1 idf-v3del-plain` | 200 [1 _id] · n=1 OID:v2 · merge · srv C=M+ | n=1 OID:inv · not-written |
| `entries v3 idf-softdel-identifier` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `entries v3 idf-softdel-plain` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `entries v3 idf-v3del-identifier` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `entries v3 idf-v3del-plain` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `food v3 idf-softdel-identifier` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `food v3 idf-softdel-plain` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `food v3 idf-v3del-identifier` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `food v3 idf-v3del-plain` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `profile v3 idf-softdel-identifier` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `profile v3 idf-softdel-plain` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `profile v3 idf-v3del-identifier` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `profile v3 idf-v3del-plain` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `profile ws idf-softdel-identifier` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `profile ws idf-softdel-plain` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `profile ws idf-v3del-identifier` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `profile ws idf-v3del-plain` | ack [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `settings v3 idf-softdel-identifier` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `settings v3 idf-softdel-plain` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `settings v3 idf-v3del-identifier` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `settings v3 idf-v3del-plain` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `treatments inproc idf-softdel-identifier` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `treatments inproc idf-softdel-plain` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `treatments inproc idf-v3del-identifier` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `treatments inproc idf-v3del-plain` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `treatments v1 idf-softdel-identifier` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `treatments v1 idf-softdel-plain` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `treatments v1 idf-v3del-identifier` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `treatments v1 idf-v3del-plain` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `treatments v3 idf-softdel-identifier` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `treatments v3 idf-softdel-plain` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `treatments v3 idf-v3del-identifier` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |
| `treatments v3 idf-v3del-plain` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:inv · not-written |

## (d2) A new record beside a deleted one becomes "acknowledged, stays deleted": 23 cells

| cell | today [M] | predicted [R, prediction] |
|---|---|---|
| `activity inproc idf-softdel-identifier` | cb [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:inv · not-written |
| `activity v1 idf-softdel-identifier` | 200 [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:inv · not-written |
| `activity ws idf-softdel-identifier` | ack [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv noCnoM,noCnoM | n=1 OID:inv · not-written |
| `devicestatus ws idf-softdel-identifier` | ack [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:inv · not-written |
| `devicestatus ws idf-softdel-plain` | ack [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:inv · not-written |
| `devicestatus ws idf-v3del-identifier` | ack [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:inv · not-written |
| `devicestatus ws idf-v3del-plain` | ack [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:inv · not-written |
| `entries ws idf-softdel-identifier` | ack [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:inv · not-written |
| `entries ws idf-v3del-identifier` | ack [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:inv · not-written |
| `food inproc idf-softdel-identifier` | cb [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:inv · not-written |
| `food inproc idf-v3del-identifier` | cb [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:inv · not-written |
| `food v1 idf-softdel-identifier` | 200 [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:inv · not-written |
| `food v1 idf-v3del-identifier` | 200 [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:inv · not-written |
| `food ws idf-softdel-identifier` | ack [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:inv · not-written |
| `food ws idf-v3del-identifier` | ack [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:inv · not-written |
| `profile inproc idf-softdel-identifier` | cb [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:inv · not-written |
| `profile inproc idf-v3del-identifier` | cb [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:inv · not-written |
| `profile v1 idf-softdel-identifier` | 200 [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:inv · not-written |
| `profile v1 idf-v3del-identifier` | 200 [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:inv · not-written |
| `treatments ws idf-softdel-identifier` | ack [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:inv · not-written |
| `treatments ws idf-softdel-plain` | ack [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:inv · not-written |
| `treatments ws idf-v3del-identifier` | ack [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:inv · not-written |
| `treatments ws idf-v3del-plain` | ack [1 _id] · n=2 OID:inv,OID:v2 · not-written,new · srv C=M=,CM | n=1 OID:inv · not-written |

## (g) Two stored records share one identifier (the split family, BF-212), pick rule P1: 50 cells

| cell | today [M] | predicted [R, prediction] |
|---|---|---|
| `activity inproc idf-split-first` | cb [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,noCnoM | n=2 OID:v2,OID · merge,not-written · A re-sent, lands on A |
| `activity inproc idf-split-second` | cb [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,noCnoM | n=2 OID:v2,OID · merge,not-written · B re-sent, lands on A: A takes B's body |
| `activity inproc idf-split-written` | cb [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv noCnoM,noCnoM,noCnoM | n=1 OID:v2 · merge · B's own write matched A by identifier: one record |
| `activity v1 idf-split-first` | 200 [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,noCnoM | n=2 OID:v2,OID · merge,not-written · A re-sent, lands on A |
| `activity v1 idf-split-second` | 200 [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,noCnoM | n=2 OID:v2,OID · merge,not-written · B re-sent, lands on A: A takes B's body |
| `activity v1 idf-split-written` | 200 [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv noCnoM,noCnoM,noCnoM | n=1 OID:v2 · merge · B's own write matched A by identifier: one record |
| `activity ws idf-split-first` | ack [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,noCnoM | n=2 OID:v2,OID · merge,not-written · A re-sent, lands on A |
| `activity ws idf-split-second` | ack [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,noCnoM | n=2 OID:v2,OID · merge,not-written · B re-sent, lands on A: A takes B's body |
| `activity ws idf-split-written` | ack [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv noCnoM,noCnoM,noCnoM | n=1 OID:v2 · merge · B's own write matched A by identifier: one record |
| `devicestatus ws idf-split-written` | ack [1 _id] · n=2 OID,OID · not-written,not-written · srv C=M=,C=M= | n=1 OID · not-written · B's own write matched A by identifier: one record |
| `entries v3 idf-split-second` | 200 {..} · n=2 OID,OID:v2 · not-written,replace · srv C=M=,C=M+ | n=2 OID,OID:v2 · not-written,merge · replace -> merge, same target |
| `entries v3 idf-split-written` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge · replace -> merge, same target |
| `entries ws idf-split-first` | ack [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,CM | n=2 OID:v2,OID · merge,not-written · A re-sent, lands on A |
| `entries ws idf-split-second` | ack [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,CM | n=2 OID:v2,OID · merge,not-written · B re-sent, lands on A: A takes B's body |
| `entries ws idf-split-written` | ack [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,CM | n=1 OID:v2 · merge · B's own write matched A by identifier: one record |
| `food inproc idf-split-first` | cb [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,CM | n=2 OID:v2,OID · merge,not-written · A re-sent, lands on A |
| `food inproc idf-split-second` | cb [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,CM | n=2 OID:v2,OID · merge,not-written · B re-sent, lands on A: A takes B's body |
| `food inproc idf-split-written` | cb [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,CM | n=1 OID:v2 · merge · B's own write matched A by identifier: one record |
| `food v1 idf-split-first` | 200 [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,CM | n=2 OID:v2,OID · merge,not-written · A re-sent, lands on A |
| `food v1 idf-split-second` | 200 [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,CM | n=2 OID:v2,OID · merge,not-written · B re-sent, lands on A: A takes B's body |
| `food v1 idf-split-written` | 200 [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,CM | n=1 OID:v2 · merge · B's own write matched A by identifier: one record |
| `food v3 idf-split-second` | 200 {..} · n=2 OID,OID:v2 · not-written,replace · srv C=M=,C=M+ | n=2 OID,OID:v2 · not-written,merge · replace -> merge, same target |
| `food v3 idf-split-written` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge · replace -> merge, same target |
| `food ws idf-split-first` | ack [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,CM | n=2 OID:v2,OID · merge,not-written · A re-sent, lands on A |
| `food ws idf-split-second` | ack [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,CM | n=2 OID:v2,OID · merge,not-written · B re-sent, lands on A: A takes B's body |
| `food ws idf-split-written` | ack [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,CM | n=1 OID:v2 · merge · B's own write matched A by identifier: one record |
| `profile inproc idf-split-first` | cb [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,CM | n=2 OID:v2,OID · merge,not-written · A re-sent, lands on A |
| `profile inproc idf-split-second` | cb [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,CM | n=2 OID:v2,OID · merge,not-written · B re-sent, lands on A: A takes B's body |
| `profile inproc idf-split-written` | cb [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,CM | n=1 OID:v2 · merge · B's own write matched A by identifier: one record |
| `profile v1 idf-split-first` | 200 [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,CM | n=2 OID:v2,OID · merge,not-written · A re-sent, lands on A |
| `profile v1 idf-split-second` | 200 [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,CM | n=2 OID:v2,OID · merge,not-written · B re-sent, lands on A: A takes B's body |
| `profile v1 idf-split-written` | 200 [1 _id] · n=3 OID,OID,OID:v2 · not-written,not-written,new · srv C=M=,C=M=,CM | n=1 OID:v2 · merge · B's own write matched A by identifier: one record |
| `profile v3 idf-split-second` | 200 {..} · n=2 OID,OID:v2 · not-written,replace · srv C=M=,C=M+ | n=2 OID,OID:v2 · not-written,merge · replace -> merge, same target |
| `profile v3 idf-split-written` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge · replace -> merge, same target |
| `profile ws idf-split-first` | ack [1 _id] · n=2 OID:v2,OID · replace,not-written · srv C=M+,C=M= | n=2 OID:v2,OID · merge,not-written · A re-sent, lands on A |
| `profile ws idf-split-second` | ack [1 _id] · n=2 OID,OID:v2 · not-written,replace · srv C=M=,C=M+ | n=2 OID:v2,OID · merge,not-written · B re-sent, lands on A: A takes B's body |
| `profile ws idf-split-written` | ack [1 _id] · n=2 OID:v2,OID · replace,not-written · srv C=M+,C=M= | n=1 OID:v2 · merge · B's own write matched A by identifier: one record |
| `settings v3 idf-split-second` | 200 {..} · n=2 OID,OID:v2 · not-written,replace · srv C=M=,C=M+ | n=2 OID,OID:v2 · not-written,merge · replace -> merge, same target |
| `settings v3 idf-split-written` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge · replace -> merge, same target |
| `treatments inproc idf-split-first` | cb [1 _id] · n=2 OID:v2,OID · replace,not-written · srv C=M+,C=M= | n=2 OID:v2,OID · merge,not-written · replace -> merge, same target |
| `treatments inproc idf-split-second` | cb [1 _id] · n=2 OID:v2,OID · replace,not-written · srv C=M+,C=M= | n=2 OID:v2,OID · merge,not-written · replace -> merge, same target |
| `treatments inproc idf-split-written` | cb [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge · replace -> merge, same target |
| `treatments v1 idf-split-first` | 200 [1 _id] · n=2 OID:v2,OID · replace,not-written · srv C=M+,C=M= | n=2 OID:v2,OID · merge,not-written · replace -> merge, same target |
| `treatments v1 idf-split-second` | 200 [1 _id] · n=2 OID:v2,OID · replace,not-written · srv C=M+,C=M= | n=2 OID:v2,OID · merge,not-written · replace -> merge, same target |
| `treatments v1 idf-split-written` | 200 [1 _id] · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge · replace -> merge, same target |
| `treatments v3 idf-split-second` | 200 {..} · n=2 OID,OID:v2 · not-written,replace · srv C=M=,C=M+ | n=2 OID,OID:v2 · not-written,merge · replace -> merge, same target |
| `treatments v3 idf-split-written` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | n=1 OID:v2 · merge · replace -> merge, same target |
| `treatments ws idf-split-first` | ack [1 _id] · n=2 OID,OID · not-written,not-written · srv C=M+,C=M= | n=2 OID:v2,OID · merge,not-written · A re-sent, lands on A |
| `treatments ws idf-split-second` | ack [1 _id] · n=2 OID,OID · not-written,not-written · srv C=M=,C=M+ | n=2 OID:v2,OID · merge,not-written · B re-sent, lands on A: A takes B's body |
| `treatments ws idf-split-written` | ack [1 _id] · n=2 OID,OID · not-written,not-written · srv C=M+,C=M= | n=1 OID:v2 · merge · B's own write matched A by identifier: one record |

## (g, not visible) Same matrix values, the reply names another record: 1 cells

| cell | today [M] | predicted [R, prediction] |
|---|---|---|
| `devicestatus ws idf-split-second` | ack [1 _id] · n=2 OID,OID · not-written,not-written · srv C=M=,C=M= | n=2 OID,OID · not-written,not-written · B re-sent, answered with A; nothing written (same matrix values; the reply names A) |

## (h) Unchanged as read, but in question: devicestatus API v3 fallback replace: 12 cells

| cell | today [M] | predicted [R, prediction] |
|---|---|---|
| `devicestatus x inproc x v3 idf-NSCLIENT_ID-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | (see note) |
| `devicestatus x inproc x v3 idf-id-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | (see note) |
| `devicestatus x inproc x v3 idf-syncIdentifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | (see note) |
| `devicestatus x inproc x v3 idf-uuid-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | (see note) |
| `devicestatus x v1 x v3 idf-NSCLIENT_ID-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | (see note) |
| `devicestatus x v1 x v3 idf-id-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | (see note) |
| `devicestatus x v1 x v3 idf-syncIdentifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | (see note) |
| `devicestatus x v1 x v3 idf-uuid-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | (see note) |
| `devicestatus x ws x v3 idf-NSCLIENT_ID-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | (see note) |
| `devicestatus x ws x v3 idf-id-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | (see note) |
| `devicestatus x ws x v3 idf-syncIdentifier-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | (see note) |
| `devicestatus x ws x v3 idf-uuid-same` | 200 {..} · n=1 OID:v2 · replace · srv C=M+ | (see note) |

## Option K: cells whose prediction differs from option M: 12

| cell | predicted, option M | predicted, option K |
|---|---|---|
| `treatments ws idf-identifier-amt` | n=1 OID:v2 · merge | n=1 OID · not-written |
| `treatments ws idf-identifier-same` | n=1 OID:v2 · merge | n=1 OID · not-written · kept by identifier: nothing written (today the similar match wrote created_at, srvModified) |
| `treatments ws idf-identifier-time` | n=1 OID:v2 · merge | n=1 OID · not-written |
| `treatments ws idf-split-first` | n=2 OID:v2,OID · merge,not-written · A re-sent, lands on A | (store and shape as today; `srv` of A goes from `C=M+` to `C=M=`) |
| `treatments ws idf-split-second` | n=2 OID:v2,OID · merge,not-written · B re-sent, lands on A: A takes B's body | n=2 OID,OID · not-written,not-written · B re-sent, answered with A; nothing written (same matrix values; the reply names A) |
| `treatments ws idf-split-written` | n=1 OID:v2 · merge · B's own write matched A by identifier: one record | n=1 OID · not-written · B's own write matched A by identifier: one record |
| `treatments x inproc x ws idf-identifier-same` | n=1 OID:v2 · merge | n=1 OID · not-written · kept by identifier: nothing written (today the similar match wrote created_at, srvModified) |
| `treatments x inproc x ws idf-identifier-time` | n=1 OID:v2 · merge | n=1 OID · not-written |
| `treatments x v1 x ws idf-identifier-same` | n=1 OID:v2 · merge | n=1 OID · not-written · kept by identifier: nothing written (today the similar match wrote created_at, srvModified) |
| `treatments x v1 x ws idf-identifier-time` | n=1 OID:v2 · merge | n=1 OID · not-written |
| `treatments x v3 x ws idf-identifier-same` | n=1 OID:v2 · merge | n=1 OID · not-written · kept by identifier: nothing written (today the similar match wrote created_at, srvModified) |
| `treatments x v3 x ws idf-identifier-time` | n=1 OID:v2 · merge | n=1 OID · not-written |

## UUID_HANDLING off (pin `dev-e1f7ac41-idfirst-uuidoff.json`, 504 cells, entries and treatments)

| group | cells |
|---|---:|
| (b) Identifier now matches where a second record was stored | 14 |
| (c1) Replace becomes merge (same record) | 114 |
| (c2) Kept becomes merge: socket treatments, option M only | 4 |
| (d1) Revived becomes "acknowledged, stays deleted" | 20 |
| (d2) A new record beside a deleted one becomes "acknowledged, stays deleted" | 6 |
| (g) Two stored records share one identifier (the split family, BF-212), pick rule P1 | 16 |

With the flag off, an upper-case UUID `_id` on API v1 and in-process is dropped instead of moved to `identifier` (identity reference §3), so the `idf-uuidid-*` cells there are re-sends with no identity and identifier matching cannot reach them; the 16 cells that differ between the two pins are all of that kind.

