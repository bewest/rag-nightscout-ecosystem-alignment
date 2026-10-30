# render.py out-M.txt out-K.txt out-uuidoff-M.txt -> the appendix (markdown)
import sys, re
TITLES = {
 'a': '(a) The write changes, no recorded value is predicted to change',
 'b': '(b) Identifier now matches where a second record was stored',
 'c1': '(c1) Replace becomes merge (same record)',
 'c2': '(c2) Kept becomes merge: socket treatments, option M only',
 'k': '(c2, option K) Kept by identifier instead of the similar match',
 'd-revived': '(d1) Revived becomes "acknowledged, stays deleted"',
 'd-beside': '(d2) A new record beside a deleted one becomes "acknowledged, stays deleted"',
 'g': '(g) Two stored records share one identifier (the split family, BF-212), pick rule P1',
 'g-hidden': '(g, not visible) Same matrix values, the reply names another record',
 'ds-replace': '(h) Unchanged as read, but in question: devicestatus API v3 fallback replace',
}
def parse(path):
    groups, cur = {}, None
    for line in open(path):
        line = line.rstrip('\n')
        m = re.match(r'^## group (\S+) (\d+)$', line)
        if m: cur = m.group(1); groups[cur] = {'n': int(m.group(2)), 'per': '', 'rows': []}; continue
        if cur and line.startswith('per collection/path:'): groups[cur]['per'] = line.split(':', 1)[1].strip()
        elif cur and line.startswith('- `'):
            parts = line[2:].split(' | ')
            groups[cur]['rows'].append(parts)
    return groups
M = parse(sys.argv[1]); K = parse(sys.argv[2]); U = parse(sys.argv[3])
out = []
w = out.append
w('# ID-FIRST-MATCH: cell-by-cell impact (appendix)\n')
w('*Generated 2026-10-29 by `tools/qc/idfirst/classify.py` (its rules are in the note, section 2) and `render.py` from the pin `tools/qc/results/write-contract-matrix/dev-e1f7ac41-idfirst.json` (1,929 cells: 456 earlier, 1,473 new). The design note is [`id-first-match-design-note-2026-10-29.md`](id-first-match-design-note-2026-10-29.md). "Today" columns are **[M]**, the pin. Every "predicted" column is **[R, prediction]**: read from code at crm `e8224807` and the rule in the note §1, not run. The implementation slice measures each one.*\n')
w('Rule options used: socket treatments merge on an identifier match (**option M**, decision 1 as written); shared-identifier pick **P1** (each path keeps today\'s pick; a path new to identifier matching picks the first stored record). Option K (socket treatments keep the stored record on an identifier match) differs only where listed at the end.\n')
w('Format of "today": reply · stored records (`n=`, one label per record: `OID`/`str*` the `_id` form, `:v2` the re-send\'s fields are on it, `:inv` soft-deleted) · `shape` · `srv`. Predicted: stored records · `shape` · note. A reply is predicted unchanged unless the note says otherwise.\n')
w('## Counts\n')
w('| group | cells | per collection / path (`A>B` = seeded through A, re-sent through B) |')
w('|---|---:|---|')
for g in ['a', 'b', 'c1', 'c2', 'd-revived', 'd-beside', 'g', 'g-hidden', 'ds-replace']:
    if g in M: w('| %s | %d | %s |' % (TITLES[g], M[g]['n'], M[g]['per']))
w('')
for g in ['a', 'b', 'c1', 'c2', 'd-revived', 'd-beside', 'g', 'g-hidden', 'ds-replace']:
    if g not in M: continue
    w('## %s: %d cells\n' % (TITLES[g], M[g]['n']))
    w('| cell | today [M] | predicted [R, prediction] |')
    w('|---|---|---|')
    for r in M[g]['rows']:
        w('| %s | %s | %s |' % (r[0], r[1], r[2] if len(r) > 2 else ''))
    w('')
# option K differences
mk = {r[0]: r for g in M.values() for r in g['rows']}
kk = {r[0]: r for g in K.values() for r in g['rows']}
diff = sorted(k for k in set(mk) | set(kk) if (mk.get(k) or [None]*3)[2:] != (kk.get(k) or [None]*3)[2:])
w('## Option K: cells whose prediction differs from option M: %d\n' % len(diff))
w('| cell | predicted, option M | predicted, option K |')
w('|---|---|---|')
for k in diff:
    w('| %s | %s | %s |' % (k, (mk.get(k) or ['', '', '(unchanged)'])[2], (kk.get(k) or ['', '', '(store and shape as today; `srv` of A goes from `C=M+` to `C=M=`)'])[2]))
w('')
w('## UUID_HANDLING off (pin `dev-e1f7ac41-idfirst-uuidoff.json`, 504 cells, entries and treatments)\n')
w('| group | cells |')
w('|---|---:|')
for g in ['a', 'b', 'c1', 'c2', 'd-revived', 'd-beside', 'g', 'g-hidden', 'ds-replace']:
    if g in U: w('| %s | %d |' % (TITLES[g], U[g]['n']))
w('\nWith the flag off, an upper-case UUID `_id` on API v1 and in-process is dropped instead of moved to `identifier` (identity reference §3), so the `idf-uuidid-*` cells there are re-sends with no identity and identifier matching cannot reach them; the 16 cells that differ between the two pins are all of that kind.\n')
open(sys.argv[4], 'w').write('\n'.join(out) + '\n')
