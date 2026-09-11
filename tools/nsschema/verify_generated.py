"""verify_generated.py — fail if a committed artifact drifted from its source.

Generated files are committed so they are reviewable in a diff and usable
without running the pipeline. That only works if they are actually
regenerable: a hand-edit to ``specs/generated/mongoose/entries.schema.js``
would reintroduce exactly the drift this package exists to remove.

Regenerates every emitter's output into memory and compares it byte for
byte with what is on disk. Intended for CI and for ``make check``.

Note that this verifies the *emitters* against the *model*, not the model
against the corpus — re-censusing 2.5 GB of documents is not a CI job. If
the model changes, run ``make schema`` and commit the result.
"""

import json
import sys
from pathlib import Path

from . import corpus, specload
from .emit import fieldref_emit, jsonschema_emit, mongoose_emit, pyarrow_emit, zod_emit


def _read_optional(path: Path):
    return json.loads(path.read_text()) if path.is_file() else None


def expected_files(root: Path):
    """Yield (path, expected_content) for every generated artifact."""
    census_dir = root / "reports" / "schema-census"
    attribution = _read_optional(census_dir / "attribution.json")
    quirk_report = _read_optional(census_dir / "quirks.json")
    quirks = (quirk_report or {}).get("results", [])
    for collection in specload.ROOT_SCHEMA:
        model_path = root / "specs" / "nsschema" / f"{collection}.model.json"
        if not model_path.is_file():
            continue
        model = json.loads(model_path.read_text())

        for profile in jsonschema_emit.PROFILES:
            for strictness in jsonschema_emit.STRICTNESS:
                schema = jsonschema_emit.emit(model, profile, strictness)
                yield (root / "specs" / "jsonschema" / "generated" /
                       f"{collection}.{profile}.{strictness}.schema.json",
                       json.dumps(schema, indent=1) + "\n")

        yield (root / "specs" / "generated" / "mongoose" / f"{collection}.schema.js",
               mongoose_emit.emit(model))
        yield (root / "specs" / "generated" / "typescript" / f"{collection}.ts",
               zod_emit.emit(model))
        yield (root / "specs" / "generated" / "arrow" / f"{collection}_wire.py",
               pyarrow_emit.emit(model))

        census_path = root / "reports" / "schema-census" / f"{collection}.census.json"
        if census_path.is_file():
            census = json.loads(census_path.read_text())
            yield (root / "docs" / "10-domain" / "field-reference" / f"{collection}.md",
                   fieldref_emit.emit(model, census, attribution, quirks))


def main(argv=None):
    root = corpus.repo_root()
    missing, stale = [], []
    checked = 0
    for path, expected in expected_files(root):
        checked += 1
        if not path.is_file():
            missing.append(path.relative_to(root))
        elif path.read_text() != expected:
            stale.append(path.relative_to(root))

    if missing or stale:
        for p in missing:
            print(f"MISSING  {p}")
        for p in stale:
            print(f"STALE    {p}")
        print(f"\n{len(missing) + len(stale)} of {checked} generated artifacts are out of "
              f"date. Run: make schema-emit", file=sys.stderr)
        return 1

    print(f"{checked} generated artifacts match their model.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
