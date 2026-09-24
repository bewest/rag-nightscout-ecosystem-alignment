"""privacy.py — what may leave the data holder's machine, and the check for it.

A result file holds counts, shares and site-counts. It never holds a
document, a timestamp finer than a calendar quarter, a free-text value, a
device string, or a site's name, and it has no per-site rows: every count is
pooled across sites, with the number of sites that contributed. Two rules
enforce that:

1. **Site threshold.** A value (an eventType string, a field path found by
   searching, a device family combination) is reported by name only if at
   least ``MIN_SITES`` sites wrote it; the rest are folded into one
   ``_other`` bucket with their total. This is the same corroboration rule
   ``nsschema.redact`` applies to census values. Quarters in the
   longitudinal probe follow the same threshold.
2. **Validator.** ``check_output`` walks every key and string in every
   result file and rejects URLs, emails, hostnames, long hex, UUIDs,
   timestamps, long digit runs and non-pseudonymous site labels.
   ``nsprobe check`` runs it; ``nsprobe run`` runs it before writing. A
   result that fails is not written.

The nsschema census files that ``nsprobe census`` writes follow nsschema's
own policy (``nsschema/redact.py``). They do carry per-site document counts
under the pseudonyms, and corpus-wide numeric minimum and maximum for fields
with at least 20 observations, which for a timestamp field is the earliest
and latest reading in the whole corpus.
"""

import json
import re
from pathlib import Path

from nsschema import redact

MIN_SITES = 3

SITE_KEY = re.compile(r"^S\d{3}$")
_BAD = [
    ("url", re.compile(r"https?://|wss?://", re.I)),
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("uuid", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)),
    ("hex", re.compile(r"\b[0-9a-fA-F]{16,}\b")),
    ("timestamp", re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")),
    ("date", re.compile(r"\b\d{4}-\d{2}-\d{2}\b")),
    ("hostname", re.compile(r"\b[a-z0-9-]+\.(herokuapp|fly|azurewebsites|ns\.|com|net|org|io|app|dev|cloud)\b", re.I)),
    ("long-number", re.compile(r"\d{9,}")),
]
# Keys whose string values are allowed to look like dates: the run's own
# date, and quarter buckets (YYYY-Qn) which the date rule does not match.
_ALLOWED_DATE_KEYS = {"generated", "tool_commit_date"}


def fold(per_value_sites, per_value_docs, min_sites=MIN_SITES):
    """Apply rule 1 to a {value: set(sites)} / {value: docs} pair."""
    kept, other_docs, other_values = {}, 0, 0
    for value, sites in per_value_sites.items():
        docs = per_value_docs.get(value, 0)
        safe = isinstance(value, str) and (
            len(value) <= redact.MAX_VALUE_LEN
            and not redact.is_personal_shape(value)) or isinstance(value, (bool, int))
        if len(sites) >= min_sites and safe:
            kept[str(value)] = {"sites": len(sites), "documents": docs}
        else:
            other_docs += docs
            other_values += 1
    if other_values:
        kept["_other"] = {"values": other_values, "documents": other_docs,
                          "note": f"values written by fewer than {min_sites} sites, or not vocabulary"}
    return kept


def share(num, den):
    return round(num / den, 6) if den else None


def _walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_key(k, path)
            yield from _walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield path, obj


def _walk_key(k, path):
    yield f"{path}.<key>", str(k)


def check_output(obj):
    """Return a list of (path, rule) violations in a result object."""
    bad = []
    for path, s in _walk(obj):
        leaf = path.rsplit(".", 1)[-1]
        if leaf in _ALLOWED_DATE_KEYS:
            continue
        # Site labels appear as keys under per_site maps; they must be S###.
        if ".per_site.<key>" in path or path.endswith("per_site.<key>"):
            if not SITE_KEY.match(s):
                bad.append((path, "site-label"))
            continue
        for rule, rx in _BAD:
            if rx.search(s):
                bad.append((path, rule))
                break
    return bad


def check_dir(out_dir: Path):
    problems = []
    files = sorted(out_dir.rglob("*.json"))
    for f in files:
        try:
            obj = json.loads(f.read_text())
        except ValueError as e:
            problems.append((str(f), f"not JSON: {e}"))
            continue
        for path, rule in check_output(obj):
            problems.append((str(f), f"{rule} at {path}"))
    return files, problems
