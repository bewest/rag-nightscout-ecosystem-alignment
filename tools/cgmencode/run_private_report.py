"""Personal-data analysis wrapper.

Backwards-compatible entry point. Delegates to the unified
`tools.cgmencode.analyze_patient` after ensuring `live-recent` has
been converted to parquet via `tools.ns2parquet`.

Old behaviour: hand-built loader (`_load_live_recent_to_patient`) that
parsed Nightscout JSON in-process. That path silently lost Loop's
enacted basal stream and SMB autobolus deliveries, leaving downstream
recommendations operating on a near-empty insulin signal. This wrapper
fixes that by reusing the same canonical ns2parquet → grid.parquet
ingestion that builds `externals/ns-parquet/training/`.

Usage:
    python -m tools.cgmencode.run_private_report
    python -m tools.cgmencode.run_private_report --rebuild-parquet
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LIVE_DIR = REPO / "externals/ns-data/live-recent"
PARQUET_DIR = REPO / "externals/ns-parquet/live-recent"
# Default output: sibling to reports/patient-c-analysis/ so the rendered
# markdown + plot PNGs surface on GitHub. The raw input parquet stays
# under externals/ns-parquet/live-recent/ (gitignored).
OUT_DIR = REPO / "reports/live-recent-analysis"


def ensure_parquet(rebuild: bool = False) -> None:
    if not LIVE_DIR.exists():
        raise SystemExit(f"Live data directory not found: {LIVE_DIR}\n"
                         f"Hint: pull from Nightscout first.")
    if PARQUET_DIR.exists() and not rebuild:
        return
    print(f"Building parquet at {PARQUET_DIR} ...")
    subprocess.run(
        [
            sys.executable, "-m", "tools.ns2parquet", "convert",
            "-i", str(LIVE_DIR),
            "-p", "live-recent",
            "-o", str(PARQUET_DIR),
        ],
        check=True,
        cwd=str(REPO),
    )


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--rebuild-parquet", action="store_true",
                   help="Re-run ns2parquet conversion even if output exists.")
    args = p.parse_args(argv)
    ensure_parquet(rebuild=args.rebuild_parquet)
    from tools.cgmencode.analyze_patient import analyze
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    analyze("live-recent", PARQUET_DIR, OUT_DIR)


if __name__ == "__main__":
    main()
