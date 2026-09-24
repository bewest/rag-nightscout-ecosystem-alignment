"""warehouse.py — probes over a flattened SQL warehouse of oref decisions.

Some data holders have already flattened Nightscout into analysis tables
(one row per loop decision, one per treatment). Those tables have lost most
schema detail, but they carry what the raw probes cannot see cheaply:
long per-user histories, device-logged IOB decomposition, and step counts.

Table and column names come from a YAML config (``warehouse.example.yaml``
names the columns used by tim2000s's public repositories at the pins in
``workspace.lock.json``). The connection string comes from the environment
variable named by ``dsn_env`` — never from the config file.

Every query below returns grouped aggregates or per-user counts. Per-user
counts are thresholded here (``privacy``) before anything is written; a
user is treated as a site for the ``MIN_SITES`` rule.
"""

import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from . import privacy
from .cli import _CONTRIBUTOR, _write_checked, envelope



def _connect(dsn):
    try:
        import psycopg
        return psycopg.connect(dsn)
    except ImportError:
        import psycopg2
        return psycopg2.connect(dsn)


def _q(conn, sql):
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def _columns(conn, table):
    schema, _, name = table.rpartition(".")
    rows = _q(conn, "SELECT column_name FROM information_schema.columns "
                    f"WHERE table_name = '{name}'"
                    + (f" AND table_schema = '{schema}'" if schema else ""))
    return {r[0] for r in rows}


def _has(cols, name):
    """Is config column ``name`` (possibly written with its quotes) in ``cols``?"""
    return bool(name) and name.strip('"').lower() in {c.lower() for c in cols}


def platform_votes(conn, cfg):
    """Per user, the three platform votes Insulin-Kinetics' platform_detect uses."""
    d, t = cfg["decisions"], cfg["treatments"]
    u = d["user"]
    votes = defaultdict(dict)
    for user, n_trio, n_aaps in _q(conn, f"""
        SELECT {t['user']},
               sum(CASE WHEN {t['event_type']} IN ('SMB','Bolus') THEN 1 ELSE 0 END),
               sum(CASE WHEN {t['event_type']} IN ('Correction Bolus','Meal Bolus') THEN 1 ELSE 0 END)
        FROM {t['table']} GROUP BY 1"""):
        votes[user]["event_type"] = ("trio" if n_trio > n_aaps else
                                     "aaps" if n_aaps > n_trio else "none")
    cols = _columns(conn, d["table"])
    for key, col, fam in (("bolusiob", d.get("bolusiob"), "trio"),
                          ("steps", d.get("steps"), "aaps")):
        if not _has(cols, col):
            continue
        for user, n in _q(conn, f"SELECT {u}, count({col}) FROM {d['table']} GROUP BY 1"):
            votes[user][key] = fam if n else "none"
    return votes


def _majority(v):
    c = Counter(x for x in v.values() if x != "none")
    return c.most_common(1)[0][0] if c else "none"


def probe_platform(conn, cfg):
    votes = platform_votes(conn, cfg)
    pattern = Counter()
    for user, v in votes.items():
        pattern["|".join(f"{k}={v.get(k, '-')}" for k in ("event_type", "bolusiob", "steps"))] += 1
    return {"users": len(votes),
            "vote_patterns": {k: (n if n >= privacy.MIN_SITES else None)
                              for k, n in sorted(pattern.items())},
            "note": "counts of users per vote pattern; None = fewer than "
                    f"{privacy.MIN_SITES} users"}, {u: _majority(v) for u, v in votes.items()}


