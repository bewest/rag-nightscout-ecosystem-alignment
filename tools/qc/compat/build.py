# build.py: classify every cell that differs between the before and after trees, attribute
# each to the bisect step that moved it, and join the client catalogue.
#
#   python3 tools/qc/compat/build.py --config ANALYSIS.json --groups GROUPS.yaml \
#       --bisect DIR [--run2 v1509=PIN --run2 dev=PIN --run2 8879=PIN] [--out DIR] [--all]
#
# Writes diff-cells.json (always) and, with --all, clients.json and summary.json into --out
# (default: the analysis file's folder). Inputs, all named in ANALYSIS.json or on the command line:
#   trees.<key>.run1     the matrix pin of each tree (v1509 before, dev middle, 8879 after)
#   --run2 KEY=PIN       a second run of a tree; cells that differ between a tree's two runs
#                        (outside cache/wire) are reported as flaky. Without it: not checked.
#   chain                the bisect chain, [key, label, cause]; key is a tree key or a commit
#                        whose pin is DIR/<commit>.json (tools/qc/compat/lane.sh writes them)
#   predictions          the per-slice prediction files, written before each slice's code
#   client_shapes        the client catalogue (read from each client's code, file:line)
#   GROUPS.yaml          group metadata; this script reads only `guard`
# Every row is derived from pins; causes from the measured bisect chain; the slice inside the
# slices-1-to-4 block from the predictions.
import argparse, json, os, re, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from classify_compat import rows, diff_fields, parse_key, GROUPS
import predmap

ap = argparse.ArgumentParser()
ap.add_argument('--config', required=True)
ap.add_argument('--groups', required=True)
ap.add_argument('--bisect', required=True, help='folder of <commit>.json pins for the chain')
ap.add_argument('--run2', action='append', default=[], metavar='KEY=PIN')
ap.add_argument('--out', default=None)
ap.add_argument('--all', action='store_true')
ARGS = ap.parse_args()
CFG = json.load(open(ARGS.config))
BASE = os.path.dirname(os.path.abspath(ARGS.config))
OUT = os.path.abspath(ARGS.out) if ARGS.out else BASE
C = lambda p: os.path.join(BASE, p)
L = lambda f: json.load(open(f))
import yaml  # noqa: E402
GMETA = yaml.safe_load(open(ARGS.groups))['groups']
RUN2 = dict(x.split('=', 1) for x in ARGS.run2)
T = CFG['trees']
A1, D1, B1 = (L(C(T[k]['run1'])) for k in ('v1509', 'dev', '8879'))
A2, D2, B2 = (L(RUN2[k]) if k in RUN2 else None for k in ('v1509', 'dev', '8879'))

# ---- repeatability: cells that differ between a tree's own two runs (outside cache/wire) are flaky
flaky = {}
racy_self = {}
for name, x, y in ((T['v1509']['name'], A1, A2), (T['dev']['name'], D1, D2), (T['8879']['name'], B1, B2)):
    if y is None:
        flaky[name] = None; racy_self[name] = None; continue
    fl, rc_ = [], 0
    for k in x['cells']:
        d = diff_fields(x['cells'][k], y['cells'].get(k, {}))
        if d: fl.append(k)
        elif x['cells'][k] != y['cells'].get(k): rc_ += 1
    flaky[name] = fl
    racy_self[name] = rc_
FLAKY = set(k for v in flaky.values() if v for k in v)

# ---- the bisect chain (first-parent dev merges, then #8879's slice commits)
CHAIN = [tuple(x) for x in CFG['chain']]
PINS = {}
for key, _, _ in CHAIN:
    f = C(T[key]['run1']) if key in T else os.path.join(ARGS.bisect, key + '.json')
    PINS[key] = L(f) if os.path.exists(f) else None
missing = [k for k, v in PINS.items() if v is None]
if missing: print('missing bisect pins:', missing)

PRED, PRULE = predmap.load([(lab, C(p)) for lab, p in CFG['predictions']])
_sba = CFG.get('slice_batch_attribution')
SLICE_BATCH = L(C(_sba)) if _sba and os.path.exists(C(_sba)) else {}
SLICE2_HEAD_MEASURED = set(CFG.get('slice2_head_measured', []))
SLICE_ORDER = CFG['slice_order']


