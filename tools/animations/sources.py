"""What each animation is drawn from, and the hashes the committed render was made from.

Plain Python (no manim), so the drift test runs where manim is not installed. Each animation names
its scene file, its scene class and its inputs. An input is a repository path, hashed whole, or a
(path, rule ids) pair for a specification whose rule table supplies only the rules' bold names: then
only those names are hashed, so an edit elsewhere in the specification does not make the animation
stale, and an edit to a name it shows does.

render.py writes docs/30-design/platform/animations/<name>.sources.json at render time;
test_animations.py recomputes every hash and fails naming each animation whose sources changed.
"""
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = REPO / "docs" / "30-design" / "platform" / "animations"

AS_CASES = "specs/sync/conformance/active-state"
COMMON = ["tools/animations/common.py", "tools/animations/sources.py", "tools/diagrams/svgkit.py"]

# rule -> case, in the order the animation shows them
SPAN_CASES = [("A5", "zero-duration-ends-instance"), ("A6", "deleted-before-start"),
              ("A7", "backfill-supersedes-by-start"), ("A8", "overlay-returns-to-open-ended")]

ANIMATIONS = {
    "active-state-spans": {
        "scene": "tools/animations/active_state_spans.py",
        "class": "ActiveStateSpans",
        "inputs": COMMON + [
            "tools/diagrams/active_state_rules.py",
            "tools/nsschema/active_state.py",
            *[f"{AS_CASES}/{c}.yaml" for _, c in SPAN_CASES],
            ("docs/30-design/platform/spec/state-intent.md", [r for r, _ in SPAN_CASES]),
        ],
    },
}


def rule_names(text, ids):
    """The bold name of each rule row `| ID | **Name.** ... |`, in the order asked."""
    out = []
    for rid in ids:
        m = re.search(r"^\| " + re.escape(rid) + r" \| \*\*(.+?)\*\*", text, re.M)
        if not m:
            raise SystemExit(f"rule {rid} not found")
        out.append(f"{rid} {m.group(1)}")
    return out


def digest(entry, root=REPO, swap=None):
    """(key, sha256) for one input. swap maps a repo-relative path to a file read in its place."""
    swap = swap or {}
    path, ids = (entry, None) if isinstance(entry, str) else entry
    src = Path(swap.get(path, root / path))
    if ids is None:
        return path, hashlib.sha256(src.read_bytes()).hexdigest()
    names = "\n".join(rule_names(src.read_text(), ids)).encode()
    return f"{path} rules {','.join(ids)}", hashlib.sha256(names).hexdigest()


def manifest(name, root=REPO, swap=None):
    a = ANIMATIONS[name]
    files = dict(digest(e, root, swap) for e in [a["scene"]] + a["inputs"])
    return {"animation": name, "scene": a["scene"], "class": a["class"], "sha256": files}


def sidecar(name):
    return OUT / f"{name}.sources.json"


def stale(swap=None):
    """Animations whose committed sidecar differs from what their sources hash to now."""
    out = []
    for name in ANIMATIONS:
        p = sidecar(name)
        if not p.exists() or json.loads(p.read_text()) != manifest(name, swap=swap):
            out.append(name)
    return out
