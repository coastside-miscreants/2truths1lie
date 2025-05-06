"""
Pytest configuration file with shared fixtures.
"""

import os
import sys
import pytest
from unittest.mock import MagicMock

# We need to mock certain modules before any imports happen
sys.modules['anthropic'] = MagicMock()
sys.modules['redis'] = MagicMock()

# Add a fixed seed for all random operations in tests
@pytest.fixture(autouse=True)
def set_random_seed():
    """Set random seed for all tests for reproducibility."""
    import random
    random.seed(42)