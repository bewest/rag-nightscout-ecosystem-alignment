"""scan_pii.py — find personal data in files that are committed to the repo.

``redact.py`` protects what the *census* emits. It cannot protect what was
committed before it existed, or what someone adds by hand: test fixtures
captured from live Nightscout sites, saved API responses, debugging dumps.

This applies the same policy in reverse — reads a JSON file, walks every
value, and reports anything the census would have refused to publish:

Findings are graded, because triage order matters and an undifferentiated
list of thousands of timestamps hides the one device token in it:

``credential``
    A secret or a value that acts as one — API secrets, APNs device
    tokens, Apple Developer Team IDs, and any high-entropy opaque string.
    Act on these first; they may need rotating, not just masking.
``identity``
    Identifies a person, an install or a device — document ids, sync
    identifiers, serial numbers, bundle identifiers, user-chosen names,
    dashboard URLs.
``quasi-identifier``
    Not identifying alone, narrowing in combination — exact timestamps,
    clock times, timezones, a person's own emoji. A captured-document
    corpus is *made of* these, so they are reported only under ``--all``.
``review``
    A value a rule cannot decide. Device strings are the case that matters:
    they are mostly app and hardware names, which are exactly the evidence
    this corpus exists to record, but LibreLinkUp and some uploaders can
    surface a user-chosen name there. Masking them by vocabulary was tried
    and every value it touched was a false positive, so the unrecognised
    ones are surfaced for a person to judge instead of being destroyed.

It reports **paths and categories, never the values themselves** — a report
about a leak should not be a second copy of it. ``--count`` shows how many
distinct values each path holds.

A ``--baseline`` file lists findings already reviewed and accepted, one
``path<TAB>category`` per line, so CI fails on new leaks rather than on the
known state of the repo. Exit status is 1 when anything unbaselined is
found.

Usage::

    python3 -m nsschema.scan_pii tools/ns2parquet/fixtures/*.json
    python3 -m nsschema.scan_pii --all --count conformance/t1pal/scenarios/*.json
    python3 -m nsschema.scan_pii --baseline tools/nsschema/pii-baseline.tsv <files>
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from . import redact

# Opaque high-entropy strings: APNs device tokens, API keys, session ids.
_OPAQUE = re.compile(r"^[0-9a-fA-F]{32,}$|^[A-Za-z0-9_\-]{40,}$")

CATEGORIES = ("credential", "identity", "quasi-identifier", "review")
DEFAULT_CATEGORIES = ("credential", "identity")

# Device strings are app, bridge and hardware names. This list exists to
# quieten the ones already recognised, not to define what is allowed: a
# token missing from it is reported for review, never masked.
_DEVICE_VOCABULARY = frozenset({
    "dexcom", "libre", "librelink", "librelinkup", "libreview", "freestyle",
    "xdrip", "xdrip+", "xdrip4ios", "xdripswift", "spike", "diable", "zukka",
    "loop", "trio", "aaps", "androidaps", "openaps", "nightscout", "nocturne",
    "share", "share2", "webfollower", "follower", "bridge", "connect",
    "medtronic", "minimed", "omnipod", "dash", "eros", "tandem", "tslim",
    "insulet", "roche", "accuchek", "combo", "dana", "ypsopump", "kaleido",
    "pump", "cgm", "sensor", "transmitter", "phone", "iphone", "ipad",
    "watch", "android", "ios", "uploader", "carelink", "glooko", "tidepool",
    "enlite", "guardian", "eversense", "sibionics", "poctech", "device",
    "sony", "samsung", "google", "pixel", "xiaomi", "huawei", "motorola",
    "via", "and", "on", "by", "with", "from",
})

# Field-name fragments that make a value a credential rather than an
# identifier: it grants access, or names the account that built the app.
_CREDENTIAL_FRAGMENTS = (
    "token", "secret", "password", "apikey", "api_key", "teamid",
    "privatekey", "accesskey",
)

# Values that are ecosystem vocabulary, not a person's text. Without this,
# every `enteredBy: "Loop"` and `defaultProfile: "Default"` is a finding.
_VOCABULARY = frozenset({
    "default", "loop", "trio", "androidaps", "aaps", "openaps", "nightscout",
    "xdrip", "xdrip+", "xdrip4ios", "xdripswift", "spike", "diable",
    "nightguard", "iphone", "ipad", "phone", "loop://iphone", "dexcom",
    "libre", "insulet", "dash", "eros", "omnipod", "medtronic", "tandem",
    "normal", "suspended", "bolusing", "error", "ok", "loaded", "readable",
})


def _device_tokens_for_review(value):
    """Device-string tokens that no vocabulary or pattern explains."""
    unknown = []
    for token in value.split():
        bare = token.strip("()[]{},")
        if not bare or any(ch.isdigit() for ch in bare) or "://" in token:
            continue
        parts = [p for p in re.split(r"[-_.:/+]+", bare.lower()) if p]
        if not any(p in _DEVICE_VOCABULARY for p in parts):
            unknown.append(bare)
    return unknown


def categorize(path: str, value: str):
    low_path = path.lower()
    if low_path.rsplit(".", 1)[-1].rstrip("[]") == "device":
        # Never `identity`: a device string is evidence first. Only the
        # tokens nothing explains are worth a human's attention.
        return "review" if _device_tokens_for_review(value) else None
    if any(f in low_path for f in _CREDENTIAL_FRAGMENTS) or _OPAQUE.match(value):
        return "credential"
    if value.strip().lower() in _VOCABULARY:
        return None
    if redact.is_denied(path):
        return "identity"
    if redact.is_personal_shape(value):
        return "quasi-identifier"
    return None


def load_baseline(path):
    """Accepted findings, one `path<TAB>category` per line; # comments."""
    accepted = set()
    if path is None or not Path(path).is_file():
        return accepted
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        field, _, category = line.partition("\t")
        accepted.add((field.strip(), category.strip()))
    return accepted