def causes(k):
    out = []
    for i in range(1, len(CHAIN)):
        a, b = PINS.get(CHAIN[i - 1][0]), PINS.get(CHAIN[i][0])
        if a is None or b is None: out.append(('?', CHAIN[i][0], 'pin missing')); continue
        ca, cb = a['cells'].get(k), b['cells'].get(k)
        if ca is None or cb is None: continue
        if diff_fields(ca, cb):
            lab = CHAIN[i][2]
            if lab == 'SLICES-1-4':
                pr = [s for s in PRED.get(k, []) if s in SLICE_ORDER]
                if pr: lab = ' + '.join('ID-FIRST-MATCH ' + s for s in pr)
                elif k in SLICE_BATCH and SLICE_BATCH[k]['steps'] and SLICE_BATCH[k]['end_equals_5bf94c8b']:
                    lab = ' + '.join('ID-FIRST-MATCH ' + s for s in SLICE_BATCH[k]['steps']) + ' [measured per slice, --batch-only at the slice commits; batch forms post-date the prediction]'
                elif k in SLICE2_HEAD_MEASURED:
                    lab = 'ID-FIRST-MATCH slice 2 [measured in slice 2\'s own head pin idf-s2/dev-521e7583-idf-s2.json (err -> cb); not in its prediction text]'
                else: lab = 'UNEXPLAINED: moved in slices 1-4 block (5bf94c8b), no slice prediction lists it'
            elif lab in ('slice 6', 'slice 6a', 'B+C'):
                pr = PRED.get(k, [])
                lab = ('ID-FIRST-MATCH ' + lab if lab != 'B+C' else 'decisions B+C (slice 6, 2026-10-31)') + ('' if lab in pr else ' [measured; not in that slice\'s prediction]')
            out.append((CHAIN[i - 1][0], CHAIN[i][0], lab))
    return out


GUARD = {g: m['guard'] for g, m in GMETA.items()}
NOUN = {'treatments': 'treatment', 'entries': 'glucose reading', 'devicestatus': 'device status', 'profile': 'profile',
        'food': 'food item', 'activity': 'activity record', 'settings': 'settings document'}


def consequence(r):
    g, c, eff = r['group'], r['collection'], r['data_effect']
    n = NOUN.get(c, c)
    if g == 'f':
        if eff == 'new-record': return 'two apps sharing a placeholder identifier get separate records (before: one overwrote the other, or v3 refused)'
        if eff == 'field-dropped': return 'the placeholder identifier value is not stored; a client reading it back finds none'
        if eff == 'duplicate-avoided': return 'a re-send with a placeholder no longer adds a second ' + n
        if eff == 'refused': return 'a write with this identifier is refused where it was stored'
        return 'identifier format handling changed'
    return {
        'b': 'a re-sent ' + n + ' updates the stored one instead of adding a duplicate',
        'c1': 'a field the client left out of a re-send is kept' + (' (a cleared field stays visible)' if c in ('profile', 'devicestatus', 'food') else ''),
        'c2': 'a re-send now changes the stored ' + n + ' where it was ignored' + (' and fields it left out are dropped' if eff == 'field-dropped' else ''),
        'c3': 'a field the client left out of a re-send is dropped',
        'c4': 'a re-send no longer changes the stored ' + n,
        'd1': 'a re-sent ' + n + ' after a delete stays hidden (before: it reappeared)',
        'd2': 'a re-sent ' + n + ' after a delete is not stored (before: a new copy appeared)',
        'd3': 'a re-sent ' + n + ' after a delete appears as a new record (before: the deleted one was revived)',
        'g': 'of two records sharing an identifier, a different one is updated',
        'n': 'a re-send now stores a second ' + n + ' (possible duplicate)',
        'p': 'a profile create carrying a stored identifier but another startDate is kept as a new profile (as before), stored without the copied identifier',
        'r': 'a write that was stored is refused (4xx); the ' + n + ' is not stored unless the client handles it',
        'r0': 'an error reply (5xx) becomes a 4xx refusal',
        'e': 'an error reply becomes success' + (' and the ' + n + ' is stored' if eff in ('new-record', 'other') else ''),
        'q': 'only the reply differs (ids, slots or status)',
        'tt': 'a Temporary Target is stored labelled mg/dl (BF-194)',
        'bt': 'items in a batch are stored differently (count or per-item outcome)',
        's': 'the seed write (API v3 with a client _id) is now refused, so the re-send lands differently',
        'a': 'stored values unchanged; server dates, history or events differ',
        'h': 'other',
    }[g]


EFFECT_RANK = {'stays-deleted': 9, 'new-record': 8, 'field-dropped': 8, 'refused': 7, 'other': 6, 'field-kept': 5,
               'duplicate-avoided': 4, 'reply-only': 2, 'no-visible-change': 1}


INVALID_V1509 = list(CFG['set_aside_on_v1509']['cells'])


