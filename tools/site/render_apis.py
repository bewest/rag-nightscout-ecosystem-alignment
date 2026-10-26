#!/usr/bin/env python3
"""Render the API reference pages in site/pages/ from OpenAPI files, with Redoc.

Every entry in site/pages/pages.yaml whose `render` is this script is an API
page. Besides the living-page keys (`sources`: exactly one OpenAPI file), each
carries an `api:` block:

    api:
      status: current | de-facto | proposed | draft-pr | superseded
      note: one sentence a reader needs before trusting the page
      see: optional tracked .md path the banner links to (e.g. the design that
           replaces a superseded file), opened on the site

For each page the script lints the source with the pinned Redocly CLI and
refuses to render on any lint error (warnings are printed), then builds the
page with `redocly build-docs` and tools/site/redoc-template.hbs: a status
banner naming the source file and the commit that last changed it, and the
Redoc runtime from jsDelivr at the pinned version with its integrity hash.
Redoc draws a schema only where an operation refers to it, so the page is
built from a copy of the source with a "Schemas" group that names every
schema in `components.schemas` (Redoc's SchemaDefinition); a file of schemas
with no operations would otherwise render as its description alone. The
source file is not changed, and lint runs on it, not on the copy.

    tools/site/.venv/bin/python tools/site/render_apis.py            # all pages
    tools/site/.venv/bin/python tools/site/render_apis.py NAME.html  # one page

Then set each page's `source_commit` in site/pages/pages.yaml to the commit the
script prints. Needs node/npx and network on first run (npx caches the CLI).
To move the pin, change REDOCLY_CLI, then REDOC_URL and REDOC_SRI to the Redoc
version that CLI bundles (`npm ls redoc` in its npx cache) and the sha384 of
that file.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
PAGES = REPO / "site/pages"
TEMPLATE = REPO / "tools/site/redoc-template.hbs"
GITHUB_REPO = "https://github.com/bewest/rag-nightscout-ecosystem-alignment"
REDOCLY_CLI = "@redocly/cli@1.34.0"
# build-docs writes the runtime as a script from cdn.redocly.com; the same bytes
# (sha256 2c0d3cb1a32e2417..., checked 2026-10-26) are served by jsDelivr, which
# the site already allows, and the hash pins them.
REDOC_CDN = "https://cdn.redocly.com/redoc/v2.4.0/bundles/redoc.standalone.js"
REDOC_URL = "https://cdn.jsdelivr.net/npm/redoc@2.4.0/bundles/redoc.standalone.js"
REDOC_SRI = "sha384-4v3wCasB17vfeckkA8KRSPd9Lc58k/TgMXEcNFq0jeMRGcwHUunHDHkTHo+q2XZ3"
STATUS = {
    "current": "Current API",
    "de-facto": "De facto, 2025",
    "proposed": "Proposed",
    "draft-pr": "Unmerged pull request",
    "superseded": "Superseded",
}


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], check=True, capture_output=True, text=True).stdout.strip()


def npx(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["npx", "-y", REDOCLY_CLI, *args], cwd=REPO, capture_output=True, text=True)


def with_schema_section(doc: dict) -> dict:
    """The document plus one tag per component schema, grouped under "Schemas"."""
    schemas = list(((doc.get("components") or {}).get("schemas") or {}))
    if not schemas or "x-tagGroups" in doc:
        return doc
    op_tags = []
    for item in (doc.get("paths") or {}).values():
        for op in (item or {}).values():
            for t in (op.get("tags") or []) if isinstance(op, dict) else []:
                if t not in op_tags:
                    op_tags.append(t)
    # every operation tag must be in a group, or Redoc hides its operations
    declared = [t["name"] for t in doc.get("tags") or []]
    declared += [t for t in op_tags if t not in declared]
    doc = dict(doc)
    doc["tags"] = list(doc.get("tags") or []) + [
        {"name": f"schema-{n}", "x-displayName": n,
         "description": f'<SchemaDefinition schemaRef="#/components/schemas/{n}" />'} for n in schemas]
    groups = [{"name": "Operations", "tags": declared}] if declared else []
    doc["x-tagGroups"] = groups + [{"name": "Schemas", "tags": [f"schema-{n}" for n in schemas]}]
    return doc


def render(name: str, entry: dict) -> str:
    api = entry.get("api") or {}
    sources = entry.get("sources") or []
    if len(sources) != 1:
        raise SystemExit(f"{name}: an API page needs exactly one source, has {len(sources)}")
    src = sources[0]
    status = api.get("status")
    if status not in STATUS:
        raise SystemExit(f"{name}: api.status must be one of {', '.join(STATUS)}, got {status!r}")
    if not api.get("note"):
        raise SystemExit(f"{name}: api.note is required")
    if git("status", "--porcelain", "--", src):
        raise SystemExit(f"{name}: {src} has uncommitted changes; commit it first, so the banner's commit is true")
    commit = git("log", "-1", "--format=%h", "--", src)
    if not commit:
        raise SystemExit(f"{name}: {src} is not committed")

    lint = npx("lint", src, "--format=stylish")
    print(lint.stdout.strip() or lint.stderr.strip())
    if lint.returncode != 0:
        raise SystemExit(f"{name}: {src} fails lint; not rendered")

    see = api.get("see")
    if see and (not see.endswith(".md") or not git("ls-files", "--", see)):
        raise SystemExit(f"{name}: api.see must be a tracked .md file, got {see!r}")
    out = PAGES / name
    opts = {
        "status": status,
        "statusLabel": STATUS[status],
        "note": " " + api["note"].strip(),
        "source": src,
        "sourceUrl": f"{GITHUB_REPO}/blob/{commit}/{src}",
        "sourceCommit": commit,
        # the site keeps the repo layout and builds page.md as page.html; pages sit two levels down
        "seeUrl": "../../" + see[:-3] + ".html" if see else "",
        "seeLabel": see or "",
    }
    # beside the source, so its relative $refs to sibling files resolve; removed afterwards
    with tempfile.TemporaryDirectory(dir=(REPO / src).parent, prefix=".render-") as tmp:
        spec = Path(tmp).parent / (Path(tmp).name + ".json")
        spec.write_text(json.dumps(with_schema_section(yaml.safe_load((REPO / src).read_text(encoding="utf-8"))),
                                   default=str), encoding="utf-8")
        args = ["build-docs", str(spec), "-o", str(out), "-t", str(TEMPLATE), "--disableGoogleFont"]
        args += [f"--templateOptions.{k}={v}" for k, v in opts.items() if v]
        try:
            built = npx(*args)
        finally:
            spec.unlink(missing_ok=True)
    if built.returncode != 0:
        raise SystemExit(f"{name}: build-docs failed:\n{built.stdout}\n{built.stderr}")

    html = out.read_text(encoding="utf-8")
    html, n = re.subn(re.escape(f'<script src="{REDOC_CDN}"></script>'),
                      f'<script src="{REDOC_URL}" integrity="{REDOC_SRI}" crossorigin="anonymous"></script>', html)
    if n != 1:
        out.unlink()
        raise SystemExit(f"{name}: expected one Redoc script from {REDOC_CDN}, found {n}; "
                         f"the CLI pin and REDOC_* constants disagree")
    out.write_text(html, encoding="utf-8")
    print(f"{name}: rendered from {src} at {commit} ({len(html.encode()) // 1024} KiB); "
          f"set source_commit: {commit}")
    return commit


def main(argv: list[str]) -> int:
    entries = (yaml.safe_load((PAGES / "pages.yaml").read_text(encoding="utf-8")) or {}).get("pages") or {}
    mine = {k: v for k, v in entries.items() if (v or {}).get("render") == "tools/site/render_apis.py"}
    want = argv or sorted(mine)
    for name in want:
        if name not in mine:
            raise SystemExit(f"{name}: not an API page in site/pages/pages.yaml")
        render(name, mine[name])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
