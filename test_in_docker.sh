#!/bin/bash
# A simplified script for running tests inside Docker

set -e  # Exit on error

# Default settings
TEST_TYPE="all"  # Options: all, frontend, backend
REBUILD=false    # Rebuild Docker image

# Parse command-line arguments
for arg in "$@"; do
  case $arg in
    --frontend)
      TEST_TYPE="frontend"
      shift
      ;;
    --backend)
      TEST_TYPE="backend"
      shift
      ;;
    --rebuild)
      REBUILD=true
      shift
      ;;
    --help)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  --frontend  Run only frontend tests"
      echo "  --backend   Run only backend tests"
      echo "  --rebuild   Force rebuild of the Docker test image"
      echo "  --help      Display this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

# Rebuild Docker image if requested
if [ "$REBUILD" = true ]; then
  echo "Rebuilding Docker test image..."
  docker-compose build --no-cache test
fi

# Display test configuration
echo "Running $TEST_TYPE tests in Docker..."

# Run the tests based on the type
case $TEST_TYPE in
  frontend)
    docker-compose run --rm test bash -c "npm run test:frontend"
    ;;
  backend)
    docker-compose run --rm test bash -c "/app/docker/run_backend_tests.sh"
    ;;
  all)
    docker-compose run --rm test bash -c "npm run test:frontend && /app/docker/run_backend_tests.sh"
    ;;
esac

# Show completion message
echo "Tests completed!"