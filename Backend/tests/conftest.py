"""Pytest configuration and fixtures.

Adds Backend directory to Python path so app module can be imported.
"""

import sys
import os

# Add Backend directory to path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)
