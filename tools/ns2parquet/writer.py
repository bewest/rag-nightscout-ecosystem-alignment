"""
writer.py — Write normalized DataFrames to Parquet files.

Supports two modes:
1. Overwrite: Write fresh parquet file
2. Append: Read existing, concatenate, deduplicate, write back

Deduplication uses (patient_id, timestamp) as composite key for each collection.
"""

import warnings

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
from typing import Optional


def _dedup_key(collection: str) -> list:
    """Return deduplication key columns for a collection."""
    return {
        'entries': ['patient_id', 'date'],
        'treatments': ['patient_id', 'created_at', 'event_type'],
        'devicestatus': ['patient_id', 'created_at', 'device'],
        'profiles': ['patient_id', '_id', 'schedule_type', 'time_seconds'],
        'grid': ['patient_id', 'time'],
    }.get(collection, ['patient_id'])


def write_parquet(df: pd.DataFrame, output_path: str,
                  collection: str,
                  schema: Optional[pa.Schema] = None,
                  append: bool = True,
                  verbose: bool = False) -> str:
    """Write a DataFrame to a Parquet file.

    Args:
        df: DataFrame to write
        output_path: Directory to write to
        collection: Collection name (entries, treatments, etc.)
        schema: Optional PyArrow schema to enforce
        append: If True and file exists, append and deduplicate
        verbose: Print progress

    Returns:
        Path to written parquet file
    """
    out_dir = Path(output_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f'{collection}.parquet'

    if df is None or df.empty:
        if verbose:
            print(f'  SKIP {collection}: empty DataFrame')
        return str(out_file)

    # Append mode: merge with existing
    if append and out_file.exists():
        existing = pd.read_parquet(out_file)
        df = pd.concat([existing, df], ignore_index=True)

        # Deduplicate
        dedup_cols = _dedup_key(collection)
        valid_cols = [c for c in dedup_cols if c in df.columns]
        if valid_cols:
            df = df.drop_duplicates(subset=valid_cols, keep='last')

        if verbose:
            print(f'  APPEND {collection}: {len(existing)} existing + {len(df) - len(existing)} new → {len(df)} total')

    # Convert timestamp columns to proper types
    for col in df.columns:
        if df[col].dtype == 'object':
            # Check if it looks like timestamps
            pass  # leave as-is for string columns

    # Write with compression
    if schema:
        try:
            table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)
        except (pa.ArrowInvalid, pa.ArrowTypeError, KeyError):
            # Schema mismatch — write without strict schema enforcement
            table = pa.Table.from_pandas(df, preserve_index=False)
    else:
        table = pa.Table.from_pandas(df, preserve_index=False)

    pq.write_table(table, out_file, compression='zstd')

    if verbose:
        size_mb = out_file.stat().st_size / (1024 * 1024)
        print(f'  WRITE {collection}: {len(df)} rows → {out_file} ({size_mb:.1f} MB)')

    return str(out_file)


def read_parquet(input_path: str, collection: str,
                 patient_id: Optional[str] = None,
                 columns: Optional[list] = None) -> pd.DataFrame:
    """Read a Parquet file, optionally filtering by patient_id.

    Args:
        input_path: Directory containing parquet files
        collection: Collection name (entries, treatments, etc.)
        patient_id: Optional patient filter
        columns: Optional column projection

    Returns:
        DataFrame
    """
    in_file = Path(input_path) / f'{collection}.parquet'
    if not in_file.exists():
        return pd.DataFrame()

    filters = None
    if patient_id:
        filters = [('patient_id', '=', patient_id)]

    return pd.read_parquet(in_file, columns=columns, filters=filters)


def parquet_info(input_path: str) -> dict:
    """Get summary info about parquet files in a directory.

    Returns dict with collection names as keys and stats as values.
    """
    in_dir = Path(input_path)
    info = {}

    for pf in sorted(in_dir.glob('*.parquet')):
        pf_meta = pq.read_metadata(pf)
        collection = pf.stem

        # Read patient_id column to count unique patients
        try:
            patient_ids = pd.read_parquet(pf, columns=['patient_id'])['patient_id'].unique()
        except Exception:
            patient_ids = []

        info[collection] = {
            'file': str(pf),
            'rows': pf_meta.num_rows,
            'columns': pf_meta.num_columns,
            'size_bytes': pf.stat().st_size,
            'size_mb': pf.stat().st_size / (1024 * 1024),
            'patients': sorted(patient_ids.tolist()) if len(patient_ids) else [],
            'num_patients': len(patient_ids),
            'num_row_groups': pf_meta.num_row_groups,
            'compression': pf_meta.row_group(0).column(0).compression if pf_meta.num_row_groups > 0 else 'unknown',
        }

    return info
