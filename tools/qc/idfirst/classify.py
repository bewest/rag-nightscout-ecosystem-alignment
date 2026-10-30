# classify.py PIN.json -> per-cell prediction under ID-FIRST-MATCH as decided 2026-10-29.
# Every prediction is read-derived ([R, prediction]); today's values are the pin's ([M]).
import json, sys, re, collections

pin = json.load(open(sys.argv[1]))
C = pin['cells']
SOCKET_OPT = sys.argv[2] if len(sys.argv) > 2 else 'M'   # M: socket treatments merge on an identifier match; K: kept

IDF_FIELDS = ['identifier', 'syncIdentifier', 'id', 'uuid', 'NSCLIENT_ID', 'uuidid']
CI = ['syncIdentifier', 'id', 'uuid', 'NSCLIENT_ID']

def parse(key):
    m = re.match(r'^(\w+) x (\w+) x (\w+) (idf-\S+)$', key)
    if m: return m.group(1), m.group(2), m.group(3), m.group(4)
    m = re.match(r'^(\w+) (\w+) (\S+)$', key)
    if m: return m.group(1), m.group(2), m.group(2), m.group(3)
    m = re.match(r'^(\w+) x (\w+) x (\w+)$', key)
    if m: return m.group(1), m.group(2), m.group(3), 'cross'
    raise ValueError(key)

def is_new(key):
    c, a, b, f = parse(key)
    return f.startswith('idf-') or c == 'settings'

# Paths that already match a sent identifier first (today, e1f7ac41 / e8224807).
def id_first_today(c, b):
    if b == 'v3': return True
    if b in ('v1', 'inproc') and c in ('treatments', 'entries', 'devicestatus'): return True
    return False

# Does the re-send through path b carry an identifier, and does it equal the seed's?
def carries_identifier(c, a, b, f):
    if f in ('idf-split-first', 'idf-split-second', 'idf-split-written'): return 'split'
    m = re.match(r'idf-(\w+)-(same|amt|time|plain|identifier)$', f)
    if not m: return None
    kind, v = m.group(1), m.group(2)
    if kind == 'identifier': return 'sent'
    if kind in ('softdel', 'harddel', 'v3del'): return 'sent' if v == 'identifier' else ('computed' if b == 'v3' else None)
    if kind == 'uuidid':
        if b in ('v1', 'inproc') and c in ('entries', 'treatments') and pin.get('uuid_handling') is not False: return 'uuid-moved'  # UUID_HANDLING
        return None
    if kind in CI: return 'computed' if b == 'v3' else None
    return None

def labels(cell):
    return (cell.get('shape') or '').split(',') if cell.get('shape') else []

def store_parts(cell):
    s = cell.get('store') or ''
    m = re.match(r'n=(\d+) (.*)$', s)
    return m.group(2).split(',') if m else []

def split_predict(c, b, f, cell, sh, parts):
    # Pick rule P1: each path keeps today's pick (v1/in-process: the first stored record, A; API v3:
    # sort identifier -1, _id -1, so B); a path that newly matches on identifier picks A as well.
    v = f.split('-')[-1]
    oc = 'ack' if c == 'devicestatus' else ('kept' if (c == 'treatments' and b == 'ws' and SOCKET_OPT == 'K') else 'merge')
    if id_first_today(c, b):
        if c == 'devicestatus': return None
        if c == 'entries' and b != 'v3': return None                     # already merges into A
        if 'replace' in sh: return ('g', cell['store'], ','.join('merge' if l == 'replace' else l for l in sh), 'replace -> merge, same target')
        return None                                                      # v3 split-first: 400 (date of B immutable)
    lab = {'merge': 'merge', 'kept': 'not-written', 'ack': 'not-written'}[oc]
    tag = {'merge': 'OID:v2', 'kept': 'OID', 'ack': 'OID'}[oc]
    if v == 'written':
        return ('g', 'n=1 ' + tag, lab, "B's own write matched A by identifier: one record")
    if v == 'first':
        pred = ('n=2 %s,OID' % tag, lab + ',not-written')
        if (cell['store'], cell['shape']) == pred: return None
        return ('g', pred[0], pred[1], 'A re-sent, lands on A')
    # second: B re-sent, lands on A
    pred = ('n=2 %s,OID' % tag, lab + ',not-written')
    note = "B re-sent, lands on A: A takes B's body" if oc == 'merge' else 'B re-sent, answered with A; nothing written'
    if (cell['store'], cell['shape']) == pred: return ('g-hidden', pred[0], pred[1], note + ' (same matrix values; the reply names A)')
    return ('g', pred[0], pred[1], note)

