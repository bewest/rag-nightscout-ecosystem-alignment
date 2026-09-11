"""tiers.py — classify census fields by strength of evidence.

The census says what exists; a tier says how much weight a schema decision
should put on it. The distinction that matters for Nightscout is *not* how
often a field appears overall — a single busy site can make a
vendor-specific field look common — but on **how many independent sites**
it appears, and whether the client on those sites writes it *every time*.

Tiers, in descending order of commitment:

``universal``
    Present on every site in the corpus, in essentially every document.
    Safe to mark ``required``; a validator that rejects its absence would
    reject nothing in the corpus.
``core``
    Present on most sites and most documents. Belongs in the typed schema
    with a declared type; not safe as ``required``.
``common``
    Independently observed on at least ``COMMON_MIN_SITES`` sites. Real,
    cross-client, but optional and often client-conditional.
``vendor``
    Concentrated on one or two sites, but written *consistently* there —
    the signature of one client that always emits the field. This is the
    population the ``x-aid-extensions`` proposal is about.
``sparse``
    Seen on one or two sites and not consistently. Document, do not type.
``rare``
    Fewer than ``RARE_MAX_DOCS`` occurrences in the whole corpus. Usually a
    one-off, a bug, or a hand-edited document.
"""

import math

UNIVERSAL_DOC_FREQ = 0.95
CORE_SITE_FRACTION = 0.6
CORE_DOC_FREQ = 0.10
COMMON_MIN_SITES = 3
VENDOR_SATURATION = 0.80
RARE_MAX_DOCS = 10


def classify(field, total_sites):
    """Return (tier, reason) for one census field record."""
    sites = field["site_count"]
    freq = field["doc_frequency"]
    docs = field["docs_present"]
    site_freq = field.get("site_frequency", {})
    saturated_sites = sum(1 for v in site_freq.values() if v >= VENDOR_SATURATION)

    if docs < RARE_MAX_DOCS:
        return "rare", f"{docs} documents in the whole corpus"

    if sites == total_sites and freq >= UNIVERSAL_DOC_FREQ:
        return "universal", f"all {total_sites} sites, {freq:.1%} of documents"

    if sites >= math.ceil(CORE_SITE_FRACTION * total_sites) and freq >= CORE_DOC_FREQ:
        return "core", f"{sites}/{total_sites} sites, {freq:.1%} of documents"

    if sites >= COMMON_MIN_SITES:
        return "common", f"{sites}/{total_sites} sites, {freq:.1%} of documents"

    if saturated_sites >= 1:
        return "vendor", (
            f"{sites}/{total_sites} sites, but written in "
            f"{max(site_freq.values()):.0%} of documents on {saturated_sites} of them"
        )

    return "sparse", f"{sites}/{total_sites} sites, {freq:.2%} of documents"


def annotate(census):
    """Add a ``tier`` and ``tier_reason`` to every field of a census dict."""
    total_sites = len(census["sites"])
    for field in census["fields"]:
        tier, reason = classify(field, total_sites)
        field["tier"] = tier
        field["tier_reason"] = reason
    return census


ORDER = ("universal", "core", "common", "vendor", "sparse", "rare")
