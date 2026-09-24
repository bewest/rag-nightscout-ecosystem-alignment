"""probes.py — aggregate-only probes over raw Nightscout documents.

Every probe answers one question in ``questions.yaml`` (the ``Q`` ids below)
and keeps only per-site counters while it runs. ``result()`` turns those into
the returned form: counts, shares, site-counts, grouped by the writer family
(``family.classify``) or by the site's dominant closed-loop family.

Nothing a probe returns names a document, a person, a device, or a moment
finer than a calendar quarter. ``privacy.check_output`` is the backstop.
"""

import hashlib
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

from . import family, privacy

# ── shared helpers ──────────────────────────────────────────────────────

_ISO_TZ = re.compile(r"(Z|[+-]\d{2}:?\d{2})$")


def iso_form(s):
    """Classify an ISO timestamp string's zone designator."""
    if not isinstance(s, str) or not s:
        return "absent"
    m = _ISO_TZ.search(s.strip())
    if not m:
        return "no-zone"
    return "Z" if m.group(1) == "Z" else ("+00:00" if m.group(1).replace(":", "") in ("+0000", "-0000") else "offset")


def parse_iso(s):
    """(epoch_ms, offset_minutes or None) for an ISO string, else (None, None)."""
    if not isinstance(s, str) or len(s) < 10:
        return None, None
    t = s.strip().replace("Z", "+00:00")
    if re.search(r"[+-]\d{4}$", t):
        t = t[:-2] + ":" + t[-2:]
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return None, None
    if dt.tzinfo is None:
        return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000), None
    off = dt.utcoffset()
    return int(dt.timestamp() * 1000), int(off.total_seconds() // 60)


def doc_time_ms(doc, collection):
    """Best-effort event time, for quarter bucketing and cadence only."""
    for key in ("date", "mills"):
        v = doc.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 1e11:
            return float(v)
    for key in ("created_at", "dateString", "timestamp", "sysTime"):
        v = doc.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 1e11:
            return float(v)
        ms, _ = parse_iso(v)
        if ms is not None:
            return float(ms)
    return None


def quarter(ms):
    if ms is None or not math.isfinite(ms):
        return None
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"


def delta_bucket(ms):
    """Coarse bucket for |a - b| in ms. Whole-hour offsets flag timezone bugs."""
    if ms is None:
        return "n/a"
    a = abs(ms)
    if a == 0:
        return "0"
    if a < 1000:
        return "<1s"
    if a < 60_000:
        return "<1m"
    r = a % 3_600_000
    if a >= 3_540_000 and (r < 60_000 or r > 3_540_000):
        return "whole-hours"
    if a < 3_600_000:
        return "<1h"
    return ">=1h"


def paths(obj, prefix="", depth=0, max_depth=4):
    """Dotted key paths in a document, arrays collapsed to ``[]``."""
    if depth > max_depth:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            yield p
            yield from paths(v, p, depth + 1, max_depth)
    elif isinstance(obj, list) and obj:
        p = f"{prefix}[]"
        for v in obj[:3]:
            if isinstance(v, (dict, list)):
                yield from paths(v, p, depth + 1, max_depth)


def get(doc, dotted):
    cur = doc
    for part in dotted.split("."):
        if isinstance(cur, list):
            cur = cur[0] if cur else None
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) and math.isfinite(v):
        return float(v)
    if isinstance(v, str):
        try:
            f = float(v)
            return f if math.isfinite(f) else None
        except ValueError:
            return None
    return None


def h64(s):
    return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "big")


