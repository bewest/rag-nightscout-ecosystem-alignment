"""ID-DUP-MEASURE: duplicate `identifier` values in the ns-data corpus (12 sites).

Aggregate output only: counts per pseudonymous site label (a..k, L), collection
and client class. No identifier values, record contents, names or hosts are
printed. Client classes reuse the write-contract corpus note's classifiers
(../write-contract-null-and-keys-2026-10-12/analyze.py), app-level fields only.

Usage: python3 -I iddup.py            # measure
       python3 -I iddup.py --control  # plant known duplicates in site a; print deltas
       python3 -I iddup.py --planted  # the planted run's full report (the queue gate's control)
"""
import json, collections, sys, copy
from datetime import datetime

BASE = '/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/ns-data/'
SITES = [(c, f'patients/{c}/raw') for c in 'abcdefghijk'] + [('L', 'live-recent-180-json/live-recent')]
COLS = ['entries', 'treatments', 'devicestatus', 'profile', 'food']
VOLATILE = {'_id', 'srvModified', 'srvCreated', 'mills', 'utcOffset'}


def cls_treat(x):
    v = x.get('enteredBy')
    if v is None: return 'no-enteredBy'
    v = str(v)
    if v.startswith('loop://') or v == 'Loop' or v.startswith('Loop (via remote'): return 'Loop'
    if v == 'Trio': return 'Trio'
    if v.startswith('openaps://AndroidAPS') or v == 'AndroidAPS': return 'AndroidAPS'
    if v.startswith('openaps://'): return 'openaps'
    if v == 'xDrip4iOS': return 'xDrip4iOS'
    if v.lower().startswith('xdrip'): return 'xDrip+'
    return 'other free-text'


def cls_ds(x):
    v = x.get('device')
    if v is None: return 'no-device'
    v = str(v)
    if v.startswith('loop://'): return 'Loop'
    if v == 'Trio': return 'Trio'
    if v.startswith('openaps://AndroidAPS'): return 'AndroidAPS'
    if v.startswith('openaps://'): return 'openaps'
    if 'uploader' in x: return 'uploader-only (phone-model device)'
    return 'other'


def cls_entry(x):
    v = x.get('device')
    if v is None: return 'no-device'
    v = str(v)
    if v.startswith('Dexcom G6 ') or v.startswith('Dexcom G7 '): return 'CGM manager (Loop/Trio)'
    if v.startswith('com.dexcom.'): return 'Dexcom app'
    if 'trio' in v.lower(): return 'Trio'
    if v == 'share2': return 'share2'
    if 'LibreLinkUp' in v: return 'LibreLinkUp'
    if v.startswith('xDrip-'): return 'xDrip+'
    if v.startswith('redacted'): return 'redacted device'
    if v.startswith('loop://'): return 'Loop'
    if v.startswith('openaps://'): return 'openaps/AndroidAPS'
    return 'other'


def cls_profile(x):
    return cls_treat(x) if x.get('enteredBy') is not None else 'no-enteredBy'


CLS = {'treatments': cls_treat, 'devicestatus': cls_ds, 'entries': cls_entry,
       'profile': cls_profile, 'food': lambda x: 'food'}


def instant(v):
    if isinstance(v, (int, float)): return int(v)
    if isinstance(v, str):
        try: return int(datetime.fromisoformat(v.replace('Z', '+00:00')).timestamp() * 1000)
        except Exception: return v
    return repr(v)


def natkey(col, x):
    # The natural keys the write-contract spec decided (Q3) plus treatments'
    # fallback key (created_at + eventType).
    if col == 'entries': return (x.get('date'), x.get('type'))
    if col == 'treatments': return (instant(x.get('created_at')), x.get('eventType'))
    if col == 'devicestatus': return (instant(x.get('created_at')), x.get('device'))
    if col == 'profile': return (instant(x.get('created_at')),)
    return (x.get('name'), x.get('category'))


def idclass(x):
    if 'identifier' not in x: return 'absent'
    v = x['identifier']
    if v is None: return 'null'
    if isinstance(v, str): return 'empty-string' if v == '' else 'non-empty string'
    return 'non-string (' + type(v).__name__ + ')'


def body(x):
    return json.dumps({k: v for k, v in x.items() if k not in VOLATILE}, sort_keys=True, default=str)


def load_file(path, col):
    try: d = json.load(open(BASE + path + '/' + col + '.json'))
    except FileNotFoundError: return None
    if isinstance(d, dict): d = [d]
    return d


