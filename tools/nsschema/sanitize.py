"""sanitize.py — mask personal data in committed JSON while keeping it usable.

``scan_pii.py`` finds personal data in files already in the repo. This
rewrites it. The constraint that shapes every rule: a test fixture exists to
exercise parsing, normalization and dosing maths, so a replacement must keep
the *shape* of a value — its type, length class and equality relationships —
while destroying its link to a person or a device.

Design:

* **Deterministic.** The same input maps to the same output everywhere, so
  cross-file joins survive: a profile ``_id`` shared by two fixtures stays
  shared after masking.
* **Shape-preserving.** A 24-character ObjectId becomes a 24-character hex
  string; a UUID becomes a UUID; a 44-character device token becomes 44
  hex characters. Parsers that care about format keep working.
* **Not reversible in practice.** Replacements are derived by HMAC over the
  original with a fixed, published salt. That is not a secret-keeping
  scheme — it is a stable pseudonym. It is safe here because every masked
  input is high-entropy (tokens, ObjectIds, UUIDs); low-entropy values such
  as override names are replaced by counters instead, which carry no
  information about the original at all.

What is deliberately **not** masked, and why:

* **Timestamps.** Every grid, window and IOB test depends on them, and
  shifting them consistently across four collections and three snapshots
  risks breaking derived assertions in ways a test suite would not
  necessarily catch. They are pseudonymous event times in a test artifact.
* **Therapy values and schedules** — basal rates, ISF, carb ratio, target
  ranges and their times of day. These are the substance the fixtures
  exist to test, and on their own they are clinical rather than
  identifying.
* **Algorithm reason strings** (``openaps.suggested.reason``) — structural
  output that dosing tests read.
* **Vocabulary** — ``eventType``, ``direction``, ``units``, pump
  manufacturer and model, client and product names.

Both of those lists are judgement calls, recorded here so they can be
disputed rather than discovered.

Usage::

    python3 -m nsschema.sanitize --dry-run tools/ns2parquet/fixtures/*.json
    python3 -m nsschema.sanitize --write  tools/ns2parquet/fixtures/*.json
"""

import argparse
import hashlib
import hmac
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

# Published, not secret: the point is a stable pseudonym, not confidentiality.
SALT = b"nsschema-fixture-pseudonym-v1"

_HEX24 = re.compile(r"^[0-9a-f]{24}$")
_HEX_RUN = re.compile(r"^[0-9a-fA-F]{16,}$")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                   r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
# Long opaque tokens that are not hex: base64-ish sync identifiers.
_OPAQUE_RUN = re.compile(r"^[A-Za-z0-9_\-+/=]{24,}$")
_URL = re.compile(r"^https?://")  # shape check only; never a masking trigger
# Apple Developer Team IDs are ten upper-case alphanumerics. They appear
# inside bundle identifiers as their own dotted component.
_TEAM_ID = re.compile(r"^[A-Z0-9]{10}$")
# A serial appended to a device string: "Dexcom G7 DXCM3Y". Five or more
# characters, upper-case alphanumeric, mixing letters and digits — which
# excludes model tokens like G6, G7, Dash and protocol strings like share2.
_SERIAL_TOKEN = re.compile(r"^(?=.*[A-Z])(?=.*\d)[A-Z0-9]{5,}$")

# Final path segment -> rule. Checked case-insensitively, trailing digits
# stripped, so frameName1..frameName8 all match "framename".
RULES = OrderedDict([
    # Credentials first: these are the ones that matter most.
    ("devicetoken", "credential"),
    ("apnsdeveloperteamid", "credential"),
    ("teamid", "credential"),
    ("apisecret", "credential"),
    ("token", "credential"),
    ("secret", "credential"),
    ("password", "credential"),
    ("bundleidentifier", "bundle-id"),
    # Identity that must stay join-stable.
    ("_id", "opaque-id"),
    ("id", "opaque-id"),
    ("identifier", "opaque-id"),
    ("syncidentifier", "opaque-id"),
    # Hardware serials are declared identity by their field name, so they
    # are masked whatever they look like. The value-shape guard on
    # `opaque-id` exists to protect human-readable test names, and a pump
    # serial like "175F78A9" is short enough to slip through it.
    ("pumpid", "serial"),
    ("pumpserial", "serial"),
    ("serial", "serial"),
    ("serialnumber", "serial"),
    ("transmitterid", "serial"),
    ("sensorid", "serial"),
    ("uuid", "opaque-id"),
    ("guid", "opaque-id"),
    # Free text a person wrote.
    ("customtitle", "label"),
    ("notes", "label"),
    ("note", "label"),
    ("framename", "label"),
    ("symbol", "symbol"),
    ("frameurl", "url"),
    ("baseurl", "url"),
])

# Values that are ecosystem vocabulary rather than a person's device name.
KNOWN_CLIENTS = frozenset({
    "loop", "trio", "androidaps", "aaps", "xdrip", "xdrip+", "xdrip4ios",
    "openaps", "nightscout", "spike", "diable", "nightguard", "iphone",
    "loop://iphone", "xdripswift", "libre", "dexcom",
})