class Tally:
    """``{group: {key: Counter(site -> n)}}`` with site-aware emission."""

    def __init__(self):
        self.d = defaultdict(lambda: defaultdict(Counter))

    def add(self, group, key, site, n=1):
        self.d[group][key][site] += n

    def emit(self, fold_keys=False, denominators=None):
        out = {}
        for group, keys in sorted(self.d.items()):
            rows = {}
            sites_by_key = {k: set(c) for k, c in keys.items()}
            docs_by_key = {k: sum(c.values()) for k, c in keys.items()}
            if fold_keys:
                folded = privacy.fold(sites_by_key, docs_by_key)
                rows = folded
            else:
                for k in sorted(keys, key=str):
                    rows[str(k)] = {"sites": len(sites_by_key[k]),
                                    "documents": docs_by_key[k]}
            if denominators is not None:
                den = denominators.get(group)
                for k, row in rows.items():
                    if den and "documents" in row:
                        row["share"] = privacy.share(row["documents"], den)
            out[str(group)] = rows
        return out


# ── probes ──────────────────────────────────────────────────────────────

class Probe:
    id = ""
    questions = ()
    collections = ()

    def observe(self, ctx, doc):  # pragma: no cover - interface
        raise NotImplementedError

    def end_source(self, ctx):
        pass

    def result(self, run):  # pragma: no cover - interface
        raise NotImplementedError


class Families(Probe):
    """Who wrote what: the classification every other probe is grouped by."""
    id = "families"
    questions = ("Q00", "Q12")
    collections = ("entries", "treatments", "devicestatus", "profile", "activity")

    def __init__(self):
        self.signal = Tally()
        self.fam = Tally()
        self.pump = Tally()

    def observe(self, ctx, doc):
        self.fam.add(ctx.collection, ctx.family, ctx.site)
        self.signal.add(f"{ctx.collection}:{ctx.family}", ctx.signal, ctx.site)
        if ctx.collection == "devicestatus" and isinstance(doc.get("pump"), dict):
            for key in ("manufacturer", "model"):
                v = get(doc, f"pump.{key}")
                if isinstance(v, str):
                    self.pump.add(key, v.strip(), ctx.site)

    def result(self, run):
        site_fams = Counter(run.site_family.values())
        return {
            "writer_family_by_collection": self.fam.emit(
                denominators=run.collection_docs),
            "signals": self.signal.emit(),
            "site_dominant_family": dict(sorted(site_fams.items())),
            "pump_vocabulary": self.pump.emit(fold_keys=True),
        }


class OpenapsShape(Probe):
    """Q01, Q02, Q11: is the openaps.* subtree one shape or several?"""
    id = "openaps_shape"
    questions = ("Q01", "Q02", "Q11")
    collections = ("devicestatus",)

    def __init__(self):
        self.paths = Tally()
        self.docs = Tally()
        self.iob_type = Tally()

    def observe(self, ctx, doc):
        oa = doc.get("openaps")
        if not isinstance(oa, dict):
            return
        fam = ctx.family
        self.docs.add(fam, "openaps_docs", ctx.site)
        for p in set(paths(oa, "openaps", max_depth=3)):
            if ".predBGs." in p and p.count(".") > 3:
                continue
            self.paths.add(fam, p, ctx.site)
        iob = oa.get("iob")
        kind = ("array" if isinstance(iob, list) else
                "object" if isinstance(iob, dict) else
                "absent" if iob is None else type(iob).__name__)
        self.iob_type.add(fam, kind, ctx.site)

    def result(self, run):
        dens = {g: sum(sum(c.values()) for c in keys.values())
                for g, keys in self.docs.d.items()}
        return {
            "openaps_docs_by_family": self.docs.emit(),
            "paths_by_family": self.paths.emit(fold_keys=True, denominators=dens),
            "iob_container_type_by_family": self.iob_type.emit(denominators=dens),
        }


class EventTypes(Probe):
    """Q03: the treatments eventType vocabulary, and who writes each value."""
    id = "event_types"
    questions = ("Q03",)
    collections = ("treatments",)

    def __init__(self):
        self.all = Tally()
        self.byfam = Tally()

    def observe(self, ctx, doc):
        et = doc.get("eventType")
        key = et if isinstance(et, str) else f"<{type(et).__name__}>"
        self.all.add("all", key, ctx.site)
        self.byfam.add(ctx.family, key, ctx.site)

    def result(self, run):
        return {"all": self.all.emit(fold_keys=True)["all"] if self.all.d else {},
                "by_writer_family": self.byfam.emit(fold_keys=True)}


