"""corpus.py — discover raw Nightscout JSON snapshots under externals/.

A *snapshot* is one dated collection pass over a set of sites. A *site* is
one Nightscout instance, identified only by the single-letter pseudonym the
collection pass assigned it; no site URL, hostname or token is ever read by
this module.

Known layouts::

    externals/ns-data/patients/<site>/raw/<collection>.json
    externals/ns-resync-<date>/raw/<site>/<collection>.json

Both hold the Nightscout REST response verbatim: a JSON array of documents
(``profile.json`` is an array of profile documents; ``settings.json`` is the
single ``/api/v1/status.json`` object).
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List

COLLECTIONS = ("entries", "treatments", "devicestatus", "profile", "settings")

# Snapshot roots, in collection order. Each entry is (snapshot_id, root, layout).
#   layout "site_dir"  -> <root>/<site>/raw/<collection>.json
#   layout "flat_site" -> <root>/<site>/<collection>.json
SNAPSHOTS = (
    ("2026-04-01", "externals/ns-data/patients", "site_dir"),
    ("2026-04-26", "externals/ns-resync-2026-04-26/raw", "flat_site"),
)


@dataclass(frozen=True)
class Source:
    snapshot: str
    site: str
    collection: str
    path: Path

    @property
    def label(self) -> str:
        return f"{self.snapshot}/{self.site}/{self.collection}"


def discover(repo_root: Path, collections=COLLECTIONS) -> List[Source]:
    """Enumerate every readable (snapshot, site, collection) JSON file."""
    found: List[Source] = []
    for snapshot, rel, layout in SNAPSHOTS:
        root = repo_root / rel
        if not root.is_dir():
            continue
        for site_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            base = site_dir / "raw" if layout == "site_dir" else site_dir
            if not base.is_dir():
                continue
            for collection in collections:
                path = base / f"{collection}.json"
                if path.is_file() and path.stat().st_size > 0:
                    found.append(Source(snapshot, site_dir.name, collection, path))
    return found


def iter_documents(path: Path) -> Iterator[dict]:
    """Yield documents from a Nightscout REST response file.

    Reads the file as one string, then decodes documents incrementally with
    ``raw_decode`` so that only one document dict is live at a time. The
    largest file in the corpus is ~225 MB, which this handles in well under
    1 GB of peak RSS; ``json.load`` on the same file would materialize every
    document at once.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    decoder = json.JSONDecoder()
    i = 0
    n = len(text)

    def skip_ws(j: int) -> int:
        while j < n and text[j] in " \t\r\n":
            j += 1
        return j

    i = skip_ws(i)
    if i >= n:
        return
    if text[i] != "[":
        # A bare object (settings.json / status.json).
        obj, _ = decoder.raw_decode(text, i)
        if isinstance(obj, dict):
            yield obj
        return

    i = skip_ws(i + 1)
    if i < n and text[i] == "]":
        return
    while i < n:
        obj, end = decoder.raw_decode(text, i)
        if isinstance(obj, dict):
            yield obj
        i = skip_ws(end)
        if i >= n or text[i] == "]":
            return
        if text[i] == ",":
            i = skip_ws(i + 1)
        else:
            raise ValueError(f"{path}: unexpected {text[i]!r} at offset {i}")


def repo_root() -> Path:
    return Path(os.environ.get("NSSCHEMA_ROOT", Path(__file__).resolve().parents[2]))
