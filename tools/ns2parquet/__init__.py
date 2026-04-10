"""
ns2parquet — Nightscout to Parquet pipeline.

Converts Nightscout JSON data (from disk or API) into columnar Parquet files
optimized for research and data warehouse queries.

Usage:
    # Convert a patient's JSON directory to parquet
    python -m tools.ns2parquet convert \\
        --input externals/ns-data/patients/a/training \\
        --patient-id a --output output/

    # Convert all patients at once
    python -m tools.ns2parquet convert-all \\
        --patients-dir externals/ns-data/patients \\
        --output output/

    # Fetch from live Nightscout site and convert
    python -m tools.ns2parquet ingest \\
        --url https://your-ns.example.com \\
        --days 90 --patient-id mysite --output output/

    # Show info about existing parquet files
    python -m tools.ns2parquet info --input output/
"""

__version__ = '0.1.0'