def main():
    R = [r for r in rows(A1, B1) if r['cell'] not in INVALID_V1509]
    devset = set(k for k in A1['cells'] if diff_fields(A1['cells'][k], D1['cells'][k])) - set(INVALID_V1509)
    oursset = set(k for k in D1['cells'] if diff_fields(D1['cells'][k], B1['cells'][k]))
    for r in R:
        k = r['cell']
        r['in_v1509_to_dev'] = k in devset
        r['in_dev_to_8879'] = k in oursset
        r['flaky'] = k in FLAKY
        cs = causes(k)
        r['cause_steps'] = [{'from': a, 'to': b, 'cause': c} for a, b, c in cs]
        labs = [c for _, _, c in cs]
        r['cause'] = '; '.join(dict.fromkeys(labs)) if labs else 'UNEXPLAINED: no bisect step moves it'
        r['unexplained'] = (not labs) or any(l.startswith('UNEXPLAINED') for l in labs)
        r['predicted_rules'] = PRULE.get(k, [])
        r['guard'] = GUARD[r['group']]
        r['consequence'] = consequence(r)
        r['re_send_path'] = r['seed_path'] + ('>' + r['resend_path'] if r['seed_path'] != r['resend_path'] else '')
    json.dump(R, open(os.path.join(OUT, 'diff-cells.json'), 'w'), indent=1)
    return R, devset, oursset


if __name__ == '__main__':
    R, devset, oursset = main()
    print('rows', len(R), 'unexplained', sum(r['unexplained'] for r in R), 'flaky', {k: (None if v is None else len(v)) for k, v in flaky.items()})


# ---------------- client join ----------------
def client_fields(c):
    """identity fields a client row sends on create/re-send, from the catalogue's text."""
    s = set()
    si = str(c['sends_identifier']).lower()
    if si not in ('false', 'no') and not si.startswith('no') and 'only on patch' not in si: s.add('identifier')
    if 'only on patch' in si: s.add('identifier-patch')
    sid = str(c['sends__id']).lower()
    if sid.startswith('none'): sid = ''   # no _id on create (an edit may address the stored _id)
    if 'uuid' in sid and 'objectid' not in sid: s.add('_id-uuid')
    if 'objectid-hex' in sid or '24-hex' in sid or "source's 24-hex" in sid or 'source _id' in sid: s.add('_id-hex')
    if 'alphanumeric' in sid or 'random 24-char' in sid: s.add('_id-other')
    if str(c['sends_syncIdentifier']).lower() not in ('false', 'no'): s.add('syncIdentifier')
    o = str(c['other_id_fields'])
    if re.search(r'\bid \(', o) or o.startswith('id') or ', id' in o: s.add('id')
    if 'uuid' in o: s.add('uuid')
    return s


def resends_after_delete(c):
    t = str(c['resends_after_delete']).lower()
    if t.startswith('yes') or 'deletes its own and re-posts' in t or 're-create' in t and not t.startswith('no'): return 'yes'
    if t.startswith('unknown') or 'possible' in t or 'not traced' in t or 'edit of a stale' in t: return 'unknown'
    return 'no'


def needed(form, coll):
    """(identity field the cell's re-send carries, needs a delete first, other condition) by form."""
    m = re.match(r'idf-(identifier|syncIdentifier|id|uuid|NSCLIENT_ID|uuidid)-(same|amt|time)$', form)
    if m: return ({'uuidid': '_id-uuid'}.get(m.group(1), m.group(1)), False, None)
    m = re.match(r'idf-(softdel|harddel|v3del)-(plain|identifier)$', form)
    if m: return ('identifier' if m.group(2) == 'identifier' else 'plain', True, None)
    if form.startswith('idf-split'): return ('split', False, None)
    m = re.match(r'idfmt-(\w+)-(time|single|twoapp)$', form)
    if m:
        k = m.group(1)
        if k in ('undefined', 'null', 'invalid', 'nan', 'unknown', 'empty', 'blank', 'jsonnull', 'number', 'len257'): return ('identifier-placeholder', False, k)
        if k == 'idundef': return ('_id-placeholder', False, k)
        return ('identifier', False, k)
    if form in ('resend-hex', 'resend-upper', 'resend-oid', 'legacy-lower', 'legacy-upper', 'idread-fail', 'update-twin'): return ('_id-hex', False, None)
    if form in ('resend-identity', 'resend-near', 'cross', 'create'): return ('plain', False, None)
    if form.startswith('tt-'): return ('tt', False, None)
    if form.startswith('batch-'):
        # every batch form sends an array of several records in one request
        return {'batch-repeat-identifier': ('identifier', False, 'batch'), 'batch-repeat-stored': ('identifier', False, 'batch'),
                'batch-deleted': ('identifier', True, 'batch'), 'batch-dupkey-mid': ('identifier', False, 'batch race'),
                'batch-placeholder-identifier': ('identifier-placeholder', False, 'batch'),
                'batch-mixed-ident': ('identifier-placeholder', False, 'batch, non-string identifier'),
                'batch-mixed-oid': ('_id-other', False, 'batch'), 'batch-taken-id': ('_id-hex', False, 'batch'),
                'batch-taken-all': ('_id-hex', False, 'batch'), 'batch-mixed-tt': ('tt', False, 'batch'),
                'batch-prebolus': ('prebolus', False, 'batch'), 'batch-storage-fail-mid': ('plain', False, 'batch, storage failure'),
                'batch-profile-permission': ('profile-permission', False, 'batch')}.get(form, ('?', False, 'batch'))
    if form in ('update', 'update-put'): return ('edit', False, None)
    if form in ('softdelete', 'harddelete', 'harddelete-custom', 'harddelete-num'): return ('delete', False, None)
    return ('?', False, None)


