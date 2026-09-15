"""vendor_drift.py — is the DDL the server ships still the DDL we emit?

``specs/generated/postgres/`` is the source of truth, but cgm-remote-monitor
cannot depend on this repository at runtime, so T2.5 vendored a copy into the
server tree at ``lib/storage/postgres/generated/``. **That copy is what actually
creates tables on a deployment.**

Two files in two repositories with no relationship between them is a schema that
drifts silently, and the failure is quiet rather than loud: the server keeps
working against whatever it vendored, the emitter keeps producing something
else, and the two only meet when a query written for the new shape runs against
the old one. On a storage layer that holds glucose data, "the column is not
there" and "the column is there and means something else" are very different
days.

Same shape of check as ``code_model --cross-check``, and it reaches into
``externals/`` the same way. It compares BYTES, because the vendored file is
meant to be a copy — anything else is a hand edit of a generated file, which is
exactly what the header of every emitted file forbids.
"""

import argparse
import sys
from pathlib import Path

from . import corpus

# Where the emitter writes, and where the server reads. Relative to the repo
# root and to each server checkout respectively.
EMITTED = "specs/generated/postgres"
VENDORED = "lib/storage/postgres/generated"

# Checkouts that may carry a vendored copy. A checkout without the directory is
# not a failure -- most branches predate T2.5 and vendor nothing.
SOURCE_ROOTS = (
    "externals/work/crm-seam",
    "externals/cgm-remote-monitor-official",
)


def compare(root: Path, checkout: Path):
    """Returns (checked, [problem, ...]) for one server checkout."""
    emitted_dir = root / EMITTED
    vendored_dir = checkout / VENDORED
    if not vendored_dir.is_dir():
        return 0, []

    problems = []
    checked = 0
    for vendored in sorted(vendored_dir.iterdir()):
        if not vendored.is_file():
            continue
        emitted = emitted_dir / vendored.name
        checked += 1
        if not emitted.is_file():
            # The server ships a file the emitter no longer produces. Worth
            # failing on: it means a table is being created from something
            # nothing regenerates.
            problems.append(f"{vendored.name}: vendored but not emitted")
            continue
        if emitted.read_bytes() != vendored.read_bytes():
            problems.append(f"{vendored.name}: differs from {EMITTED}/{vendored.name}")

    for emitted in sorted(emitted_dir.iterdir()) if emitted_dir.is_dir() else []:
        if emitted.is_file() and not (vendored_dir / emitted.name).exists():
            # Not a failure. The emitter covers four collections; T2.5 vendored
            # only the one the server can actually run on, deliberately.
            pass

    return checked, problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--source", type=Path, action="append", dest="sources",
                    help="server checkout to check (repeatable); defaults to the known ones")
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    checkouts = args.sources or [root / s for s in SOURCE_ROOTS]

    failed = False
    looked = False
    for checkout in checkouts:
        checkout = Path(checkout)
        if not checkout.is_dir():
            continue
        checked, problems = compare(root, checkout)
        if not checked:
            continue
        looked = True
        name = checkout.name
        if problems:
            failed = True
            for p in problems:
                print(f"  DRIFT    {name}: {p}")
        else:
            print(f"  agrees   {name} ({checked} vendored file{'s' if checked != 1 else ''})")

    if not looked:
        # Say so rather than exiting 0 on having checked nothing, which is the
        # way a drift check quietly stops being one.
        print("no vendored PostgreSQL DDL found in any checkout -- nothing checked")
        return 0

    if failed:
        print("\nThe server ships DDL that is not what the emitter produces.")
        print(f"Regenerate with `make schema-emit`, then copy {EMITTED}/ into the")
        print(f"server checkout's {VENDORED}/. Do not hand-edit either copy.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
