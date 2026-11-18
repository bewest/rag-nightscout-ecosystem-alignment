"""Load the Kubernetes adapter by path when entering through a companion CLI."""
import importlib.util
from pathlib import Path
import sys


spec = importlib.util.spec_from_file_location(__name__, Path(__file__).with_name('adapter.py'))
module = importlib.util.module_from_spec(spec)
sys.modules[__name__] = module
spec.loader.exec_module(module)
