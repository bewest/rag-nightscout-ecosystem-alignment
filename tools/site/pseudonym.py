"""Build-time pseudonyms for data-commons participant IDs (tools/site).

The repository keeps the data commons' own participant IDs (`odc-` plus exactly
eight digits). The public site must not show them, so every staged text, path
and nav entry is rewritten to `odc-p-<first 8 hex of HMAC-SHA256(key, id)>`.

* The key comes from the environment variable SITE_PSEUDONYM_KEY. There is no
  default: if any ID is present and the key is unset, the build fails.
* A short form (`odc-` plus 2 to 7 digits, as some research notes abbreviate)
  is rewritten to the pseudonym of the ONE full staged ID it is a prefix of.
  A short form that matches no full ID, or more than one, fails the build.
* 13-digit `odc-<timestamp>` record ids are a different thing and are left
  alone (none is staged today).
* Neither the key nor any raw-to-pseudonym mapping is written anywhere; the
  build report gets counts only.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re

ENV = "SITE_PSEUDONYM_KEY"
FULL = re.compile(r"(?<![A-Za-z0-9])odc-(\d{8})(?!\d)")
SHORT = re.compile(r"(?<![A-Za-z0-9])odc-(\d{2,7})(?!\d)")
ANY = re.compile(r"(?<![A-Za-z0-9])odc-(\d{2,12})(?!\d)")  # what the scan forbids


class PseudonymError(SystemExit):
    pass


class Pseudonymizer:
    def __init__(self, texts: dict[str, str], paths: list[str]):
        """texts: staged path -> raw text; paths: every staged path."""
        self.full_ids = set()
        for t in list(texts.values()) + paths:
            self.full_ids.update(FULL.findall(t))
        has_short = any(SHORT.search(t) for t in list(texts.values()) + paths)
        key = os.environ.get(ENV, "")
        if (self.full_ids or has_short) and not key:
            raise PseudonymError(
                f"site: FAIL: {ENV} is not set, and staged content holds data-commons "
                f"participant IDs. Set the key (see tools/site/README.md); there is no default.")
        self._key = key.encode()
        self._cache: dict[str, str] = {}
        self.errors: list[str] = []
        self.count_full = 0
        self.count_short = 0
        self.files_touched: set[str] = set()
        self.paths_renamed = 0

    def _p(self, digits: str) -> str:
        if digits not in self._cache:
            self._cache[digits] = hmac.new(self._key, f"odc-{digits}".encode(), hashlib.sha256).hexdigest()[:8]
        return "odc-p-" + self._cache[digits]

    def text(self, s: str, where: str = "") -> str:
        n0 = self.count_full + self.count_short

        def full(m):
            self.count_full += 1
            return self._p(m.group(1))

        def short(m):
            d = m.group(1)
            hits = [f for f in self.full_ids if f.startswith(d)]
            if len(hits) != 1:
                self.errors.append(f"{where}: a {len(d)}-digit participant-ID short form matches "
                                   f"{len(hits)} staged full IDs (needs exactly 1)")
                return m.group(0)
            self.count_short += 1
            return self._p(hits[0])

        s = FULL.sub(full, s)
        s = SHORT.sub(short, s)
        if where and self.count_full + self.count_short > n0:
            self.files_touched.add(where)
        return s

    def path(self, p: str) -> str:
        q = self.text(p, where=p)
        if q != p:
            self.paths_renamed += 1
        return q

    def stats(self) -> dict:
        return {"participant_ids_found": len(self.full_ids),
                "full_rewrites": self.count_full, "short_rewrites": self.count_short,
                "files_touched": len(self.files_touched), "paths_renamed": self.paths_renamed,
                "errors": len(self.errors)}
