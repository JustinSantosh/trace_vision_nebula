"""TRACEVISION AI: vehicle identification and traceability from CCTV footage (Hack-A-Sol 5.0, AIML-01)."""
from pathlib import Path

import yaml

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = PACKAGE_DIR.parent


def load_config(path=None):
    with open(path or PACKAGE_DIR / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)
