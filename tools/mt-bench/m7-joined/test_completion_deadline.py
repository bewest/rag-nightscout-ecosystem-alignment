"""Run the actual generated poller against a synthetic monotonic clock."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from probe import generate

ROOT = Path(__file__).resolve().parents[3]
KUBE = ROOT / 'tools/mt-bench/kubernetes'


class CompletionDeadline(unittest.TestCase):
    def test_actual_generated_poller_strict_120_seconds(self):
        with tempfile.TemporaryDirectory() as tmp:
            compose = Path(tmp) / 'compose.cjs'
            native = Path(tmp) / 'native.cjs'
            generate(ROOT, compose)
            subprocess.run(['python3', '-c',
                            'import kube_adapter,sys; kube_adapter.generate_probe(sys.argv[1])',
                            str(native)], cwd=KUBE, check=True)
            for path in (compose, native):
                with self.subTest(path=path.name):
                    subprocess.run(['node', str(Path(__file__).with_name('clinical-acceptance.test.cjs')),
                                    str(path)], check=True, timeout=10)
