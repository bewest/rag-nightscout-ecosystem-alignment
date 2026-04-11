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

    # Convert OpenAPS Data Commons patients
    python -m tools.ns2parquet convert-odc \\
        --odc-dir path/to/odc-dataset --output output/

    # Fetch from live Nightscout site and convert
    python -m tools.ns2parquet ingest \\
        --url https://your-ns.example.com \\
        --days 90 --patient-id mysite --output output/

    # Merge parquet from multiple sources
    python -m tools.ns2parquet merge dir1/ dir2/ --output combined/

    # Generate patient manifest
    python -m tools.ns2parquet manifest --input output/

    # Show info about existing parquet files
    python -m tools.ns2parquet info --input output/
"""

__version__ = '0.3.0'

# Public API re-exports
from .normalize import (                                    # noqa: F401
    normalize_entries, normalize_treatments,
    normalize_devicestatus, normalize_profiles,
    normalize_settings,
)
from .grid import build_grid                                # noqa: F401
from .writer import write_parquet, read_parquet, parquet_info  # noqa: F401
from .schemas import (                                      # noqa: F401
    ENTRIES_SCHEMA, TREATMENTS_SCHEMA, DEVICESTATUS_SCHEMA,
    PROFILES_SCHEMA, SETTINGS_SCHEMA, GRID_SCHEMA,
)
from .constants import MMOLL_TO_MGDL, DIRECTION_MAP, normalize_timezone  # noqa: F401
from .ns_fetch import (                                     # noqa: F401
    fetch_json, fetch_entries, fetch_treatments,
    fetch_devicestatus, load_ns_url,
)
from .cli import build_manifest                             # noqa: F401
