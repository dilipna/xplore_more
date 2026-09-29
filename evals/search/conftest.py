"""The eval scripts import each other as top-level modules (they run as `python evals/search/x.py`).

pytest runs with --import-mode=importlib, which does not add this directory to sys.path.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