def probe_dedup(conn, cfg, plat):
    t = cfg["treatments"]
    out = defaultdict(Counter)
    for user, total, distinct_id in _q(conn, f"""
        SELECT {t['user']}, count(*), count(DISTINCT {t['ns_id']}) FROM {t['table']} GROUP BY 1"""):
        p = plat.get(user, "none")
        out[p]["rows"] += total
        out[p]["repeated_ns_id"] += total - distinct_id
        out[p]["users"] += 1
    for user, n in _q(conn, f"""
        SELECT {t['user']}, count(*) FROM (
          SELECT {t['user']}, {t['insulin']} AS ins, {t['ns_id']} AS id, {t['ts']} AS ts,
                 lag({t['insulin']}) OVER w AS pins, lag({t['ns_id']}) OVER w AS pid,
                 lag({t['ts']}) OVER w AS pts
          FROM {t['table']} WHERE {t['insulin']} > 0
          WINDOW w AS (PARTITION BY {t['user']} ORDER BY {t['ts']})) x
        WHERE ins = pins AND id IS DISTINCT FROM pid
          AND ts - pts <= interval '60 seconds'
        GROUP BY 1"""):
        out[plat.get(user, "none")]["same_dose_within_60s_different_ns_id"] += n
    return {p: dict(c) for p, c in out.items() if c["users"] >= privacy.MIN_SITES}


def probe_iob(conn, cfg, plat):
    d = cfg["decisions"]
    cols = _columns(conn, d["table"])
    need = [d.get(k) for k in ("iob", "basaliob", "bolusiob")]
    if not all(_has(cols, c) for c in need):
        return {"skipped": "iob/basaliob/bolusiob columns not all present"}
    out = defaultdict(Counter)
    for user, total, has_bolus, mismatch in _q(conn, f"""
        SELECT {d['user']}, count(*), count({d['bolusiob']}),
               sum(CASE WHEN {d['bolusiob']} IS NOT NULL AND
                   abs({d['iob']} - {d['basaliob']} - {d['bolusiob']}) > 0.05 THEN 1 ELSE 0 END)
        FROM {d['table']} GROUP BY 1"""):
        p = plat.get(user, "none")
        out[p]["users"] += 1
        out[p]["decisions"] += total
        out[p]["bolusiob_present"] += has_bolus
        out[p]["iob_minus_basaliob_ne_bolusiob"] += mismatch or 0
    return {p: dict(c) for p, c in out.items() if c["users"] >= privacy.MIN_SITES}


def probe_steps(conn, cfg, plat):
    d = cfg["decisions"]
    col = d.get("steps")
    if not _has(_columns(conn, d["table"]), col):
        return {"skipped": "no steps column"}
    out = defaultdict(Counter)
    for user, total, present, zero in _q(conn, f"""
        SELECT {d['user']}, count(*), count({col}),
               sum(CASE WHEN {col} = 0 THEN 1 ELSE 0 END) FROM {d['table']} GROUP BY 1"""):
        p = plat.get(user, "none")
        out[p]["users"] += 1
        out[p]["users_with_any_steps"] += 1 if present else 0
        out[p]["decisions"] += total
        out[p]["steps_present"] += present
        out[p]["steps_zero"] += zero or 0
    return {p: dict(c) for p, c in out.items() if c["users"] >= privacy.MIN_SITES}


def probe_bolus_typing(conn, cfg, plat):
    t = cfg["treatments"]
    sites, docs = defaultdict(set), Counter()
    bt = t.get("bolus_type")
    sel = f"{t['event_type']}, {bt}" if bt else f"{t['event_type']}, NULL"
    for user, et, typ, n in _q(conn, f"""
        SELECT {t['user']}, {sel}, count(*) FROM {t['table']}
        WHERE {t['insulin']} > 0 GROUP BY 1, 2, 3"""):
        key = f"{plat.get(user, 'none')}|eventType={et}|type={typ}"
        sites[key].add(user)
        docs[key] += n
    return privacy.fold(sites, docs)


def probe_external_insulin(conn, cfg, plat):
    t = cfg["treatments"]
    users, rows = Counter(), Counter()
    buckets = Counter()
    for user, ins in _q(conn, f"""
        SELECT {t['user']}, {t['insulin']} FROM {t['table']}
        WHERE {t['event_type']} = 'External Insulin' AND {t['insulin']} > 0"""):
        p = plat.get(user, "none")
        rows[p] += 1
        users[(p, user)] += 1
        b = "<2" if ins < 2 else "<5" if ins < 5 else "<10" if ins < 10 else "<20" if ins < 20 else ">=20"
        buckets[(p, b)] += 1
    per_p = Counter(p for p, _ in users)
    return {p: {"users": per_p[p], "rows": rows[p],
                "dose_units": {b: n for (pp, b), n in sorted(buckets.items()) if pp == p}}
            for p in per_p if per_p[p] >= privacy.MIN_SITES}


