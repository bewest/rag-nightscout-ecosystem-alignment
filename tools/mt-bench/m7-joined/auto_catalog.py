"""Index retained terminal evidence without changing the operating verdict."""

from pathlib import Path
import subprocess
import sys

TOOL = Path(__file__).resolve().parent.parent / 'run-catalog' / 'catalog.py'
ARTIFACTS = Path('/mnt/data/nightscout-workspace/artifacts')


def auto_catalog(root, write):
    if not root.is_relative_to(ARTIFACTS) or not TOOL.is_file():
        return
    try:
        completed = subprocess.run([sys.executable, '-B', str(TOOL), 'add', str(root)],
                                   capture_output=True, timeout=30)
        code = 'CATALOG_INDEX_REFUSED' if completed.returncode else None
    except (OSError, subprocess.TimeoutExpired):
        code = 'CATALOG_COULD_NOT_RUN'
    if code:
        try:
            write(root / 'catalog-status.json', {'status': 'UNMEASURED', 'code': code})
        except OSError:
            # Primary results are already retained. A full or inaccessible
            # catalog must not replace the original experiment failure.
            pass
