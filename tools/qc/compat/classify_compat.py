# classify_compat.py BEFORE.json AFTER.json -> rows (list of dicts) for cells that differ outside cache/wire.
# Mechanical, from the two pins only. Groups follow tools/qc/idfirst/classify.py's letters where a cell fits,
# with added groups where none does. Nothing here is read from code; every value is from a pin.
import json, re

RACY = ('cache', 'wire')
PLACEHOLDER_CLASSES = {'undefined', 'null', 'invalid', 'nan', 'unknown', 'empty', 'blank', 'jsonnull', 'number', 'len257', 'idundef'}

GROUPS = {
    'a': '(a) write changes, no stored value changes',
    'b': '(b) second record no longer stored',
    'c1': '(c1) replace -> merge',
    'c2': '(c2) kept -> merge/replace (re-send now written)',
    'c3': '(c3) merge -> replace',
    'c4': '(c4) written -> kept (re-send no longer written)',
    'd1': '(d1) revived -> stays deleted',
    'd2': '(d2) new beside deleted -> stays deleted',
    'd3': '(d3) revived -> new record beside the deleted one',
    'g': '(g) shared identifier pick',
    'f': '(f) format: identifier treated as absent',
    'n': '(n) second record now stored',
    'p': '(p) new profile, identifier dropped',
    'r': '(r) refused (4xx) where it was stored',
    'r0': '(r0) refused, was an error (5xx/err) -> 4xx',
    'e': '(e) error (5xx/err) -> answered',
    'q': '(q) reply only',
    'tt': '(tt) Temporary Target units stamped',
    'bt': '(bt) batch: items stored differently',
    's': '(s) seed now refused (API v3 client _id), re-send lands differently',
    'h': '(h) other',
}


def parse_key(k):
    m = re.match(r'^(\w+) x (\w+) x (\w+)(?: (\S+))?$', k)
    if m:
        return dict(collection=m.group(1), seed_path=m.group(2), resend_path=m.group(3), form=m.group(4) or 'cross', results=False)
    m = re.match(r'^(\w+) (\w+) (\S+)( \+results)?$', k)
    if m:
        return dict(collection=m.group(1), seed_path=m.group(2), resend_path=m.group(2), form=m.group(3), results=bool(m.group(4)))
    raise ValueError(k)


def rc(st):
    s = st or ''
    if s.startswith('n/a'): return 'na'
    if 'INVALID' in s: return 'invalid'
    if re.match(r'^5\d\d|^err|^NO-ACK', s): return 'failed'
    if re.match(r'^4\d\d', s): return 'refused'
    if s.startswith('ack {') and 'success' not in s: return 'refused'
    return 'ok'


def store(s):
    s = s or ''
    if s in ('', 'none', None): return []
    m = re.match(r'n=(\d+) (.*)$', s)
    return m.group(2).split(',') if m else []


def live(labels): return [l for l in labels if ':inv' not in l]
def dead(labels): return [l for l in labels if ':inv' in l]


def diff_fields(a, b):
    return [f for f in sorted(set(a) | set(b)) if a.get(f) != b.get(f) and f not in RACY]