def scan_document(doc, findings, prefix=""):
    if isinstance(doc, dict):
        for key, value in doc.items():
            scan_document(value, findings, f"{prefix}.{key}" if prefix else key)
    elif isinstance(doc, list):
        for item in doc:
            scan_document(item, findings, f"{prefix}[]")
    elif isinstance(doc, str) and doc:
        category = categorize(prefix, doc)
        if category:
            findings[(prefix, category)].add(doc)


def scan_file(path: Path):
    try:
        doc = json.loads(path.read_text())
    except (ValueError, OSError) as exc:
        return None, str(exc)
    findings = defaultdict(set)
    scan_document(doc, findings)
    return findings, None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--count", action="store_true",
                    help="show how many distinct values each path holds")
    ap.add_argument("--category", action="append", choices=CATEGORIES,
                    help="report only these categories")
    ap.add_argument("--all", action="store_true",
                    help="include quasi-identifiers (timestamps, clock times, "
                         "timezones) — a captured corpus is full of them")
    ap.add_argument("--baseline", help="file of reviewed, accepted findings")
    ap.add_argument("--update-baseline", metavar="FILE",
                    help="write the current findings to FILE and exit 0")
    args = ap.parse_args(argv)

    wanted = set(args.category or (CATEGORIES if args.all else DEFAULT_CATEGORIES))
    accepted = load_baseline(args.baseline)
    total = 0
    seen = set()
    for path in args.paths:
        findings, error = scan_file(path)
        if error:
            print(f"{path}: unreadable ({error})", file=sys.stderr)
            continue
        rows = sorted((p, c, len(v)) for (p, c), v in findings.items()
                      if c in wanted and (p, c) not in accepted)
        seen.update((p, c) for (p, c), _ in findings.items() if c in wanted)
        if not rows:
            continue
        print(f"{path}")
        for field, category, n in rows:
            suffix = f"  ({n} distinct)" if args.count else ""
            print(f"    {category:16s} {field}{suffix}")
            total += 1

    if args.update_baseline:
        lines = ["# Reviewed and accepted findings for tools/nsschema/scan_pii.py.",
                 "# One `path<TAB>category` per line. Regenerate with",
                 "# `python3 -m nsschema.scan_pii --update-baseline <file> <paths>`",
                 "# after reviewing every new entry — this file is an assertion that",
                 "# a human looked, not a way to silence the scanner.", ""]
        lines += [f"{p}\t{c}" for p, c in sorted(seen)]
        Path(args.update_baseline).write_text("\n".join(lines) + "\n")
        print(f"\nwrote {len(seen)} accepted findings to {args.update_baseline}")
        return 0

    if total:
        print(f"\n{total} unaccepted field/category findings. Values are "
              f"deliberately not printed.", file=sys.stderr)
        return 1
    print("no unaccepted findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
