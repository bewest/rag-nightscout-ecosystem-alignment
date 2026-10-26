#!/usr/bin/env python3
"""Copy cgm-remote-monitor's OpenAPI documents, at one commit, into
specs/openapi/upstream/cgm-remote-monitor/, so the site can render the current
API next to this repository's proposals (tools/site/render_apis.py).

The site builds only from tracked files, so the upstream documents are copied
in rather than read from externals/. The directory's README.md records where
each copy came from: repository, ref, commit and sha256.

    python3 tools/site/vendor_upstream_openapi.py <cgm-remote-monitor checkout> <ref> [--label TEXT]

<ref> is any commit-ish in that checkout (for example official/dev). --label
says what the ref is (for example "dev, the 16.0.0 line"); it goes into the
README. Then commit the directory and re-render the API pages whose source it
changed.
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEST = REPO / "specs/openapi/upstream/cgm-remote-monitor"
UPSTREAM = "https://github.com/nightscout/cgm-remote-monitor"
FILES = {
    "api-v1.yaml": "lib/server/swagger.yaml",
    "api-v3.yaml": "lib/api3/swagger.yaml",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("checkout")
    ap.add_argument("ref")
    ap.add_argument("--label", default="")
    a = ap.parse_args()

    def git(*args: str) -> bytes:
        return subprocess.run(["git", "-C", a.checkout, *args], check=True, capture_output=True).stdout

    commit = git("rev-parse", "--verify", a.ref + "^{commit}").decode().strip()
    date = git("log", "-1", "--format=%cs", commit).decode().strip()
    DEST.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, path in FILES.items():
        data = git("show", f"{commit}:{path}")
        (DEST / name).write_bytes(data)
        rows.append(f"| `{name}` | [`{path}`]({UPSTREAM}/blob/{commit}/{path}) | `{hashlib.sha256(data).hexdigest()[:16]}` |")
    label = f" ({a.label})" if a.label else ""
    (DEST / "README.md").write_text(f"""# cgm-remote-monitor OpenAPI documents (copies)

Copies of the OpenAPI documents that cgm-remote-monitor serves, taken from
[nightscout/cgm-remote-monitor]({UPSTREAM}) at commit
[`{commit[:8]}`]({UPSTREAM}/commit/{commit}){label}, committed {date}.
They are copied so the site can render the current API beside this
repository's proposals; edit them upstream, not here. To refresh:
`python3 tools/site/vendor_upstream_openapi.py <checkout> <ref> --label "..."`.

| Copy | Upstream file | sha256 (first 16) |
|---|---|---|
{chr(10).join(rows)}
""", encoding="utf-8")
    print(f"copied {len(FILES)} files from {commit[:8]} ({date}) into {DEST.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
