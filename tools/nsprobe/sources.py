"""sources.py — read a pseudonymous corpus tree laid out by ``layout.py``.

Layout::

    <root>/<api>/<site>/<collection>.json

``<api>`` is ``v1`` or ``v3``. ``<site>`` is a pseudonym (``S001``...);
``layout.py`` refuses anything else. Every file is a JSON array of
documents, which is also the layout ``nsschema`` reads when
``NSSCHEMA_CORPUS`` points at ``<root>/<api>:flat_site``.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List

COLLECTIONS = ("entries", "treatments", "devicestatus", "profile", "activity",
               "food", "settings")
APIS = ("v1", "v3")
SITE_LABEL = re.compile(r"^S\d{3}$")


@dataclass(frozen=True)
class Source:
    api: str
    site: str
    collection: str
    path: Path


def discover(root: Path, collections=COLLECTIONS) -> List[Source]:
    found = []
    for api in APIS:
        base = root / api
        if not base.is_dir():
            continue
        for site_dir in sorted(p for p in base.iterdir() if p.is_dir()):
            if not SITE_LABEL.match(site_dir.name):
                raise ValueError(
                    f"{site_dir}: site directories must be pseudonyms "
                    "(S001, S002...). Run `nsprobe layout` first.")
            for collection in collections:
                path = site_dir / f"{collection}.json"
                if path.is_file() and path.stat().st_size > 0:
                    found.append(Source(api, site_dir.name, collection, path))
    return found


def iter_documents(path: Path) -> Iterator[dict]:
    """Documents from a file: a JSON array, a single object, or NDJSON.

    Reuses nsschema's incremental array decoder so that a 200 MB export is
    never materialised as one list.
    """
    from nsschema import corpus
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        head = fh.read(4096).lstrip()[:1]
    if head in ("[", ""):
        yield from corpus.iter_documents(path)
        return
    # One object, or one object per line.
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        obj = json.loads(text)
    except ValueError:
        for line in text.splitlines():
            line = line.strip()
            if line:
                doc = json.loads(line)
                if isinstance(doc, dict):
                    yield doc
        return
    yield from unwrap(obj)


def unwrap(obj) -> Iterator[dict]:
    """Documents inside a REST response, whichever API produced it.

    API v3 answers ``{"status": 200, "result": [...]}``; ``/history``
    answers the same shape. v1 answers a bare array. A dump tool may have
    saved either.
    """
    if isinstance(obj, list):
        for doc in obj:
            if isinstance(doc, dict):
                yield doc
    elif isinstance(obj, dict):
        result = obj.get("result")
        if isinstance(result, list) and "status" in obj:
            yield from unwrap(result)
        else:
            yield obj
