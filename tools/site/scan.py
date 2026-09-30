#!/usr/bin/env python3
"""Fail-closed content scan over the STAGED site tree (build/site-src/).

Runs inside tools/site/build.py (before MkDocs) and again in tools/site/check.py
(make site-check). Every hit must be covered by an entry in
tools/site/scan-allowlist.yaml (path + kind + reason) or the build fails.

Output names the path, the kind and a count. It never prints the matched text,
so the log is safe to paste into an issue.

Kinds:
  email    an email address that is not a role, placeholder or SSH-remote form
  ns-host  a hostname on a Nightscout hosting platform that is not a placeholder
  token    a credential-shaped value: KEY=value / key: value with a 16+ char
           value holding letters and digits, a Nightscout subject-hash token,
           or a well-known provider key / private-key / URI-credential shape
  payload  a request-shaped string for a defect class still live on the
           shipping release: socket.io frames for the alarm namespace or the
           retro-load handler, nested-quantifier patterns sent as a regex query,
           `$where` / `$lookup` query-string operands with a concrete value
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "build" / "site-src"
ALLOWLIST = REPO / "tools" / "site" / "scan-allowlist.yaml"
TEXT_EXT = {".md", ".svg", ".html", ".htm"}
KINDS = ("email", "ns-host", "token", "payload")

EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
EMAIL_OK = re.compile(
    r"^(git@github\.com|git@gitlab\.com|git@bitbucket\.org)$"      # SSH remotes
    r"|noreply|no-reply|@users\.noreply\.github\.com$"
    r"|@example\.(com|org|net)$|\.example$|@localhost$|@test$|@invalid$", re.I)

NS_HOST = re.compile(
    r"\b([a-z0-9-]+)\.(herokuapp\.com|azurewebsites\.net|ns\.10be\.de|fly\.dev|railway\.app"
    r"|onrender\.com|t1pal\.com|nightscoutpro\.com|ns\.gluroo\.com|nightscout\.pro)\b", re.I)
NS_HOST_OK = re.compile(r"^(your|my|example|sample|demo|placeholder|test|site|foo|bar|xxx)", re.I)

TOKEN_ASSIGN = re.compile(
    r"(?i)(token|api[_-]?secret|secret|password|passwd|apikey|api[_-]?key)[\"']?\s*[=:]\s*[\"']?"
    r"([A-Za-z0-9_\-+/]{16,})")
PLACEHOLDER = re.compile(r"(?i)example|your[_-]|changeme|placeholder|dummy|xxxx|<[^>]*>")
TOKEN_SHAPES = [
    re.compile(r"\b[a-z][a-z0-9]{1,30}-[0-9a-f]{16}\b"),                # Nightscout subject token
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),                      # GitHub token
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                                # AWS access key
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bmongodb(\+srv)?://[^\s/:@]+:[^\s/@]+@", re.I),       # URI with credentials
    re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"),
]

PAYLOADS = [
    re.compile(r"\b4[02]/alarm\b"),                                     # engine.io frame, alarm ns
    re.compile(r"42\[\s*[\"']"),                                        # engine.io event frame
    re.compile(r"emit\(\s*[\"']loadRetro", re.I),
    re.compile(r"(\$regex|\[re\]|re=)[^\n]{0,80}\([^()\s]{1,12}[+*]\)[+*{]"),
    re.compile(r"\[\$where\]=(?!<|…|\.\.\.)[^\s`|)]+"),
    re.compile(r"\[\$lookup\]|pipeline\[\d*\]\[\$", re.I),
]


def hits_in(text: str) -> collections.Counter:
    c = collections.Counter()
    for m in EMAIL.finditer(text):
        if not EMAIL_OK.search(m.group(0)):
            c["email"] += 1
    for m in NS_HOST.finditer(text):
        if not NS_HOST_OK.search(m.group(1)):
            c["ns-host"] += 1
    for m in TOKEN_ASSIGN.finditer(text):
        v = m.group(2)
        if re.search(r"\d", v) and re.search(r"[A-Za-z]", v) and not PLACEHOLDER.search(v):
            c["token"] += 1
    for rx in TOKEN_SHAPES:
        c["token"] += len(rx.findall(text))
    for rx in PAYLOADS:
        c["payload"] += len(rx.findall(text))
    return +c


def load_allowlist() -> dict[tuple[str, str], str]:
    data = yaml.safe_load(ALLOWLIST.read_text()) or {}
    allow = {}
    for n, e in enumerate(data.get("allow") or []):
        if set(e) != {"path", "kind", "reason"}:
            sys.exit(f"scan-allowlist.yaml entry {n}: fields must be exactly path, kind, reason")
        if e["kind"] not in KINDS:
            sys.exit(f"scan-allowlist.yaml entry {n}: unknown kind {e['kind']!r}")
        allow[(e["path"], e["kind"])] = e["reason"]
    return allow


def scan(root: Path = SRC) -> dict:
    allow = load_allowlist()
    found, blocked, used = {}, [], set()
    for p in sorted(root.rglob("*")):  # the staged tree is our own output, not the repo
        if not p.is_file() or p.suffix.lower() not in TEXT_EXT:
            continue
        rel = p.relative_to(root).as_posix()
        c = hits_in(p.read_text(encoding="utf-8", errors="replace"))
        for kind, n in c.items():
            found[f"{rel}|{kind}"] = n
            if (rel, kind) in allow:
                used.add((rel, kind))
            else:
                blocked.append({"path": rel, "kind": kind, "count": n})
    stale = [{"path": p, "kind": k} for (p, k) in allow if (p, k) not in used]
    return {"hits": len(found), "allowed": len(used), "blocked": blocked, "stale_allowlist": stale}


def report(res: dict, prefix: str = "scan") -> int:
    for b in res["blocked"]:
        print(f"{prefix}: BLOCKED {b['path']}: {b['count']} {b['kind']} hit(s) not on scan-allowlist.yaml")
    for s in res["stale_allowlist"]:
        print(f"{prefix}: note: allowlist entry matches nothing: {s['path']} ({s['kind']})")
    if res["blocked"]:
        print(f"{prefix}: FAIL: {len(res['blocked'])} path/kind pair(s) blocked; fix the text or add an "
              f"allowlist entry with a reason (never the matched text)")
        return 1
    print(f"{prefix}: OK: {res['hits']} path/kind hit(s), all on the allowlist")
    return 0


if __name__ == "__main__":
    sys.exit(report(scan()))