def _explicit_smb(doc):
    return (doc.get("type") == "SMB" or doc.get("isSMB") is True
            or doc.get("eventType") == "SMB")


def _heuristic_smb(doc):
    """The size rule in ns2parquet's _is_smb and grid.py: automatic and < 5 U."""
    if doc.get("automatic") is True:
        ins = num(doc.get("insulin")) or 0
        if 0 < ins < 5.0:
            return True
    return False


def _size_bucket(u):
    for edge in (0.1, 0.5, 1, 2, 5, 10, 25):
        if u < edge:
            return f"<{edge}"
    return ">=25"


class SmbMarking(Probe):
    """Q04: how automatic boluses are marked, and whether our rule finds them."""
    id = "smb_marking"
    questions = ("Q04",)
    collections = ("treatments",)

    def __init__(self):
        self.combo = Tally()
        self.confusion = Tally()
        self.size = Tally()

    def observe(self, ctx, doc):
        ins = num(doc.get("insulin"))
        if not ins or ins <= 0:
            return
        et = doc.get("eventType")
        et = et if et in ("SMB", "Correction Bolus", "Bolus", "Meal Bolus",
                          "Snack Bolus", "Combo Bolus", "External Insulin") else (
            "other" if isinstance(et, str) else "absent")
        typ = doc.get("type")
        typ = typ if typ in ("SMB", "NORMAL", "normal", "square", "dual", "PRIMING") else (
            "other" if isinstance(typ, str) else "absent")
        combo = (f"eventType={et}|type={typ}|isSMB={_tri(doc.get('isSMB'))}"
                 f"|automatic={_tri(doc.get('automatic'))}"
                 f"|isBasalInsulin={_tri(doc.get('isBasalInsulin'))}")
        self.combo.add(ctx.family, combo, ctx.site)
        e, h = _explicit_smb(doc), _heuristic_smb(doc)
        self.confusion.add(ctx.family, f"explicit={e}|automatic_lt5U={h}", ctx.site)
        if e:
            self.size.add(ctx.family, _size_bucket(ins), ctx.site)

    def result(self, run):
        return {"marker_combinations": self.combo.emit(fold_keys=True),
                "explicit_marker_vs_automatic_lt5U_rule": self.confusion.emit(),
                "explicit_smb_size_units": self.size.emit()}


def _tri(v):
    return "true" if v is True else "false" if v is False else (
        "absent" if v is None else "non-bool")


class TempBasal(Probe):
    """Q05: absolute vs percent vs rate, and duration units."""
    id = "temp_basal"
    questions = ("Q05",)
    collections = ("treatments",)

    def __init__(self):
        self.shape = Tally()
        self.flags = Tally()

    def observe(self, ctx, doc):
        if doc.get("eventType") != "Temp Basal":
            return
        present = [k for k in ("absolute", "rate", "percent", "duration",
                               "durationInMilliseconds", "type", "temp")
                   if doc.get(k) is not None]
        self.shape.add(ctx.family, "+".join(present) or "none", ctx.site)
        a, r = num(doc.get("absolute")), num(doc.get("rate"))
        d = num(doc.get("duration"))
        dms = num(doc.get("durationInMilliseconds"))
        if a is not None and r is not None and abs(a - r) > 1e-6:
            self.flags.add(ctx.family, "absolute!=rate", ctx.site)
        if a is None and r is None and doc.get("percent") is not None:
            self.flags.add(ctx.family, "percent-only", ctx.site)
        if d == 0:
            self.flags.add(ctx.family, "duration=0", ctx.site)
        if d is not None and d != int(d):
            self.flags.add(ctx.family, "duration-fractional", ctx.site)
        if d is not None and dms is not None and abs(d * 60000 - dms) > 1000:
            self.flags.add(ctx.family, "duration!=durationInMilliseconds/60000", ctx.site)
        self.flags.add(ctx.family, "total", ctx.site)

    def result(self, run):
        return {"field_presence": self.shape.emit(fold_keys=True),
                "flags": self.flags.emit()}


