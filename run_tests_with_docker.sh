#!/bin/bash
# Script to run tests in Docker

# Build the test image if needed
docker-compose build test

# Run the tests
docker-compose run --rm test

# Show status
if [ $? -eq 0 ]; then
    echo "All tests passed!"
else
    echo "Some tests failed!"
fi