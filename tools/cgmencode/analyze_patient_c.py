"""Patient C analysis — thin wrapper for the unified analyzer.

Historical entry point. Delegates to
`tools.cgmencode.analyze_patient` with `--patient-id c` against the
training-cohort parquet.

The original 499-line implementation was consolidated so live-recent
personal data and the cohort patients use the same code path.
"""
from __future__ import annotations

from pathlib import Path

from tools.cgmencode.analyze_patient import analyze

REPO = Path(__file__).resolve().parents[2]


def main():
    analyze(
        patient_id="c",
        parquet_dir=REPO / "externals/ns-parquet/training",
        out_dir=REPO / "reports/patient-c-analysis",
    )


if __name__ == "__main__":
    main()
