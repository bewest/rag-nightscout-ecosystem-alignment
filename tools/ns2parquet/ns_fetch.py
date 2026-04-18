"""
ns_fetch.py — Fetch Nightscout data via REST API.

Provides windowed fetching with deduplication for each Nightscout collection.
Uses 7-day windows to stay within the Nightscout 10K record limit per request.

Usage (standalone):
    python -m tools.ns2parquet.ns_fetch \\
        --url https://your-ns.example.com \\
        --days 90 --output /tmp/ns-data

Usage (as library):
    from tools.ns2parquet.ns_fetch import fetch_entries, fetch_treatments
    entries = fetch_entries(base_url, start_ms, end_ms)
"""

import json
import logging
import time
import urllib.error
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Retry configuration
_MAX_RETRIES = 3
_RETRY_BACKOFF = [2, 5, 15]          # seconds between retries
_RETRYABLE_CODES = {429, 500, 502, 503, 504}  # HTTP codes worth retrying
_INTER_REQUEST_SLEEP = 1.5           # seconds between windowed requests


def load_ns_url(env_path: str) -> str:
    """Parse NS_URL from a bash-style env file."""
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith('NS_URL='):
                url = line.split('=', 1)[1].strip().strip('"').strip("'")
                return url.rstrip('/')
    raise ValueError(f'NS_URL not found in {env_path}')


def parse_ns_url(url: str) -> tuple:
    """Split a Nightscout URL into (base_url, token_or_none).

    Handles URLs like ``https://site.example.com/?token=abc-123`` by
    extracting the token from query params and returning the clean base URL.

    Returns:
        (base_url, token) — base_url has no trailing slash or query string;
        token is ``None`` when the URL carries no ``?token=`` parameter.
    """
    parsed = urllib.parse.urlparse(url.strip())
    qs = urllib.parse.parse_qs(parsed.query)
    token = qs.get('token', [None])[0]
    # Rebuild URL without query string
    clean = urllib.parse.urlunparse((
        parsed.scheme, parsed.netloc, parsed.path.rstrip('/'), '', '', '',
    ))
    return clean.rstrip('/'), token


def fetch_json(url: str, params: Optional[dict] = None,
               token: Optional[str] = None) -> any:
    """Fetch JSON from a URL with optional query parameters.

    Retries on transient HTTP errors (429, 5xx) with exponential backoff.
    Raises immediately on auth errors (401, 403) since retrying won't help.

    Args:
        url: Full URL (should not contain ``?token=``; use *token* param).
        params: Extra query-string parameters.
        token: Nightscout readable token (appended as ``&token=…``).
    """
    all_params = dict(params or {})
    if token:
        all_params['token'] = token
    full_url = url
    if all_params:
        qs = urllib.parse.urlencode(all_params)
        full_url = f'{url}?{qs}'
    req = urllib.request.Request(full_url, headers={'Accept': 'application/json'})

    last_exc = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in _RETRYABLE_CODES and attempt < _MAX_RETRIES:
                wait = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)]
                logger.info('HTTP %d on %s — retry %d/%d in %ds',
                            e.code, url, attempt + 1, _MAX_RETRIES, wait)
                time.sleep(wait)
                last_exc = e
                continue
            raise  # 401, 403, 404, etc. — don't retry
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            if attempt < _MAX_RETRIES:
                wait = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)]
                logger.info('Network error on %s — retry %d/%d in %ds: %s',
                            url, attempt + 1, _MAX_RETRIES, wait, e)
                time.sleep(wait)
                last_exc = e
                continue
            raise
    raise last_exc  # pragma: no cover


def _fetch_windowed(base_url: str, endpoint: str, id_field: str,
                    sort_field: str, start, end,
                    date_mode: str = 'iso',
                    verbose: bool = False,
                    label: str = '',
                    token: Optional[str] = None) -> List[Dict]:
    """Fetch records in 7-day windows with deduplication.

    Args:
        base_url: Nightscout base URL (no trailing slash, no query string).
        endpoint: API path (e.g., '/api/v1/entries.json')
        id_field: Field name for deduplication (typically '_id')
        sort_field: Field to sort results by
        start: Start of range (epoch ms for 'epoch' mode, datetime for 'iso')
        end: End of range (epoch ms for 'epoch' mode, datetime for 'iso')
        date_mode: 'epoch' for epoch milliseconds, 'iso' for ISO 8601 strings
        verbose: Print progress
        label: Display label for progress messages
        token: Nightscout readable token (passed through to each request).

    Returns:
        Deduplicated, sorted list of records
    """
    all_records = []

    if date_mode == 'epoch':
        window = 7 * 86400 * 1000  # 7 days in ms
        cursor = end
        while cursor > start:
            win_start = max(start, cursor - window)
            if verbose:
                d1 = datetime.fromtimestamp(win_start / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
                d2 = datetime.fromtimestamp(cursor / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
                print(f'  {label} {d1} → {d2}...', end='', flush=True)

            params = {
                'find[date][$gte]': int(win_start),
                'find[date][$lt]': int(cursor),
                'count': 10000,
            }
            chunk = fetch_json(f'{base_url}{endpoint}', params, token=token)
            if verbose:
                print(f' {len(chunk)} records')
            all_records.extend(chunk)
            cursor -= window
            time.sleep(_INTER_REQUEST_SLEEP)
    else:
        window = timedelta(days=7)
        cursor = end
        while cursor > start:
            win_start = max(start, cursor - window)
            if verbose:
                print(f'  {label} {win_start.strftime("%Y-%m-%d")} → '
                      f'{cursor.strftime("%Y-%m-%d")}...', end='', flush=True)

            params = {
                'find[created_at][$gte]': win_start.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
                'find[created_at][$lt]': cursor.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
                'count': 10000,
            }
            chunk = fetch_json(f'{base_url}{endpoint}', params, token=token)
            if verbose:
                print(f' {len(chunk)} records')
            all_records.extend(chunk)
            cursor -= window
            time.sleep(_INTER_REQUEST_SLEEP)

    # Deduplicate by id_field
    seen = set()
    unique = []
    for rec in all_records:
        rid = rec.get(id_field, id(rec))
        if rid not in seen:
            seen.add(rid)
            unique.append(rec)
    unique.sort(key=lambda x: x.get(sort_field, 0), reverse=True)
    return unique


def fetch_entries(base_url: str, start_ms: int, end_ms: int,
                  verbose: bool = False,
                  token: Optional[str] = None) -> List[Dict]:
    """Fetch CGM entries in 7-day windows (NS has a 10K record limit)."""
    return _fetch_windowed(
        base_url, '/api/v1/entries.json', '_id', 'date',
        start_ms, end_ms, date_mode='epoch',
        verbose=verbose, label='entries', token=token,
    )


def fetch_treatments(base_url: str, start_dt: datetime, end_dt: datetime,
                     verbose: bool = False,
                     token: Optional[str] = None) -> List[Dict]:
    """Fetch treatments in 7-day windows."""
    return _fetch_windowed(
        base_url, '/api/v1/treatments.json', '_id', 'created_at',
        start_dt, end_dt, date_mode='iso',
        verbose=verbose, label='treatments', token=token,
    )


def fetch_devicestatus(base_url: str, start_dt: datetime, end_dt: datetime,
                       verbose: bool = False,
                       token: Optional[str] = None) -> List[Dict]:
    """Fetch devicestatus in 7-day windows."""
    return _fetch_windowed(
        base_url, '/api/v1/devicestatus.json', '_id', 'created_at',
        start_dt, end_dt, date_mode='iso',
        verbose=verbose, label='devicestatus', token=token,
    )
