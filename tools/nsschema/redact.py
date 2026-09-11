"""redact.py — de-identification policy for census output.

The corpus is real Nightscout data from consenting sites. Field *names*,
*types*, *frequencies* and *numeric ranges* are the evidence we want;
field *values* are health data and must not leave the corpus except in
forms that cannot identify a person, a site, or a device.

Policy, applied to every value before it can appear in an artifact:

1. **Name denylist** — fields that are free text, identity, or hardware
   identity never have values recorded at all. Only length statistics.
2. **Cardinality cap** — a field whose observed distinct values exceed
   ``MAX_DISTINCT`` is marked high-cardinality and its value set dropped.
   Enum-like fields (``direction``, ``eventType``) survive; identifiers
   and free text do not.
2a. **Cross-site corroboration** — a value is only recorded if at least
   ``MIN_VALUE_SITES`` independent sites were seen to write it. This is the
   rule that distinguishes *vocabulary* from *personal data* structurally
   rather than by pattern: a shared vocabulary term is by definition used by
   more than one site, and a person's own text is not. It is enforced at
   output time, in ``census.FieldStat``, because it needs the per-site
   counts this module does not see.
3. **Shape rejection** — a value is dropped, whatever its field is called,
   if its *shape* is one that carries personal information rather than
   vocabulary: a timestamp, a clock time, a timezone, a reverse-DNS bundle
   identifier, or anything containing non-ASCII characters. The names of
   these fields are not predictable (``created_at``, ``bundleIdentifier``,
   ``overridePresets[].symbol``, ``store.{}.timezone`` and
   ``store.{}.basal[].time`` all reached the output of an earlier version
   of this module), so the check is on the value, not the key.
4. **Scrubbing** — any string that does survive still has digit runs,
   emails, URLs and long hex/base64 tokens masked, because device strings
   mix a useful model name with a serial number.
5. **Length cap** — strings longer than ``MAX_VALUE_LEN`` are never
   recorded verbatim, regardless of cardinality.

What each rejected shape would have revealed, in this corpus:

* timestamps — the exact millisecond a named site's profile was edited
* ``bundleIdentifier`` — an Apple Developer Team ID, i.e. the identity of
  the individual who built that copy of Loop
* override-preset symbols — a person's own emoji vocabulary, which
  fingerprints them across documents
* timezone and schedule times — location, and the shape of one person's
  insulin therapy day
* ``frameName1`` — the first names of the people a dashboard was set up to
  watch; caught by rule 2a, not by any shape rule
* ``apnsDeveloperTeamId`` — the same class of identity as
  ``bundleIdentifier``, in a field whose name suggests configuration

None of that is needed to know a field is a string.
"""

import re

MAX_DISTINCT = 60
MAX_VALUE_LEN = 64

# A value must be written by at least this many independent sites to be
# recorded. Three, not two: two sites sharing a value can simply be two
# installs built by the same person, which is how an Apple Developer Team ID
# survived a two-site threshold. Without it, a collection with few documents has no effective
# cardinality cap at all: `settings` holds one document per site, so every
# string in it is per-site free text that the distinct-value cap never
# reaches. That is how an earlier run recorded two people's first names
# from one site's `frameName1`/`frameName2` dashboard labels, and an Apple
# Developer Team ID from its `extendedSettings.loop.apnsDeveloperTeamId` —
# neither of which matches any personal *shape*, because both look exactly
# like ordinary vocabulary tokens.
MIN_VALUE_SITES = 3

# Final path segment (case-insensitive) whose values are never recorded.
_DENY_SEGMENTS = {
    "_id", "id", "identifier", "syncidentifier", "pumpid", "pumpserial",
    "serial", "serialnumber", "sn", "name", "profile", "defaultprofile",
    "notes", "note", "enteredby", "reason", "customtitle", "title",
    "url", "email", "token", "secret", "apisecret", "key", "password",
    "uuid", "guid", "transmitterid", "sensorid", "deviceid", "clientid",
    "ns_url", "hostname", "remoteaddress", "ip",
}

# Substring match on the full dotted path, for nested identity fields.
_DENY_SUBSTRINGS = ("secret", "password", "token", "apikey", "api_key")

# Suffix match on the final path segment. Identity fields are named far more
# variously than an exact-name list can track — `apnsDeveloperTeamId`,
# `bundleIdentifier` and `transmitterId` are all identity, and none of them
# is a name anyone would think to enumerate in advance.
_DENY_SUFFIXES = (
    "id", "identifier", "token", "secret", "key", "serial",
    "name", "url", "uri", "email", "host", "address",
)

# Value shapes that are personal data rather than vocabulary.
_TIMESTAMP = re.compile(r"(\d{4}|<n>)-\d{2}-\d{2}[T ]?|\d{2}/\d{2}/\d{4}")
_CLOCK_TIME = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
_REVERSE_DNS = re.compile(r"^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+){2,}$")
_ALPHA_GROUP = re.compile(r"^[A-Za-z][A-Za-z_-]*$")

_DIGIT_RUN = re.compile(r"\d{4,}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL = re.compile(r"https?://\S+")
_HEXTOKEN = re.compile(r"\b[0-9a-fA-F]{16,}\b")


def _timezone_names():
    """IANA timezone names, lowercased, for shape rejection."""
    try:
        from zoneinfo import available_timezones
        return {name.lower() for name in available_timezones()}
    except Exception:  # pragma: no cover — no tzdata on this host
        return set()


_TIMEZONES = _timezone_names()


def is_personal_shape(value: str) -> bool:
    """True if the value's shape makes it personal data, whatever its name.

    Field names do not predict this: a profile's ``created_at``, a Loop
    build's ``bundleIdentifier``, an override preset's ``symbol`` and a
    basal schedule's ``time`` are all ordinary-looking keys whose values
    identify a person, a device owner, or a place.
    """
    if any(ord(ch) > 127 for ch in value):
        return True                       # emoji and other personal glyphs
    if _TIMESTAMP.search(value):
        return True
    if _CLOCK_TIME.match(value):
        return True
    if value.lower() in _TIMEZONES:
        return True
    if _REVERSE_DNS.match(value):
        # Distinguish a bundle identifier (com.example.loopkit.Loop) from a
        # dotted version number (3.12.0.2): the former has alphabetic groups.
        groups = value.split(".")
        if sum(1 for g in groups if _ALPHA_GROUP.match(g)) >= 2:
            return True
    return False


def is_denied(path: str) -> bool:
    """True if this dotted path's values must never be recorded."""
    lower = path.lower()
    if any(s in lower for s in _DENY_SUBSTRINGS):
        return True
    segment = lower.rsplit(".", 1)[-1].rstrip("[]")
    if segment in _DENY_SEGMENTS:
        return True
    # Trailing digits are an index, not part of the name: Nightscout's
    # dashboard labels are frameName1..frameName8 and frameUrl1..frameUrl8.
    return segment.rstrip("0123456789").endswith(_DENY_SUFFIXES)


def scrub(value: str) -> str:
    """Mask identifying substructure inside a value we are about to record."""
    out = _URL.sub("<url>", value)
    out = _EMAIL.sub("<email>", out)
    out = _HEXTOKEN.sub("<hex>", out)
    out = _DIGIT_RUN.sub("<n>", out)
    return out


def recordable(path: str, value) -> bool:
    """True if this value may be held in the distinct-value set for ``path``."""
    if is_denied(path):
        return False
    if isinstance(value, str):
        return len(value) <= MAX_VALUE_LEN and not is_personal_shape(value)
    return isinstance(value, bool)
