"""Exchange each tenant's access token for a JWT once, before k6 starts.

The k6 workload loads the resulting tenants file once into a SharedArray and its
setup() returns nothing, so driver memory does not grow with roster x VUs. The
exchange runs concurrently, bounded by the existing `jwtSetupConcurrency` setting.
The first refusal stops the run before load, as the k6 setup exchange did.

CLI (compose-baseline/bench.sh): jwt_tenants.py <tenants.json> <base-url> <concurrency> <output.json>
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def exchange(base, row, timeout=60):
    url = base.rstrip('/') + '/api/v2/authorization/request/' + urllib.parse.quote(row['token'], safe='')
    request = urllib.request.Request(url, headers={'Host': row['host'], 'Accept': 'application/json'})
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            token = json.loads(response.read()).get('token')
    except urllib.error.HTTPError as error:
        raise RuntimeError('M7_JWT_EXCHANGE_REFUSED:%d' % error.code) from None
    if not isinstance(token, str) or not token:
        raise RuntimeError('M7_JWT_EXCHANGE_MISSING')
    return token


def attach(rows, base, concurrency=1, *, timeout=60, deadline=None):
    """Return the rows with a `jwt` field, in roster order."""
    def token(row):
        seconds = min(timeout, deadline-time.time()) if deadline is not None else timeout
        if seconds <= 0:
            raise TimeoutError('M7_JWT_SETUP_DEADLINE')
        return exchange(base, row, seconds)
    with ThreadPoolExecutor(max_workers=max(1, min(int(concurrency), len(rows) or 1))) as pool:
        tokens = list(pool.map(token, rows))
    return [{**row, 'jwt': token} for row, token in zip(rows, tokens)]


def write(path, rows):
    """Private file: tokens and JWTs are credentials."""
    path = Path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(rows, stream, separators=(',', ':'))
    return path


if __name__ == '__main__':
    source, base, concurrency, output = sys.argv[1:5]
    write(output, attach(json.loads(Path(source).read_text()), base, int(concurrency)))
