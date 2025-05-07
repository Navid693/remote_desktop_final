"""Test configuration for pytest.

Adds the project root directory to Python path so that
modules can be imported during testing.
"""

import os
import sys
from pathlib import Path

# Add project root to Python path
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))