def classify(k, a, b):
    p = parse_key(k)
    c, f = p['collection'], p['form']
    d = diff_fields(a, b)
    ra, rb = rc(a.get('st')), rc(b.get('st'))
    sa, sb = store(a.get('store')), store(b.get('store'))
    la, lb = live(sa), live(sb)
    sha = (a.get('shape') or '').split(',') if a.get('shape') else []
    shb = (b.get('shape') or '').split(',') if b.get('shape') else []
    ia = (a.get('ident') or '').split(',') if a.get('ident') else []
    ib = (b.get('ident') or '').split(',') if b.get('ident') else []
    value_fields = [x for x in d if x in ('store', 'shape', 'ident', 'storeb', 'tt')]
    m = re.match(r'idfmt-(\w+)-(time|single|twoapp)$', f)
    fmt_cls = m.group(1) if m else None
    deleted_form = bool(re.match(r'idf-(softdel|v3del|harddel)-', f)) or f == 'batch-deleted'

    # 0. the seed itself is now refused (the cell then measures a different situation)
    if rc(a.get('seed')) == 'ok' and rc(b.get('seed')) == 'refused':
        if len(lb) > len(la): eff = 'new-record'
        elif len(lb) < len(la): eff = 'refused'
        else: eff = 'other'
        return 's', eff
    if rc(a.get('seed')) == 'failed' and rc(b.get('seed')) == 'ok':
        return 'e', ('new-record' if len(lb) > len(la) else 'other')
    # 0c. profile at another startDate: a new profile, the copied identifier dropped (slice 6 line 90 + C)
    if c == 'profile' and len(la) == len(lb) and len(ia) == 2 and ia == ['kept', 'kept'] and ib == ['kept', 'absent'] \
            and fmt_cls not in PLACEHOLDER_CLASSES:
        return 'p', 'field-dropped'
    # 1. identifier format (slice 2 territory): an invalid or placeholder identifier
    if fmt_cls in PLACEHOLDER_CLASSES or f == 'batch-placeholder-identifier':
        if ra == 'refused' and rb == 'ok': eff = 'new-record'
        elif len(lb) > len(la): eff = 'new-record'
        elif len(lb) < len(la): eff = 'duplicate-avoided'
        elif set(d) <= {'ident'}: eff = 'field-dropped'
        elif rb == 'refused' and ra != 'refused': eff = 'refused'
        else: eff = 'other'
        return 'f', eff
    # 2. shared identifier (split family)
    if f.startswith('idf-split'):
        return 'g', ('duplicate-avoided' if len(lb) < len(la) else 'other')
    # 3. reply class changes
    if ra == 'failed' and rb == 'refused':
        return 'r0', ('refused' if len(lb) < len(la) else 'reply-only')
    if ra == 'failed' and rb == 'ok':
        if len(lb) > len(la): return 'e', 'new-record'
        return 'e', ('reply-only' if not value_fields else 'other')
    if rb == 'refused' and ra == 'ok':
        return 'r', 'refused'
    # 4. deleted-record forms
    if deleted_form and sa:
        seed_a = sa[0]; seed_b = sb[0] if sb else ''
        revived_a = ':inv' not in seed_a
        beside_a = (':inv' in seed_a) and len(la) > 0
        stays_b = (':inv' in seed_b) and len(lb) == 0
        if revived_a and stays_b: return 'd1', 'stays-deleted'
        if beside_a and stays_b: return 'd2', 'stays-deleted'
        if revived_a and ':inv' in seed_b and len(lb) > 0: return 'd3', 'new-record'
    # 5. batch cells
    if f.startswith('batch-'):
        if len(lb) < len(la): return 'b', 'duplicate-avoided'
        if len(lb) > len(la): return 'bt', 'new-record'
        if value_fields: return 'bt', 'other'
        if set(d) <= {'st', 'seed', 'slots', 'len', 'warn', 'items', 'body'}: return 'q', 'reply-only'
        return 'a', 'no-visible-change'
    # 6. record count
    if len(lb) < len(la) and 'new' in sha:
        return 'b', 'duplicate-avoided'
    if len(lb) < len(la):
        return 'b', 'duplicate-avoided'
    if len(lb) > len(la):
        if c == 'profile' and ib and 'absent' in ib and 'absent' not in ia:
            return 'p', 'new-record'
        return 'n', 'new-record'
    # 7. same count: what the re-send did to the seeded record
    if sha and shb:
        x, y = sha[0], shb[0]
        if x == 'replace' and y == 'merge': return 'c1', 'field-kept'
        if x == 'not-written' and y == 'merge': return 'c2', 'other'
        if x == 'not-written' and y == 'replace': return 'c2', 'field-dropped'
        if x == 'merge' and y == 'replace': return 'c3', 'field-dropped'
        if x in ('merge', 'replace') and y == 'not-written': return 'c4', 'other'
    if 'tt' in d:
        return 'tt', 'other'
    if set(d) <= {'ident'}:
        return 'f', 'field-dropped'
    if set(d) <= {'st', 'seed', 'slots', 'len', 'warn', 'items', 'body', 'inj'}:
        return 'q', 'reply-only'
    if set(d) <= {'st', 'seed', 'srv', 'hist', 'ev', 'v1read', 'inj', 'writes', 'len', 'slots'} and not value_fields:
        return 'a', 'no-visible-change'
    return 'h', 'other'


def rows(A, B):
    out = []
    for k in A['cells']:
        a, b = A['cells'][k], B['cells'].get(k)
        if b is None: continue
        d = diff_fields(a, b)
        if not d: continue
        g, eff = classify(k, a, b)
        r = dict(cell=k, **parse_key(k))
        r['diff_fields'] = d
        r['before'] = {x: a.get(x) for x in d}
        r['after'] = {x: b.get(x) for x in d}
        r['group'] = g
        r['group_label'] = GROUPS[g]
        r['data_effect'] = eff
        out.append(r)
    return out
