"""family.py — which kind of client wrote a document.

A probe that says "Trio writes X" is only as good as the rule that decided a
document came from Trio, so the rule is written down here, runs the same way
on every data set, and reports which signal fired (``signal``) alongside the
answer (``family``). A disagreement between his classifier and this one is a
finding, not noise.

Families: ``aaps``, ``trio``, ``iaps``, ``oref0-rig``, ``loop``, ``xdrip``,
``xdrip4ios``, ``share``, ``librelink``, ``nightscout-connect``,
``redacted`` (the holder scrubbed the string before export), ``other``,
``unknown``.

Signals are read from the device string (``device``, else ``enteredBy``) and
from document shape. The raw strings are never emitted: a device string
carries serial numbers and rig hostnames.

Sources for each rule (read from code at the pins in workspace.lock.json):

* AAPS devicestatus ``device`` is ``openaps://<manufacturer> <model>``
  (AndroidAPS LoopPlugin), treatments ``enteredBy`` is ``openaps://AndroidAPS``.
* oref0 rigs write ``openaps://<hostname>`` — no space, no AndroidAPS.
* Trio writes ``Trio``; iAPS/FreeAPS X write ``iAPS``/``freeaps``.
* Loop writes ``loop://<device>`` and a top-level ``loop`` object in
  devicestatus.
"""

import re

_OPENAPS = re.compile(r"^openaps://", re.I)


def _device_string(doc):
    for key in ("device", "enteredBy"):
        v = doc.get(key)
        if isinstance(v, str) and v:
            return key, v
    return None, ""


def classify(doc, collection):
    """Return (family, signal). ``signal`` names the rule, never the value."""
    if collection == "devicestatus":
        if isinstance(doc.get("loop"), dict):
            return "loop", "shape:loop"
    key, s = _device_string(doc)
    low = s.lower()
    if key:
        if low.startswith("redacted") or low in ("<redacted>", "[redacted]"):
            return "redacted", f"{key}:redacted"
        if "androidaps" in low:
            return "aaps", f"{key}:androidaps"
        if "trio" in low:
            return "trio", f"{key}:trio"
        if "iaps" in low or "freeaps" in low:
            return "iaps", f"{key}:iaps"
        if _OPENAPS.match(s):
            rest = s[len("openaps://"):]
            # AAPS: "<manufacturer> <model>" (has a space); rig: a hostname.
            if " " in rest.strip():
                return "aaps", f"{key}:openaps-space"
            return "oref0-rig", f"{key}:openaps-host"
        if low.startswith("loop://") or low == "loop":
            return "loop", f"{key}:loop"
        if "xdrip4ios" in low or "xdripswift" in low:
            return "xdrip4ios", f"{key}:xdrip4ios"
        if "xdrip" in low:
            return "xdrip", f"{key}:xdrip"
        if "share2" in low or "dexcom" in low or low.startswith("dxcm"):
            return "share", f"{key}:share"
        if "librelink" in low or "llu" in low:
            return "librelink", f"{key}:librelink"
        if "nightscout-connect" in low or "nightscout connect" in low:
            return "nightscout-connect", f"{key}:ns-connect"
    if collection == "devicestatus" and isinstance(doc.get("openaps"), dict):
        return "unknown", "shape:openaps-no-device"
    if collection == "entries" and key is None and (
            "filtered" in doc and "unfiltered" in doc):
        return "xdrip", "shape:raw-filtered"
    return ("other", f"{key}:unmatched") if key else ("unknown", "none")


def site_family(counts):
    """A site's dominant closed-loop family from its devicestatus families."""
    loops = {f: n for f, n in counts.items()
             if f in ("aaps", "trio", "iaps", "oref0-rig", "loop")}
    if not loops:
        return "none"
    total = sum(counts.values())
    best, n = max(loops.items(), key=lambda kv: kv[1])
    return best if n >= 0.2 * total else "mixed"