class Units(Probe):
    """Q06: mmol/L prevalence, and whether the ISF < 15 rule agrees with units."""
    id = "units"
    questions = ("Q06",)
    collections = ("profile", "entries", "devicestatus")

    def __init__(self):
        self.spelling = Tally()
        self.site_units = defaultdict(Counter)
        self.sgv = Tally()
        self.isf = defaultdict(Counter)       # site -> bucket
        self.target = defaultdict(Counter)

    def observe(self, ctx, doc):
        if ctx.collection == "profile":
            for where, v in [("top", doc.get("units"))] + [
                    ("store", b.get("units")) for b in (doc.get("store") or {}).values()
                    if isinstance(b, dict)]:
                if isinstance(v, str):
                    self.spelling.add(where, v, ctx.site)
                    self.site_units[ctx.site]["mmol" if "mmol" in v.lower() else "mgdl"] += 1
                else:
                    self.spelling.add(where, "<absent>", ctx.site)
        elif ctx.collection == "entries":
            s = num(doc.get("sgv"))
            if s is not None:
                self.sgv.add("sgv", "0" if s == 0 else "<30" if s < 30 else
                             "30-39" if s < 40 else ">400" if s > 400 else "40-400", ctx.site)
        else:
            sug = get(doc, "openaps.suggested") or {}
            if isinstance(sug, dict):
                isf = num(sug.get("ISF"))
                if isf is not None:
                    self.isf[ctx.site]["<15" if isf < 15 else "15+"] += 1
                tgt = num(sug.get("targetBG"))
                if tgt is not None:
                    self.target[ctx.site]["<30" if tgt < 30 else "30+"] += 1

    def result(self, run):
        confusion = Tally()
        for site, c in self.isf.items():
            u = self.site_units.get(site)
            units = ("mmol" if u and u["mmol"] >= u["mgdl"] else
                     "mgdl" if u else "unknown")
            for bucket, n in c.items():
                confusion.add("isf", f"profile={units}|isf{bucket}", site, n)
        for site, c in self.target.items():
            u = self.site_units.get(site)
            units = ("mmol" if u and u["mmol"] >= u["mgdl"] else
                     "mgdl" if u else "unknown")
            for bucket, n in c.items():
                confusion.add("targetBG", f"profile={units}|target{bucket}", site, n)
        return {"profile_units_spelling": self.spelling.emit(fold_keys=True),
                "entries_sgv_range": self.sgv.emit(),
                "algorithm_value_vs_profile_units": confusion.emit()}


class Time(Probe):
    """Q07, Q09: timestamp forms, zone agreement, fractional ms."""
    id = "time"
    questions = ("Q07", "Q09")
    collections = ("entries", "treatments", "devicestatus")

    def __init__(self):
        self.t = Tally()

    def observe(self, ctx, doc):
        c, f, s = ctx.collection, ctx.family, ctx.site
        g = f"{c}:{f}"
        self.t.add(g, "total", s)
        date = doc.get("date")
        if isinstance(date, float) and not date.is_integer():
            self.t.add(g, "date:fractional", s)
        elif isinstance(date, str):
            self.t.add(g, "date:string", s)
        iso_key = "dateString" if c == "entries" else "created_at"
        self.t.add(g, f"{iso_key}:{iso_form(doc.get(iso_key))}", s)
        ms, off = parse_iso(doc.get(iso_key))
        base = num(date) if c == "entries" else (
            num(doc.get("mills")) or num(doc.get("date")))
        if ms is not None and base is not None and base > 1e11:
            self.t.add(g, f"|{iso_key}-date|:{delta_bucket(ms - base)}", s)
        uo = doc.get("utcOffset")
        if uo is None:
            self.t.add(g, "utcOffset:absent", s)
        elif num(uo) is None:
            self.t.add(g, "utcOffset:non-numeric", s)
        else:
            if off is None:
                self.t.add(g, "utcOffset:present|iso-has-no-offset", s)
            elif int(num(uo)) == off:
                self.t.add(g, "utcOffset:agrees-with-iso", s)
            elif off == 0:
                self.t.add(g, "utcOffset:iso-is-UTC", s)
            else:
                self.t.add(g, "utcOffset:disagrees-with-iso", s)
        if c == "entries" and doc.get("direction") == "NONE":
            self.t.add(g, "direction:NONE", s)

    def result(self, run):
        dens = {g: sum(keys["total"].values()) for g, keys in self.t.d.items()}
        return {"by_collection_and_writer": self.t.emit(denominators=dens)}