def _feature_quality():
    """FEATURE_QUALITY from data_bridge.py, read as a literal so the warehouse
    track does not need data_bridge's pandas/numpy imports."""
    import ast
    src = Path(__file__).resolve().parents[1] / "oref_inv_003_replication" / "data_bridge.py"
    for node in ast.parse(src.read_text()).body:
        target = getattr(node, "target", None) or (node.targets[0] if isinstance(node, ast.Assign) else None)
        if isinstance(target, ast.Name) and target.id == "FEATURE_QUALITY":
            return ast.literal_eval(node.value)
    raise LookupError(f"FEATURE_QUALITY not found in {src}")


def probe_feature_coverage(conn, cfg, plat):
    """Which OREF-INV-003 features a warehouse logs directly, and how often."""
    FEATURE_QUALITY = _feature_quality()
    d = cfg["decisions"]
    # Warehouses mix quoted mixed-case ("sug_ISF") and folded lower-case
    # (sug_isf) column names, so match case-insensitively and quote.
    by_lower = {c.lower(): c for c in _columns(conn, d["table"])}
    present = [f for f in FEATURE_QUALITY if f.lower() in by_lower]
    if not present:
        return {"skipped": "no OREF-INV-003 feature columns in the decisions table"}
    sel = ", ".join(f'count("{by_lower[f.lower()]}")' for f in present)
    by_p = defaultdict(Counter)
    for row in _q(conn, f"SELECT {d['user']}, count(*), {sel} FROM {d['table']} GROUP BY 1"):
        user, total, counts = row[0], row[1], row[2:]
        p = plat.get(user, "none")
        by_p[p]["_users"] += 1
        by_p[p]["_decisions"] += total
        for f, n in zip(present, counts):
            by_p[p][f] += n
    return {
        "our_quality_grade": {f: FEATURE_QUALITY[f] for f in FEATURE_QUALITY},
        "logged_directly": present,
        "non_null_share_by_platform": {
            p: {f: privacy.share(c[f], c["_decisions"]) for f in present} | {"users": c["_users"]}
            for p, c in by_p.items() if c["_users"] >= privacy.MIN_SITES},
    }


PROBES = (("platform", ("Q00",)), ("dedup", ("Q08",)), ("iob", ("Q11", "Q15")),
          ("steps", ("Q16", "Q17")), ("bolus_typing", ("Q04",)),
          ("external_insulin", ("Q04",)), ("feature_coverage", ("Q15",)))


def main(args):
    if not _CONTRIBUTOR.match(args.contributor):
        raise SystemExit("--contributor must be a short lower-case label")
    cfg = yaml.safe_load(Path(args.config).read_text())
    dsn = os.environ.get(cfg.get("dsn_env", "NSPROBE_DSN"))
    if not dsn:
        raise SystemExit(f"set ${cfg.get('dsn_env', 'NSPROBE_DSN')} to the warehouse DSN")
    conn = _connect(dsn)
    platform_result, plat = probe_platform(conn, cfg)
    results = {"platform": platform_result}
    fns = {"dedup": probe_dedup, "iob": probe_iob, "steps": probe_steps,
           "bolus_typing": probe_bolus_typing, "external_insulin": probe_external_insulin,
           "feature_coverage": probe_feature_coverage}
    for name, fn in fns.items():
        try:
            results[name] = fn(conn, cfg, plat)
        except Exception as e:  # a missing column should not sink the other probes
            conn.rollback()
            results[name] = {"error": type(e).__name__}
            print(f"  {name}: {type(e).__name__}: {e}", file=sys.stderr)
    meta = {"source": "warehouse", "users": platform_result["users"]}
    out = Path(args.out) / "warehouse"
    for name, qs in PROBES:
        _write_checked(out, f"{name}.json",
                       envelope(f"warehouse.{name}", qs, args.contributor, meta, results[name]))
        print(f"-> {out / (name + '.json')}")
    return 0
