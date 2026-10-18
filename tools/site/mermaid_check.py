#!/usr/bin/env python3
"""Parse every ```mermaid block in the tracked docs with the pinned mermaid.

    python tools/site/mermaid_check.py [files...]      (make diagrams-check)

The mermaid version is the one mkdocs.yml pins under extra_javascript, so the
check and the site use the same parser. Each block goes through
`mermaid.parse()` in headless Chrome (`--dump-dom` on a generated local page;
no node packages). A failure prints `file:line` (the line inside the block the
parser names, else the fence line) and the parser's message, and exits 1.

Network: none at check time once the runtime is cached. The first run for a
version downloads the npm tarball once, verifies it against the sha512
integrity recorded below, and caches dist/mermaid.min.js under
~/.cache/nightscout-alignment/mermaid/<version>/. MERMAID_JS=<path> uses a
local copy instead; CHROME=<binary> picks the browser.
"""
from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MKDOCS = REPO / "mkdocs.yml"

# npm `dist.integrity` per pinned version (npm view mermaid@<v> dist.integrity)
INTEGRITY = {
    "11.17.2": "sha512-V6K3C8EBdEsPFZXSKMJe6ppQOENxuHARr9GvHX4hh47lAbhMRD9qf4oEK7LoaRQxULMa80/qt5gHO73aCleBBg==",
}

FENCE_OPEN = re.compile(r"^(\s*)(`{3,}|~{3,})\s*mermaid\s*$")
PIN = re.compile(r"mermaid@(\d+\.\d+\.\d+)/dist/mermaid\.min\.js")


def pinned_version() -> str:
    found = PIN.findall(MKDOCS.read_text(encoding="utf-8"))
    if len(set(found)) != 1:
        sys.exit(f"mkdocs.yml: expected one pinned mermaid@X.Y.Z URL, found {sorted(set(found)) or 'none'}")
    return found[0]


def runtime(version: str) -> Path:
    if os.environ.get("MERMAID_JS"):
        return Path(os.environ["MERMAID_JS"])
    cache = Path.home() / ".cache" / "nightscout-alignment" / "mermaid" / version
    js = cache / "mermaid.min.js"
    if js.exists():
        return js
    if version not in INTEGRITY:
        sys.exit(f"no recorded integrity for mermaid {version}; add it to INTEGRITY in {Path(__file__).name}")
    url = f"https://registry.npmjs.org/mermaid/-/mermaid-{version}.tgz"
    print(f"one-time download: {url}", file=sys.stderr)
    data = urllib.request.urlopen(url, timeout=60).read()
    algo, want = INTEGRITY[version].split("-", 1)
    got = base64.b64encode(hashlib.new(algo, data).digest()).decode()
    if got != want:
        sys.exit(f"integrity mismatch for {url}")
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        member = tar.extractfile("package/dist/mermaid.min.js")
        cache.mkdir(parents=True, exist_ok=True)
        js.write_bytes(member.read())
    return js


def blocks(paths: list[str]):
    for rel in paths:
        lines = (REPO / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        i = 0
        while i < len(lines):
            m = FENCE_OPEN.match(lines[i])
            if not m:
                i += 1
                continue
            indent, fence = m.group(1), m.group(2)
            start = i + 1  # 1-based line of the fence
            body = []
            i += 1
            while i < len(lines) and not re.match(rf"^{re.escape(indent)}{re.escape(fence[0])}{{{len(fence)},}}\s*$", lines[i]):
                body.append(lines[i][len(indent):] if lines[i].startswith(indent) else lines[i].lstrip())
                i += 1
            yield {"file": rel, "line": start, "text": "\n".join(body)}
            i += 1


PAGE = """<!doctype html><meta charset="utf-8"><pre id="out">pending</pre>
<script src="mermaid.min.js"></script>
<script>
const blocks = %s;
mermaid.initialize({startOnLoad: false});
(async () => {
  const res = [];
  for (const b of blocks) {
    try { await mermaid.parse(b); res.push(null); }
    catch (e) { res.push(String((e && (e.message || e.str)) || e)); }
  }
  document.getElementById('out').textContent = 'RESULT ' + JSON.stringify(res);
})().catch(e => { document.getElementById('out').textContent = 'FATAL ' + e; });
</script>"""


def chrome() -> str:
    for c in [os.environ.get("CHROME"), "google-chrome", "chromium", "chromium-browser", "chrome"]:
        if c and shutil.which(c):
            return shutil.which(c)
    sys.exit("no Chrome/Chromium found (set CHROME=)")


def main(argv: list[str]) -> int:
    version = pinned_version()
    js = runtime(version)
    paths = argv or subprocess.run(["git", "ls-files", "*.md"], cwd=REPO, capture_output=True, text=True, check=True).stdout.split()
    found = list(blocks(paths))
    if not found:
        print(f"diagrams-check: no mermaid blocks in {len(paths)} files")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        shutil.copy(js, t / "mermaid.min.js")
        payload = json.dumps([b["text"] for b in found]).replace("</", "<\\/")
        (t / "check.html").write_text(PAGE % payload, encoding="utf-8")
        proc = subprocess.run(
            [chrome(), "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={t / 'profile'}",
             "--allow-file-access-from-files", "--virtual-time-budget=60000", "--dump-dom", (t / "check.html").as_uri()],
            capture_output=True, text=True, timeout=180)
    m = re.search(r'<pre id="out">(.*?)</pre>', proc.stdout, re.S)
    out = html.unescape(m.group(1)) if m else ""
    if not out.startswith("RESULT "):
        print(f"diagrams-check: browser run did not finish: {out[:300] or proc.stderr[-500:]}", file=sys.stderr)
        return 2
    results = json.loads(out[len("RESULT "):])
    bad = 0
    for b, err in zip(found, results):
        if err is None:
            continue
        bad += 1
        n = re.search(r"on line (\d+)", err)
        line = b["line"] + int(n.group(1)) if n else b["line"]
        msg = " ".join(err.split())
        print(f"{b['file']}:{line}: mermaid {version}: {msg[:400]}")
    files = len({b["file"] for b in found})
    print(f"diagrams-check: {len(found) - bad}/{len(found)} mermaid blocks parse in {files} files (mermaid {version})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
