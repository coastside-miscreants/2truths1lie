#!/usr/bin/env python3
"""
This script patches the test_backend.py file to avoid Redis/FakeRedis compatibility issues.
It creates a temporary modified version of the test file that works in Docker.
"""

import os
import sys
import shutil
import tempfile
import subprocess

def create_patched_test():
    """Create a patched version of test_backend.py that works with Docker"""
    test_file = "/app/tests/test_backend.py"
    patched_file = "/tmp/patched_test_backend.py"
    
    with open(test_file, 'r') as f:
        content = f.read()
    
    # Patch 1: Replace problematic imports and add necessary mocks
    new_content = content.replace(
        """import fakeredis
from unittest.mock import patch, MagicMock
import tempfile
import yaml

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# We need to mock important modules before importing the main application
sys.modules['anthropic'] = MagicMock()
sys.modules['redis'] = MagicMock()""", 
        """from unittest.mock import patch, MagicMock
import tempfile
import yaml

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# We need to mock important modules before importing the main application
sys.modules['anthropic'] = MagicMock()
sys.modules['redis'] = MagicMock()

# Mock fakeredis
class FakeRedis:
    def __init__(self, *args, **kwargs):
        self.data = {}
    
    def get(self, key):
        return self.data.get(key)
    
    def set(self, key, value, *args, **kwargs):
        self.data[key] = value
        return True
    
    def delete(self, key):
        if key in self.data:
            del self.data[key]
        return True
        
    def hset(self, name, key, value):
        if name not in self.data:
            self.data[name] = {}
        self.data[name][key] = value
        return 1
    
    def hgetall(self, name):
        return self.data.get(name, {})
        
    def close(self):
        pass

# Mock fakeredis at the module level
fakeredis = MagicMock()
fakeredis.FakeRedis = FakeRedis"""
    )
    
    # Patch 2: Replace fakeredis.FakeRedis() with our mocked FakeRedis
    new_content = new_content.replace(
        "fakeredis.FakeRedis(", 
        "FakeRedis("
    )
    
    with open(patched_file, 'w') as f:
        f.write(new_content)
    
    return patched_file

def run_patched_tests():
    """Run the patched backend tests"""
    patched_file = create_patched_test()
    
    # Run pytest with the patched file
    print("Running backend tests with patched Redis mock...")
    # Set timeout to avoid hanging
    try:
        # Use real-time output instead of capturing
        result = subprocess.run(
            ["python", "-m", "pytest", patched_file, "-v", "--no-header", "--timeout=30"],
            timeout=60,  # Set a 60-second timeout for the entire process
            check=False  # Don't raise exception on non-zero exit
        )
        return result.returncode
    except subprocess.TimeoutExpired:
        print("ERROR: Tests timed out after 60 seconds")
        return 1

if __name__ == "__main__":
    sys.exit(run_patched_tests())