def join_clients(R):
    CL = [c for c in L(C(CFG['client_shapes'])) if c['path'] not in ('none',)]
    combos = collections.defaultdict(list)
    for r in R: combos[(r['group'], r['collection'], r['resend_path'])].append(r)
    out = []
    for (g, coll, path), cells in sorted(combos.items()):
        forms = collections.Counter(needed(r['form'], coll)[0] for r in cells)
        for c in CL:
            if c['collection'] != coll or c['path'] != path: continue
            cf = client_fields(c)
            matched = []
            for r in cells:
                fld, needs_del, cond = needed(r['form'], coll)
                rk = str(c.get('record_kind') or '')
                ok = False
                if fld == 'plain': ok = not (cf - {'identifier-patch'})   # time key only: the client sends no identity field
                elif fld == 'identifier': ok = 'identifier' in cf
                elif fld == 'identifier-placeholder': ok = False
                elif fld == '_id-placeholder': ok = False
                elif fld == '_id-hex': ok = '_id-hex' in cf
                elif fld == '_id-uuid': ok = '_id-uuid' in cf
                elif fld in ('syncIdentifier', 'id', 'uuid'): ok = fld in cf
                elif fld == 'split': ok = 'split' in rk or 'chart' in rk
                elif fld == 'tt': ok = bool(re.search(r'\bTT\b|Temporary Target|careportal', json.dumps(c)))
                elif fld == 'prebolus': ok = bool(re.search(r'preBolus|bolus wizard', json.dumps(c), re.I))
                elif fld == '_id-other': ok = '_id-other' in cf
                elif fld == 'edit': ok = str(c['edit_method']) != 'none'
                elif fld == 'delete': ok = str(c['delete_method']) not in ('none', 'None', 'n/a')
                if ok and needs_del and resends_after_delete(c) == 'no': ok = False
                if ok: matched.append(r)
            if not matched: continue
            fl = sorted(set(needed(r['form'], coll)[0] for r in matched))
            dl = any(needed(r['form'], coll)[1] for r in matched)
            out.append(dict(
                group=g, group_label=GROUPS[g], collection=coll, path=path, client=c['client'],
                record_kind=c.get('record_kind'), client_commit=c.get('client_commit'),
                cells_matched=len(matched), cells_in_combo=len(cells),
                sends_shape='; '.join(x for x in [
                    'path ' + path,
                    'identity sent: ' + (', '.join(sorted(cf)) or 'none (time key only)'),
                    'cells need: ' + ', '.join(fl),
                    ('re-sends after delete: ' + resends_after_delete(c) + ' (' + str(c['resends_after_delete'])[:120] + ')') if dl else None,
                    'whole-record re-send: ' + str(c['resends_whole_record'])[:120]] if x),
                tier=c['tier'] + ('' if not dl or resends_after_delete(c) == 'yes' else ' (re-send after delete: ' + resends_after_delete(c) + ')'),
                source=c['source'],
                consequence=matched[0]['consequence'],
                join_basis='matched by collection, path and the identity field each cell re-sends (read from the client catalogue at the clone commit); a plain/time-key cell matches only clients that send no identity field; a client whose identity field has no matrix form (e.g. syncIdentifier after a delete) is not matched',
            ))
    return out


