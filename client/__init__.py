"""Client package initialization"""

import os
import sys
from pathlib import Path

# Add project root to Python path
ROOT_DIR = (
    Path(__file__).resolve().parents[1]
)  # go up two levels from client/__init__.py to reach project root
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