def predict(key):
    cell = C[key]
    c, a, b, f = parse(key)
    st = cell.get('st', '')
    if st.startswith('n/a') or 'INVALID' in st: return None
    sh = labels(cell); parts = store_parts(cell)
    if not sh or sh == ['none']: return None                  # nothing seeded or refused before storage
    seeded = [i for i, l in enumerate(sh) if l != 'new']
    newi = [i for i, l in enumerate(sh) if l == 'new']
    if f.startswith('idf-split'): return split_predict(c, b, f, cell, sh, parts)
    deleted_form = bool(re.match(r'idf-(softdel|v3del)-', f))
    ident = carries_identifier(c, a, b, f)
    # Does an identifier on b reach the seeded record?
    reach_id = False
    if ident == 'sent': reach_id = True
    elif ident == 'computed': reach_id = (a == 'v3')         # only a v3 seed carries the same computed value
    elif ident == 'uuid-moved': reach_id = True               # identifier, or _id under UUID_HANDLING (today too)
    seed_is_deleted_today = any(':inv' in parts[i] for i in seeded)
    revived_today = deleted_form and seeded and not seed_is_deleted_today
    # outcome on a live match, by collection and path b (the rule table's onMatch after the change)
    def live_outcome():
        if c == 'devicestatus': return 'ack'
        if c == 'treatments' and b == 'ws': return 'merge' if SOCKET_OPT == 'M' else 'kept'
        return 'merge'
    # 1. A soft-deleted seed reached by any key: acknowledged, stays deleted.
    if deleted_form and f.find('harddel') == -1:
        if revived_today:
            return ('d-revived', 'n=1 %s:inv' % parts[seeded[0]].split(':')[0], 'not-written')
        if seed_is_deleted_today and newi:
            # a second record beside the deleted one: does a key on b reach it under the rule?
            plain_key = (b == 'ws' and c in ('treatments', 'devicestatus', 'profile')) or b == 'v3' \
                or (b in ('v1', 'inproc') and c in ('treatments', 'entries'))
            if ident == 'sent' or plain_key:
                return ('d-beside', 'n=1 %s:inv' % parts[seeded[0]].split(':')[0], 'not-written')
            return None
        return None
    # 2. Identifier-first on a path that did not match it first.
    if reach_id and not id_first_today(c, b) and seeded:
        oc = live_outcome()
        base = parts[seeded[0]].split(':')[0]
        if oc == 'merge': pred = ('n=1 %s:v2' % base, 'merge')
        else: pred = ('n=1 %s' % base, 'not-written')
        if newi: return ('b', pred[0], pred[1])
        if sh[seeded[0]] == 'replace' and oc == 'merge': return ('c1', pred[0], pred[1])
        if sh[seeded[0]] == 'not-written' and oc == 'merge': return ('c2', pred[0], pred[1])
        if sh[seeded[0]] == 'not-written' and oc in ('kept', 'ack'):
            return ('a' if c == 'devicestatus' else 'k', pred[0], pred[1], 'match key changes to identifier; values as today' if c == 'devicestatus' else 'kept by identifier: nothing written (today the similar match wrote created_at, srvModified)')
        return ('?', pred[0], pred[1])
    # 3. Today's match, outcome replace -> merge (decision 1), except devicestatus (never merges).
    if seeded and sh[seeded[0]] == 'replace' and c != 'devicestatus':
        return ('c1', cell['store'].replace(parts[seeded[0]], parts[seeded[0]]), ','.join('merge' if l == 'replace' else l for l in sh))
    if seeded and sh[seeded[0]] == 'replace' and c == 'devicestatus':
        return ('ds-replace', None)
    return None

RESEND = ['resend-hex', 'resend-upper', 'resend-oid', 'resend-identity', 'resend-near', 'legacy-lower', 'legacy-upper', 'idread-fail']
def old_a(key):
    cell = C[key]
    if 'shape' in cell: return None
    c, a, b, f = parse(key)
    if f != 'cross' and f not in RESEND: return None
    st = cell.get('st', '')
    if st.startswith('n/a') or st.startswith('400') or 'INVALID' in st: return None
    if c == 'devicestatus': return None
    rep = (b == 'v3') or (b in ('v1', 'inproc') and c in ('treatments', 'food', 'activity')) or (b == 'ws' and c == 'profile')
    if not rep or not re.match(r'n=1 ', cell.get('store') or ''): return None
    return ('a', cell.get('store'), 'replace -> merge of an identical body: no recorded value predicted to change')

rows = []
for key in C:
    p = old_a(key) if not ('shape' in C[key]) else None
    if p: rows.append((p[0], key, C[key], p[1:])); continue
    if not is_new(key): continue
    p = predict(key)
    if p is None: continue
    rows.append((p[0], key, C[key], p[1:]))

order = ['a', 'b', 'c1', 'c2', 'k', 'd-revived', 'd-beside', 'g', 'g-hidden', 'ds-replace', '?']
by = collections.defaultdict(list)
for g, k, cell, pr in rows: by[g].append((k, cell, pr))
print('# option', SOCKET_OPT, '| cells in pin', len(C), '| new', sum(1 for k in C if is_new(k)), '| old', sum(1 for k in C if not is_new(k)))
for g in order:
    if g not in by: continue
    print('\n## group', g, len(by[g]))
    cnt = collections.Counter()
    for k, cell, pr in by[g]:
        c, a, b, f = parse(k)
        cnt[(c, a if a == b else a + '>' + b)] += 1
    print('per collection/path:', ', '.join('%s %s %d' % (c, p, n) for (c, p), n in sorted(cnt.items())))
    for k, cell, pr in sorted(by[g]):
        today = '%s · %s · %s · srv %s' % (re.sub(r'\{.*\}', '{..}', cell.get('st', '')), cell.get('store'), cell.get('shape'), cell.get('srv'))
        pred = ' · '.join(x for x in pr if x) if pr and pr[0] else '(see note)'
        print('- `%s` | %s | %s' % (k, today, pred))
