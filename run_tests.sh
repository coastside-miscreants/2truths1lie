#!/bin/bash
# Script to run all tests for the Two Truths & AI Game

# Set up Python virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install Python requirements
echo "Installing Python requirements..."
pip install -r requirements.txt
pip install -r test-requirements.txt

# Install Node.js dependencies
echo "Installing Node.js dependencies..."
npm install

# Run backend tests
echo "Running backend tests..."
python -m pytest tests/test_backend.py -v

# Run frontend tests
echo "Running frontend tests..."
npm run test:frontend

# Run integration tests (optional)
if [ "$1" == "--integration" ]; then
    echo "Running integration tests..."
    python -m pytest tests/test_integration.py -v
fi

# Deactivate virtual environment
deactivate

echo "All tests completed!"