# Dotted-path suffixes whose values are a person's own words.
LABEL_PATHS = (
    "overridepresets[].name", "scheduleoverride.name", "presets[].name",
    "override.name",
)

# Path components that mark *derived* test material — algorithm inputs,
# expected outputs, vector metadata — rather than a captured Nightscout
# document. A `reason` here is an algorithm's output that a conformance
# test compares against, and an `id` is a human-readable test name. Masking
# either destroys the artifact without protecting anyone.
DERIVED_CONTEXTS = frozenset({
    "testcases", "test_cases", "testresults", "vectors", "files", "expected",
    "comparison", "originaloutput", "oref0_output", "actual", "metadata",
    "results", "scenario", "assertions",
})
# `reason` is a person's words on a treatment and an algorithm's output on a
# device status. Only the first is masked.
ALGORITHM_REASON_PREFIXES = ("openaps.", "loop.", "suggested.", "enacted.")
PERSON_DEVICE_PATHS = ("uploader.name",)
DEVICE_STRING_PATHS = ("device",)
ENTEREDBY_PATHS = ("enteredby",)


class Masker:
    """Stable value replacement, with counters for low-entropy values."""

    def __init__(self):
        self.counters = {}
        self.assigned = {}
        self.changes = []

    def _counter(self, kind, value):
        key = (kind, value)
        if key not in self.assigned:
            self.counters[kind] = self.counters.get(kind, 0) + 1
            self.assigned[key] = self.counters[kind]
        return self.assigned[key]

    @staticmethod
    def _digest(value):
        return hmac.new(SALT, value.encode("utf-8"), hashlib.sha256).hexdigest()

    def credential(self, value):
        # Same length, same alphabet: a token parser cannot tell the
        # difference, and nothing of the original survives.
        digest = self._digest(value)
        while len(digest) < len(value):
            digest += self._digest(digest)
        return digest[:len(value)]

    def bundle_id(self, value):
        """Keep the app's own name, drop everyone's namespace.

        Real values seen: ``com.<TEAMID>.loopkit.Loop``,
        ``org.nightscout.<TEAMID>.trio``, ``org.<person>.<build>.Loop``. The
        Team ID is the clearest identity, but the organisation component is
        identifying too when a person builds under their own namespace, so
        only the final component — the app — survives.
        """
        parts = [p for p in value.split(".") if p and not _TEAM_ID.match(p)]
        return f"com.example.{parts[-1]}" if parts else "com.example.app"

    def opaque_id(self, value):
        """Mask only values that actually look like machine identifiers.

        Conformance vectors name their cases `COB-001`, `IOB-003`,
        `LV-175-2026-02-03`. Those are documentation, not identity, and
        replacing them destroys the vector's readability while protecting
        nobody. Only UUIDs, ObjectIds and long hex/opaque runs are masked.
        """
        if not (_UUID.match(value) or _HEX24.match(value)
                or _HEX_RUN.match(value) or _OPAQUE_RUN.match(value)):
            return value
        digest = self._digest(value)
        if _UUID.match(value):
            h = digest[:32]
            return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}".upper() \
                if value[0].isupper() or value[:8].upper() == value[:8] else \
                f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
        if _HEX24.match(value):
            return digest[:24]
        if _HEX_RUN.match(value):
            out = digest
            while len(out) < len(value):
                out += self._digest(out)
            return out[:len(value)]
        # Unreachable for unmatched shapes: those returned early above.
        out = digest
        while len(out) < len(value):
            out += self._digest(out)
        return out[:len(value)]

    def serial(self, value):
        """Same length and alphabet class, no relation to the original."""
        digest = self._digest(value)
        alphabet = "0123456789ABCDEF" if value.isupper() else "0123456789abcdef"
        out = "".join(alphabet[int(c, 16)] for c in digest)
        while len(out) < len(value):
            out += out
        return out[:len(value)]

    def label(self, value):
        return f"Label {self._counter('label', value)}"

    def symbol(self, value):
        return f"[{self._counter('symbol', value)}]"

    def url(self, value):
        return "" if not value else "https://example.invalid/frame"

    def person_device(self, value):
        return value if value.strip().lower() in KNOWN_CLIENTS else \
            f"device-{self._counter('device', value):02d}"

    def device_string(self, value):
        """Strip an appended hardware serial. Keep everything else.

        `device` drives controller detection in the analysis pipeline and is
        core schema evidence, so it is stripped as little as possible: only
        serial-shaped tokens, which are unambiguous by pattern
        ("Dexcom G7 <serial>").

        An earlier version also masked any token it did not recognise as
        technology, on the theory that free text in a device string is
        usually a person — LibreLinkUp does surface a connection's display
        name. Every value it actually touched was a false positive: "Zukka
        (LibreLinkUp)" is a bridge app, "Sony SO-53B" is a phone model, and
        "device" is a placeholder in a public research export. Three for
        three, destroying exactly the ecosystem evidence this corpus exists
        to record. A vocabulary cannot keep up with the bridge apps people
        write, and masking is a one-way door on evidence.

        A personal name in a device string remains possible. It is handled
        by review rather than by guessing: `scan_pii.py` reports device
        strings whose tokens it does not recognise, for a human to judge.
        """
        tokens = [t for t in value.split() if not _SERIAL_TOKEN.match(t)]
        return " ".join(tokens) if tokens else "device"

    def entered_by(self, value):
        low = value.strip().lower()
        if low in KNOWN_CLIENTS or low.startswith(("loop://", "openaps://")):
            return value
        return f"uploader-{self._counter('enteredby', value):02d}"


