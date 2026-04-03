"""Pytest configuration — adds the spotyvibe directory to sys.path."""

import sys
from pathlib import Path

# Allow imports like `from config import ...` and `from core.xxx import ...`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

