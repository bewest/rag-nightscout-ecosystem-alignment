"""MkDocs hook: load the nav that tools/site/build.py generated.

mkdocs.yml is committed and static; the nav is regenerated from `git ls-files`
on every build and written to build/site-nav.yaml.
"""
from pathlib import Path

import yaml

NAV_FILE = Path(__file__).resolve().parents[2] / "build" / "site-nav.yaml"


def on_config(config, **kwargs):
    if not NAV_FILE.exists():
        raise SystemExit(f"{NAV_FILE} missing: run `make site` (tools/site/build.py) first")
    config["nav"] = yaml.safe_load(NAV_FILE.read_text())
    return config
