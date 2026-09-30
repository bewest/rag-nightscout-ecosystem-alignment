"""Page labels for the static site: every staged markdown page is a Record or
a Living document (maintainer rule, 2026-09-30).

* Record: the file name carries a YYYY-MM-DD date. The page gets a banner
  "Record as of <date>. A point-in-time document; it is not kept up to date."
* Living: everything else. The page gets the line
  "Living document, last changed <git date> at <short sha>."
* tools/site/page-kinds.yaml overrides either way, per path.

Per-file dates come from ONE `git log --name-only` pass.
"""
from __future__ import annotations

import collections
import re
import subprocess
from pathlib import Path

import yaml

DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
# words in a dated file name that suggest a document people keep updating
LIVING_HINTS = re.compile(r"(?i)(plan|register|roadmap|policy|proposal|matrix|guide|charter|"
                          r"brief|status|backlog|map|queue|index|readme|record|tracker|spec)")


def last_changed(repo: Path) -> dict[str, tuple[str, str]]:
    """path -> (commit date YYYY-MM-DD, short sha) of the newest commit touching it."""
    out = subprocess.run(["git", "-C", str(repo), "log", "--no-renames", "--name-only",
                          "--format=%x01%h %cs"], check=True, capture_output=True, text=True).stdout
    seen: dict[str, tuple[str, str]] = {}
    sha = date = None
    for line in out.splitlines():
        if line.startswith("\x01"):
            sha, date = line[1:].split(" ", 1)
        elif line and line not in seen:
            seen[line] = (date, sha)
    return seen


class Labeller:
    def __init__(self, repo: Path, overrides_file: Path):
        self.dates = last_changed(repo)
        data = yaml.safe_load(overrides_file.read_text()) if overrides_file.exists() else None
        self.overrides = {}
        for n, e in enumerate((data or {}).get("overrides") or []):
            if e.get("kind") not in ("record", "living") or "path" not in e or "reason" not in e:
                raise SystemExit(f"page-kinds.yaml entry {n}: needs path, kind (record|living) and reason")
            if e["kind"] == "record" and not (DATE.search(e["path"].rsplit("/", 1)[-1]) or e.get("as_of")):
                raise SystemExit(f"page-kinds.yaml entry {n}: a record without a dated file name needs as_of")
            self.overrides[e["path"]] = e
        self.counts = collections.Counter()
        self.candidates: list[str] = []

    def kind(self, path: str) -> tuple[str, str | None]:
        name = path.rsplit("/", 1)[-1]
        m = DATE.search(name)
        o = self.overrides.get(path)
        if o:
            self.counts[f"override-{o['kind']}"] += 1
            return o["kind"], (str(o.get("as_of")) if o.get("as_of") else (m.group(1) if m else None))
        return ("record", m.group(1)) if m else ("living", None)

    def label(self, path: str, text: str, date_source: str | None = None) -> str:
        kind, as_of = self.kind(path)
        self.counts[kind] += 1
        if kind == "record":
            if LIVING_HINTS.search(path.rsplit("/", 1)[-1]) and path not in self.overrides:
                self.candidates.append(path)
            block = (f'!!! note "Record"\n    Record as of {as_of}. A point-in-time document; '
                     f'it is not kept up to date.\n')
        else:
            date, sha = self.dates.get(date_source or path, (None, None))
            if not date:
                self.counts["living-without-git-date"] += 1
                block = "*Living document (no committed history yet).*\n"
            else:
                block = f"*Living document, last changed {date} at `{sha}`.*\n"
        return insert_after_title(text, block)


def insert_after_title(text: str, block: str) -> str:
    lines = text.splitlines(keepends=True)
    i = 0
    if lines and lines[0].strip() == "---":  # YAML front matter
        for j in range(1, len(lines)):
            if lines[j].strip() in ("---", "..."):
                i = j + 1
                break
    fence = None
    for j in range(i, len(lines)):
        m = FENCE.match(lines[j])
        if fence is None and m:
            fence = m.group(1)[0]
            continue
        if fence is not None:
            if lines[j].strip().startswith(fence * 3):
                fence = None
            continue
        if lines[j].startswith("# "):
            return "".join(lines[:j + 1]) + "\n" + block + "\n" + "".join(lines[j + 1:])
        if lines[j].strip() and not lines[j].startswith(("<!--", "[//]")):
            break  # content before any H1: put the label at the top
    return "".join(lines[:i]) + block + "\n" + "".join(lines[i:])
