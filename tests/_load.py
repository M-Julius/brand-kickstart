"""Puts the skill's scripts/ dir on sys.path so tests can `from _load import check`."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT / "skills" / "brand-kickstart" / "scripts"))

import check  # noqa: E402,F401