def run(load):
    R = collections.defaultdict(collections.Counter)
    present = set()
    for site, path in SITES:
        for col in COLS:
            docs = load(path, col)
            if docs is None: continue
            present.add((site, col))
            R['docs'][(site, col)] += len(docs)
            groups = collections.defaultdict(list)
            sgroups = collections.defaultdict(list)
            for x in docs:
                c = CLS[col](x)
                k = idclass(x)
                R['idclass'][(site, col, k)] += 1
                R['idclass_client'][(col, c, k)] += 1
                if k == 'non-empty string':
                    groups[x['identifier']].append(x)
                # secondary: treatments' syncIdentifier (Loop/Trio), the value a client
                # would most likely send as identifier; v1 does not key on it today.
                if col == 'treatments' and isinstance(x.get('syncIdentifier'), str) and x['syncIdentifier']:
                    R['syncid_docs'][(site, c)] += 1
                    sgroups[x['syncIdentifier']].append(x)
            for label, G in (('identifier', groups), ('syncIdentifier', sgroups)):
              for ident, members in G.items():
                if len(members) < 2: continue
                keys = {repr(natkey(col, m)) for m in members}
                bodies = {body(m) for m in members}
                kind = ('same natural key, identical body' if len(keys) == 1 and len(bodies) == 1 else
                        'same natural key, different body' if len(keys) == 1 else
                        'different natural key')
                clients = '+'.join(sorted({CLS[col](m) for m in members}))
                R['dupvals'][(label, site, col)] += 1
                R['dupdocs'][(label, site, col)] += len(members)
                R['dupkind'][(label, site, col, kind, 'values')] += 1
                R['dupkind'][(label, site, col, kind, 'docs')] += len(members)
                R['dupclient'][(label, col, clients, kind, 'values')] += 1
                R['dupclient'][(label, col, clients, kind, 'docs')] += len(members)
                if col == 'treatments':
                    ev = '+'.join(sorted(str(m.get('eventType')) for m in members))
                    t = [instant(m.get('created_at')) for m in members]
                    t = [v for v in t if isinstance(v, int)]
                    sp = (max(t) - min(t)) / 1000 if len(t) == len(members) else None
                    spread = ('unparseable' if sp is None else '0 s' if sp == 0 else '<=60 s' if sp <= 60
                              else '<=1 d' if sp <= 86400 else '>1 d')
                    withid = sum('identifier' in m for m in members)
                    R['dupshape'][(label, site, ev, 'created_at spread ' + spread,
                                   f'{withid} of {len(members)} carry identifier')] += 1
            del docs
    R['present'] = present
    return R


def dump(R, out=sys.stdout):
    out.write('## collections present (site, collection, docs)\n')
    for k in sorted(R['present']): out.write(f"{R['docs'][k]}\t{k[0]}\t{k[1]}\n")
    for name in ['idclass', 'idclass_client', 'dupvals', 'dupdocs', 'dupkind', 'dupclient', 'dupshape', 'syncid_docs']:
        out.write(f'## {name}\n')
        for k, v in sorted(R[name].items(), key=lambda kv: tuple(map(str, kv[0]))):
            out.write(f'{v}\t' + '\t'.join(map(str, k)) + '\n')
    out.write('## partial unique index {identifier: {$type:"string",$gt:""}} builds? (per collection, all sites)\n')
    for col in COLS:
        sites = sorted(s for s, c in R['present'] if c == col)
        if not sites: out.write(f'{col}\tnot in corpus\n'); continue
        bad = sorted(s for s in sites if R['dupvals'][('identifier', s, col)])
        out.write(f"{col}\t{'yes at every site' if not bad else 'no at ' + ','.join(bad)}\t({len(sites)} sites)\n")
    bad = sorted(s for (l, s, c) in R['dupvals'] if l == 'syncIdentifier' and R['dupvals'][(l, s, c)])
    out.write(f"treatments, if syncIdentifier were sent as identifier\t{'yes at every site' if not bad else 'no at ' + ','.join(bad)}\n")


if __name__ == '__main__':
    if '--control' not in sys.argv and '--planted' not in sys.argv:
        dump(run(load_file))
    else:
        # Plant, in site a: (1) two treatments sharing a fresh identifier with the same
        # natural key and identical bodies; (2) two entries sharing one with different
        # natural keys; (3) one devicestatus with identifier "" and one with null;
        # (4) a treatment with a numeric identifier.
        def planted(path, col):
            d = load_file(path, col)
            if d is None or not path.endswith('/a/raw'): return d
            if col == 'treatments':
                t = copy.deepcopy(d[0]); t['identifier'] = 'PLANT-T'; t['_id'] = 'p1'
                t2 = copy.deepcopy(t); t2['_id'] = 'p2'
                t3 = copy.deepcopy(d[1]); t3['identifier'] = 7; t3['_id'] = 'p3'
                d += [t, t2, t3]
            if col == 'entries':
                e = copy.deepcopy(d[0]); e['identifier'] = 'PLANT-E'; e['_id'] = 'p4'
                e2 = copy.deepcopy(d[1]); e2['identifier'] = 'PLANT-E'; e2['_id'] = 'p5'
                d += [e, e2]
            if col == 'devicestatus':
                s = copy.deepcopy(d[0]); s['identifier'] = ''; s['_id'] = 'p6'
                s2 = copy.deepcopy(d[1]); s2['identifier'] = None; s2['_id'] = 'p7'
                d += [s, s2]
            return d
        if '--planted' in sys.argv:
            dump(run(planted)); sys.exit(0)
        R0, R1 = run(load_file), run(planted)
        for name in sorted(set(R0) | set(R1)):
            if name == 'present': continue
            for k in sorted(set(R0[name]) | set(R1[name]), key=lambda k: tuple(map(str, k))):
                if R0[name][k] != R1[name][k]:
                    print('CONTROL DELTA', name, k, R0[name][k], '->', R1[name][k])
        print('## index verdict, planted run')
        bad = sorted({c for (l, s, c) in R1['dupvals'] if l == 'identifier' and R1['dupvals'][(l, s, c)]})
        print('collections that would NOT build:', bad)