class Duplicates(Probe):
    """Q08: duplicates that _id-only dedup misses."""
    id = "duplicates"
    questions = ("Q08",)
    collections = ("entries", "treatments", "devicestatus")

    ENTRY_WINDOW_MS = 150_000
    TREATMENT_WINDOW_MS = 60_000

    def __init__(self):
        self.t = Tally()
        self.buf = []

    def observe(self, ctx, doc):
        _id = doc.get("_id")
        _id = _id if isinstance(_id, str) else (
            _id.get("$oid") if isinstance(_id, dict) else None)
        c = ctx.collection
        if c == "entries":
            t, v = num(doc.get("date")), num(doc.get("sgv"))
            if t is not None and v is not None:
                dev = doc.get("device")
                self.buf.append((t, v, _id, ctx.family,
                                 h64(dev) if isinstance(dev, str) else 0))
        elif c == "treatments":
            t = doc_time_ms(doc, c)
            if t is not None:
                ids = tuple(doc.get(k) for k in ("identifier", "syncIdentifier",
                                                 "pumpId", "interfaceIDs"))
                self.buf.append((t, doc.get("eventType"), num(doc.get("insulin")),
                                 num(doc.get("carbs")), _id, ctx.family, ids))
        else:
            self.buf.append((doc.get("created_at"), doc.get("device"), _id, ctx.family))

    def end_source(self, ctx):
        g, s = f"{ctx.api}:{ctx.collection}", ctx.site
        buf, self.buf = self.buf, []
        self.t.add(g, "total", s, len(buf))
        ids = Counter(r[2] if ctx.collection == "entries" else
                      (r[4] if ctx.collection == "treatments" else r[2]) for r in buf)
        self.t.add(g, "same_id_repeated", s, sum(n - 1 for i, n in ids.items() if i and n > 1))
        if ctx.collection == "entries":
            buf.sort(key=lambda r: r[0])
            gaps = [b[0] - a[0] for a, b in zip(buf, buf[1:]) if b[4] == a[4]]
            if len(gaps) >= 20:
                med = sorted(gaps)[len(gaps) // 2] / 1000
                self.t.add(g, "site_median_same_device_interval:" +
                           ("<=90s" if med <= 90 else "<=240s" if med <= 240 else
                            "<=360s" if med <= 360 else ">360s"), s)
            for i in range(1, len(buf)):
                for j in range(i - 1, max(-1, i - 8), -1):
                    a, b = buf[j], buf[i]
                    dt = b[0] - a[0]
                    if dt > self.ENTRY_WINDOW_MS:
                        break
                    if a[1] == b[1] and a[2] != b[2]:
                        # Same value from the same device a minute apart is a
                        # high-cadence sensor; from two devices seconds apart
                        # it is one reading uploaded twice.
                        src = "same-device" if a[4] == b[4] else "cross-device"
                        win = "<=5s" if dt <= 5000 else "<=60s" if dt <= 60000 else "<=150s"
                        pair = "+".join(sorted((a[3], b[3])))
                        self.t.add(g, f"same_sgv:{src}:{win}:{pair}", s)
                        break
        elif ctx.collection == "treatments":
            buf.sort(key=lambda r: r[0])
            seen_keys = defaultdict(set)
            for i, r in enumerate(buf):
                for j in range(i - 1, max(-1, i - 10), -1):
                    a = buf[j]
                    if r[0] - a[0] > self.TREATMENT_WINDOW_MS:
                        break
                    if (a[1] == r[1] and a[2] == r[2] and a[3] == r[3]
                            and a[4] != r[4] and (r[2] or r[3])):
                        pair = "+".join(sorted((a[5], r[5])))
                        self.t.add(g, f"same_event_within_60s:{pair}", s)
                        break
                for name, v in zip(("identifier", "syncIdentifier", "pumpId", "interfaceIDs"), r[6]):
                    if isinstance(v, (str, int)) and not isinstance(v, bool):
                        k = h64(f"{name}:{v}")
                        if k in seen_keys[name]:
                            self.t.add(g, f"same_{name}_different_doc", s)
                        seen_keys[name].add(k)
        else:
            keys = Counter((r[0], r[1]) for r in buf if r[0] and r[1])
            self.t.add(g, "same_created_at+device_repeated", s,
                       sum(n - 1 for n in keys.values() if n > 1))

    def result(self, run):
        dens = {g: sum(keys["total"].values()) for g, keys in self.t.d.items()}
        return {"by_api_and_collection": self.t.emit(denominators=dens)}


V3_FIELDS = ("identifier", "srvCreated", "srvModified", "isValid", "subject",
             "modifiedBy", "isReadOnly", "app")


class V3Envelope(Probe):
    """Q13: is the v3 envelope present, visible through v1, and consistent?"""
    id = "v3_envelope"
    questions = ("Q13",)
    collections = ("entries", "treatments", "devicestatus", "profile", "food")

    def __init__(self):
        self.t = Tally()
        self.v1ids = defaultdict(set)
        self.overlap = Tally()

    def observe(self, ctx, doc):
        g = f"{ctx.api}:{ctx.collection}"
        self.t.add(g, "total", ctx.site)
        for f in V3_FIELDS:
            if f in doc:
                self.t.add(g, f"has:{f}", ctx.site)
        if doc.get("isValid") is False:
            self.t.add(g, "isValid:false", ctx.site)
        key = (ctx.site, ctx.collection)
        ident, _id = doc.get("identifier"), doc.get("_id")
        if ctx.api == "v1":
            for v in (ident, _id):
                if isinstance(v, str):
                    self.v1ids[key].add(h64(v))
        elif key in self.v1ids and isinstance(ident, str):
            hit = h64(ident) in self.v1ids[key]
            self.overlap.add(ctx.collection, "v3_identifier_in_v1" if hit
                             else "v3_identifier_not_in_v1", ctx.site)

    def result(self, run):
        dens = {g: sum(keys["total"].values()) for g, keys in self.t.d.items()}
        return {"envelope_fields": self.t.emit(denominators=dens),
                "v1_v3_identifier_overlap": self.overlap.emit()}


TRACKED = (
    ("entries", "trend"), ("entries", "trendRate"), ("entries", "utcOffset"),
    ("entries", "identifier"), ("entries", "srvModified"),
    ("treatments", "isSMB"), ("treatments", "type"), ("treatments", "automatic"),
    ("treatments", "utcOffset"), ("treatments", "identifier"),
    ("treatments", "syncIdentifier"), ("treatments", "pumpId"),
    ("treatments", "isBasalInsulin"), ("treatments", "srvModified"),
    ("devicestatus", "openaps.suggested.TDD"), ("devicestatus", "openaps.suggested.ISF"),
    ("devicestatus", "openaps.iob"), ("devicestatus", "openaps.iob.lastTemp"),
    ("devicestatus", "openaps.suggested.predBGs"), ("devicestatus", "pump.bolusing"),
    ("devicestatus", "pump.status.bolusing"), ("devicestatus", "loop"),
    ("devicestatus", "identifier"), ("devicestatus", "srvModified"),
)


class Longitudinal(Probe):
    """Q14: when did tracked fields appear or disappear, by quarter."""
    id = "longitudinal"
    questions = ("Q14",)
    collections = ("entries", "treatments", "devicestatus")

    def __init__(self):
        self.tot = Tally()
        self.has = Tally()

    def observe(self, ctx, doc):
        q = quarter(doc_time_ms(doc, ctx.collection))
        if q is None:
            return
        self.tot.add(ctx.collection, q, ctx.site)
        for coll, p in TRACKED:
            if coll == ctx.collection and get(doc, p) is not None:
                self.has.add(f"{coll}:{p}", q, ctx.site)

    def result(self, run):
        out = {}
        tot = {c: {q: (len(s), sum(s.values())) for q, s in keys.items()}
               for c, keys in self.tot.d.items()}
        for c, keys in tot.items():
            out[f"{c}:_documents"] = {
                q: ({"sites": ns, "documents": nd} if ns >= privacy.MIN_SITES
                    else {"sites": ns, "documents": None, "suppressed": True})
                for q, (ns, nd) in sorted(keys.items())}
        for g, keys in sorted(self.has.d.items()):
            coll = g.split(":", 1)[0]
            rows = {}
            for q, sites in sorted(keys.items()):
                ns_all, nd_all = tot.get(coll, {}).get(q, (0, 0))
                if ns_all < privacy.MIN_SITES:
                    continue
                rows[q] = {"sites": len(sites), "documents": sum(sites.values()),
                           "share": privacy.share(sum(sites.values()), nd_all)}
            out[g] = rows
        return {"tracked_paths_by_quarter": out,
                "note": f"quarters with fewer than {privacy.MIN_SITES} contributing sites are omitted"}


_ACTIVITY_PATH = re.compile(r"heart|(^|[._])hr($|[._])|bpm|step|pedom|activit|exercis|motion", re.I)
# oref's `activity` under iob is insulin activity (U/min), not physical activity.
_INSULIN_ACTIVITY = re.compile(r"(^|\.)iob(\[\])?(\.iobWithZeroTemp)?\.activity$|insulin_?activity", re.I)


class Activity(Probe):
    """Q16, Q17: activity collection shape, and HR/steps anywhere else."""
    id = "activity"
    questions = ("Q16", "Q17")
    collections = ("activity", "devicestatus", "treatments", "entries")

    def __init__(self):
        self.keys = Tally()
        self.types = Tally()
        self.anywhere = Tally()
        self.times = defaultdict(list)

    def observe(self, ctx, doc):
        if ctx.collection == "activity":
            self.keys.add(ctx.family, "+".join(sorted(k for k in doc if k != "_id")), ctx.site)
            typ = doc.get("type")
            self.types.add("type", typ if isinstance(typ, str) else "<absent>", ctx.site)
            t = doc_time_ms(doc, "activity")
            if t is not None:
                self.times[(ctx.site, typ if isinstance(typ, str) else "<absent>")].append(t)
        for p in set(paths(doc, max_depth=3)):
            if _ACTIVITY_PATH.search(p) and not _INSULIN_ACTIVITY.search(p):
                self.anywhere.add(ctx.collection, p, ctx.site)

    def result(self, run):
        types = self.types.emit(fold_keys=True).get("type", {})
        cadence = Tally()
        for (site, typ), ts in self.times.items():
            typ = typ if typ in types else "_other"
            ts.sort()
            gaps = [b - a for a, b in zip(ts, ts[1:]) if b > a]
            if len(gaps) >= 20:
                med = sorted(gaps)[len(gaps) // 2] / 1000
                bucket = ("<=10s" if med <= 10 else "<=1m" if med <= 60 else
                          "<=5m" if med <= 300 else "<=15m" if med <= 900 else ">15m")
                cadence.add(typ, bucket, site)
        return {"activity_key_sets": self.keys.emit(fold_keys=True),
                "activity_type_values": types,
                "activity_median_interval_by_type": cadence.emit(fold_keys=False),
                "hr_steps_paths_in_any_collection": self.anywhere.emit(fold_keys=True)}


ALL = (Families, OpenapsShape, EventTypes, SmbMarking, TempBasal, Units,
       Time, Duplicates, V3Envelope, Longitudinal, Activity)