def in_derived_context(path):
    """True if the path sits inside derived test material, not a document."""
    return any(part.rstrip("[]") in DERIVED_CONTEXTS
               for part in path.lower().split("."))


def rule_for(path):
    """Return the rule name for a dotted path, or None."""
    low = path.lower()
    if low.endswith("reason") or low.endswith("reason[]"):
        if any(pre in low for pre in ALGORITHM_REASON_PREFIXES):
            return None
        return None if in_derived_context(low) else "label"
    for suffix in LABEL_PATHS:
        if low.endswith(suffix):
            return "label"
    for suffix in PERSON_DEVICE_PATHS:
        if low.endswith(suffix):
            return "person-device"
    segment = low.rsplit(".", 1)[-1].rstrip("[]")
    if segment in ENTEREDBY_PATHS:
        return "entered-by"
    if segment in DEVICE_STRING_PATHS:
        return "device-string"
    stripped = segment.rstrip("0123456789")
    for name, rule in RULES.items():
        if segment == name or stripped == name:
            if rule == "label" and in_derived_context(low):
                return None
            return rule
    return None


def apply_rule(masker, rule, value):
    return {
        "credential": masker.credential,
        "bundle-id": masker.bundle_id,
        "opaque-id": masker.opaque_id,
        "serial": masker.serial,
        "label": masker.label,
        "symbol": masker.symbol,
        "url": masker.url,
        "person-device": masker.person_device,
        "device-string": masker.device_string,
        "entered-by": masker.entered_by,
    }[rule](value)


# When set, only these rules run. See --only.
_ONLY_RULES = None


def transform(doc, masker, prefix=""):
    if isinstance(doc, dict):
        return {k: transform(v, masker, f"{prefix}.{k}" if prefix else k)
                for k, v in doc.items()}
    if isinstance(doc, list):
        return [transform(v, masker, f"{prefix}[]") for v in doc]
    if isinstance(doc, str) and doc:
        # Only fields named as a dashboard frame or a site base URL are
        # masked. A blanket "any http(s) value" rule rewrites lockfile
        # repository URLs and JSON Schema $id keywords, which are not
        # personal data and whose values are load-bearing.
        rule = rule_for(prefix)
        if rule and _ONLY_RULES is not None and rule not in _ONLY_RULES:
            rule = None
        if rule:
            replaced = apply_rule(masker, rule, doc)
            if replaced != doc:
                masker.changes.append((prefix, rule))
                return replaced
    return doc


def sanitize_file(path: Path, write=False):
    original = path.read_text()
    try:
        doc = json.loads(original)
    except ValueError as exc:
        return None, str(exc)
    masker = Masker()
    out = transform(doc, masker)
    if not masker.changes:
        return masker, None
    if write:
        # Preserve the file's separator style: these fixtures are compact.
        compact = "\n" not in original[:2000] or original.count("\n") < 5
        text = json.dumps(out, separators=(",", ":")) if compact else \
            json.dumps(out, indent=1)
        path.write_text(text + ("\n" if original.endswith("\n") else ""))
    return masker, None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", type=Path)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="rewrite files in place")
    group.add_argument("--dry-run", action="store_true", help="report only")
    ap.add_argument("--only", action="append", dest="only",
                    help="apply only these rules (repeatable), leaving every "
                         "other value untouched — used to add a rule without "
                         "re-masking what earlier passes already handled")
    args = ap.parse_args(argv)

    if args.only:
        globals()["_ONLY_RULES"] = frozenset(args.only)

    totals = {}
    touched = 0
    for path in args.paths:
        masker, error = sanitize_file(path, write=args.write)
        if error:
            print(f"{path}: unreadable ({error})", file=sys.stderr)
            continue
        if not masker.changes:
            continue
        touched += 1
        by_rule = {}
        for _field, rule in masker.changes:
            by_rule[rule] = by_rule.get(rule, 0) + 1
            totals[rule] = totals.get(rule, 0) + 1
        summary = ", ".join(f"{r}:{n}" for r, n in sorted(by_rule.items()))
        print(f"{'rewrote' if args.write else 'would rewrite'} {path}  ({summary})")

    print(f"\n{touched} file(s), {sum(totals.values())} value(s) replaced: "
          + ", ".join(f"{r}={n}" for r, n in sorted(totals.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
