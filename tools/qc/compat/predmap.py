# predmap.py -> {cell: [slice labels]} from the per-slice prediction files (each written before its slice's code).
#   python3 tools/qc/compat/predmap.py ANALYSIS.json
# The prediction files are listed in the analysis file's "predictions" as [label, path relative to that file].
import json, os, re, sys

CELL = re.compile(r'^((?:settings|entries|treatments|devicestatus|profile|food|activity) (?:x \w+ x \w+(?: \S+)?|\w+ \S+))$')


def load(files):
    """files: [(label, path)]. Returns ({cell: [labels]}, {cell: ['label:rule']})."""
    m, rules = {}, {}
    for lab, f in files:
        for line in open(f):
            if line.startswith('#') or not line.strip(): continue
            parts = line.rstrip('\n').split('\t')
            cell = next((p.strip() for p in parts if CELL.match(p.strip())), None)
            if not cell: continue
            m.setdefault(cell, []).append(lab)
            rules.setdefault(cell, []).append(lab + ':' + parts[0])
    return m, rules


if __name__ == '__main__':
    cfg_path = sys.argv[1]
    cfg = json.load(open(cfg_path))
    base = os.path.dirname(os.path.abspath(cfg_path))
    m, r = load([(lab, os.path.join(base, p)) for lab, p in cfg['predictions']])
    import collections
    print(len(m), collections.Counter(x for v in m.values() for x in v))