def summary(R, devset, oursset, clients):
    by = lambda f: dict(collections.Counter(f(r) for r in R).most_common())
    heat = collections.defaultdict(int)
    for r in R: heat[(r['group'], r['collection'], r['resend_path'])] += 1
    unexp = [dict(cell=r['cell'], group=r['group'], cause=r['cause'], before=r['before'], after=r['after']) for r in R if r['unexplained']]
    ncl = collections.defaultdict(set)
    for c in clients: ncl[(c['group'], c['collection'], c['path'])].add(c['client'])
    ranking = []
    for (g, coll, path), n in heat.items():
        effs = collections.Counter(r['data_effect'] for r in R if (r['group'], r['collection'], r['resend_path']) == (g, coll, path))
        worst = max(effs, key=lambda e: EFFECT_RANK[e])
        ranking.append(dict(group=g, collection=coll, path=path, cells=n, worst_effect=worst, effect_rank=EFFECT_RANK[worst],
                            clients=sorted(ncl[(g, coll, path)]), n_clients=len(ncl[(g, coll, path)]),
                            score=EFFECT_RANK[worst] * len(ncl[(g, coll, path)])))
    ranking.sort(key=lambda x: (-x['score'], -x['effect_rank'], -x['cells']))
    allcells = len(A1['cells'])
    invalid = {n: sum(1 for c in x['cells'].values() if 'INVALID' in str(c.get('st'))) for n, x in ((T['v1509']['name'], A1), (T['dev']['name'], D1), (T['8879']['name'], B1))}
    racy_v_b = sum(1 for k in A1['cells'] if not diff_fields(A1['cells'][k], B1['cells'][k]) and A1['cells'][k] != B1['cells'][k])
    s = dict(
        trees={T['v1509']['name']: A1['head'], T['dev']['name']: D1['head'], T['8879']['name']: B1['head']},
        node=B1['node'], mongod=B1['mongod'],
        settings=CFG['settings'],
        totals=dict(cells_per_tree=allcells, invalid_liveness=invalid,
                    harness_set_aside=dict(cells=INVALID_V1509, reason=CFG['set_aside_on_v1509']['reason']),
                    flaky_outside_cache_wire={k: (None if v is None else len(v)) for k, v in flaky.items()}, flaky_cells=flaky,
                    cache_wire_only_between_own_runs=racy_self,
                    cache_wire_only_v1509_to_8879=racy_v_b,
                    differing_cells_v1509_to_8879=len(R), differing_v1509_to_dev=len(devset), differing_dev_to_8879=len(oursset),
                    in_both_steps=len(devset & oursset), unexplained=len(unexp)),
        split=dict(v1509_to_dev_only=sum(1 for r in R if r['in_v1509_to_dev'] and not r['in_dev_to_8879']),
                   dev_to_8879_only=sum(1 for r in R if r['in_dev_to_8879'] and not r['in_v1509_to_dev']),
                   both=sum(1 for r in R if r['in_dev_to_8879'] and r['in_v1509_to_dev']),
                   neither_but_differs=sum(1 for r in R if not r['in_dev_to_8879'] and not r['in_v1509_to_dev']),
                   by_group_v1509_to_dev=dict(collections.Counter(r['group'] for r in R if r['in_v1509_to_dev'] and not r['in_dev_to_8879'])),
                   by_group_dev_to_8879=dict(collections.Counter(r['group'] for r in R if r['in_dev_to_8879']))),
        groups=GROUPS,
        by_group=by(lambda r: r['group']), by_data_effect=by(lambda r: r['data_effect']),
        by_collection=by(lambda r: r['collection']), by_path=by(lambda r: r['re_send_path']),
        by_resend_path=by(lambda r: r['resend_path']),
        by_cause=by(lambda r: r['cause']), by_guard=by(lambda r: r['guard']),
        by_form_family=by(lambda r: (r['form'].split('-')[0] if r['form'].startswith(('idf', 'idfmt', 'batch', 'tt')) else 'earlier')),
        heatmap=dict(rows=sorted(set(g for g, _, _ in heat)), cols=sorted(set((c, p) for _, c, p in heat)),
                     cells=[dict(group=g, collection=c, path=p, count=n) for (g, c, p), n in sorted(heat.items())]),
        ranking=ranking,
        unexplained=unexp,
    )
    json.dump(s, open(os.path.join(OUT, 'summary.json'), 'w'), indent=1)
    return s


if __name__ == '__main__' and ARGS.all:
    R, devset, oursset = main()
    cl = join_clients(R)
    json.dump(cl, open(os.path.join(OUT, 'clients.json'), 'w'), indent=1)
    s = summary(R, devset, oursset, cl)
    print(json.dumps(s['totals'], indent=1)[:3000])
