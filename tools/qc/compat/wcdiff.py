# wcdiff.py A.json B.json [--json] : cells differing outside cache/wire; also counts cache/wire-only diffs
import json, sys
RACY = ('cache', 'wire')
def load(p): return json.load(open(p))
def diff(a, b):
    A, B = a['cells'], b['cells']
    keys = list(dict.fromkeys(list(A) + list(B)))
    real, racy = [], []
    for k in keys:
        x, y = A.get(k), B.get(k)
        if x is None or y is None: real.append((k, ['<cell missing>'])); continue
        fs = sorted(set(x) | set(y))
        d = [f for f in fs if x.get(f) != y.get(f)]
        dr = [f for f in d if f not in RACY]
        if dr: real.append((k, dr))
        elif d: racy.append((k, d))
    return real, racy
if __name__ == '__main__':
    a, b = load(sys.argv[1]), load(sys.argv[2])
    real, racy = diff(a, b)
    if '--list' in sys.argv:
        for k, d in real: print(k, '\t', ','.join(d))
    print('cells A %d B %d | differ outside cache/wire: %d | cache/wire only: %d' % (len(a['cells']), len(b['cells']), len(real), len(racy)))
