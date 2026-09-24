"""layout.py — copy raw per-site exports into a pseudonymous corpus tree.

Input is whatever the data holder already has, one directory per site::

    <src>/<any-site-name>/<collection>.json            (API v1 assumed)
    <src>/<any-site-name>/v1/<collection>.json
    <src>/<any-site-name>/v3/<collection>.json
    <src>/<any-site-name>/<collection>/<page>.json     (pages, concatenated)

Files may be JSON arrays, v3 ``{"status","result"}`` envelopes, or NDJSON.

Output is ``<dest>/<api>/S001/<collection>.json``, always a JSON array. Site
directory names are replaced by ``S001``, ``S002``... in sorted order of the
original names; the mapping is written to ``--key`` and nowhere else. The
key file identifies people. It stays with the data holder and is never part
of a result.

Documents are copied verbatim. Nothing is deduplicated: duplicates are one
of the things the probes measure. Pages that overlap will therefore show up
as ``same _id`` repeats in probe Q08; ``layout`` prints the count per site
so a paging artefact can be told apart from an upload duplicate.
"""

import json
import sys
from collections import Counter
from pathlib import Path

from . import sources

ALIASES = {
    "entries": "entries", "sgv": "entries", "glucose": "entries",
    "treatments": "treatments",
    "devicestatus": "devicestatus", "device_status": "devicestatus",
    "profile": "profile", "profiles": "profile",
    "activity": "activity",
    "food": "food",
    "settings": "settings", "status": "settings",
}


def _collection_of(name: str):
    stem = name.lower().split(".")[0]
    return ALIASES.get(stem)


def _site_inputs(site_dir: Path):
    """Yield (api, collection, [files]) for one site's raw directory."""
    # Loose files at the site root are API v1 unless a v1/ directory exists.
    v1 = site_dir / "v1" if (site_dir / "v1").is_dir() else site_dir
    apis = [("v1", v1)] + [(a, site_dir / a) for a in sources.APIS[1:]
                           if (site_dir / a).is_dir()]
    for api, base in apis:
        grouped = {}
        for entry in sorted(base.iterdir()):
            coll = _collection_of(entry.name)
            if coll is None:
                continue
            if entry.is_dir():
                files = sorted(p for p in entry.rglob("*")
                               if p.is_file() and p.suffix in (".json", ".ndjson", ".jsonl"))
            elif entry.suffix in (".json", ".ndjson", ".jsonl"):
                files = [entry]
            else:
                continue
            grouped.setdefault(coll, []).extend(files)
        for coll, files in grouped.items():
            yield api, coll, files


def layout(src: Path, dest: Path, key: Path, force=False):
    sites = sorted(p for p in src.iterdir() if p.is_dir())
    if not sites:
        raise SystemExit(f"{src}: no site directories found")
    if key.resolve().is_relative_to(dest.resolve()):
        raise SystemExit("--key must be outside --dest: the key identifies "
                         "people and dest is what the probes read")
    if dest.exists() and any(dest.iterdir()) and not force:
        raise SystemExit(f"{dest} is not empty; pass --force to overwrite")

    mapping = {}
    summary = []
    for n, site_dir in enumerate(sites, 1):
        label = f"S{n:03d}"
        mapping[label] = site_dir.name
        for api, coll, files in _site_inputs(site_dir):
            out = dest / api / label / f"{coll}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            ids = Counter()
            count = 0
            with open(out, "w", encoding="utf-8") as fh:
                fh.write("[")
                for f in files:
                    for doc in sources.iter_documents(f):
                        if count:
                            fh.write(",\n")
                        fh.write(json.dumps(doc, separators=(",", ":")))
                        count += 1
                        _id = doc.get("_id") or doc.get("identifier")
                        if isinstance(_id, str):
                            ids[_id] += 1
                fh.write("]\n")
            repeats = sum(v - 1 for v in ids.values() if v > 1)
            summary.append((label, api, coll, count, repeats))

    key.parent.mkdir(parents=True, exist_ok=True)
    key.write_text(json.dumps(mapping, indent=1) + "\n")

    print(f"{len(sites)} sites -> {dest}   (key: {key} -- keep private)")
    for label, api, coll, count, repeats in summary:
        flag = f"  {repeats} repeated _id" if repeats else ""
        print(f"  {label} {api} {coll:13s} {count:9d}{flag}")
    return mapping


def main(args):
    layout(Path(args.src), Path(args.dest), Path(args.key), force=args.force)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit("run as: python3 -m nsprobe layout ...")
