#!/bin/bash
# Test runner script for Aigent

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🧪 Aigent Test Suite"
echo "==================="
echo ""

# Parse arguments
RUN_E2E=false
RUN_UNIT=true
RUN_INTEGRATION=false
VERBOSE=""
COVERAGE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --e2e)
            RUN_E2E=true
            shift
            ;;
        --integration)
            RUN_INTEGRATION=true
            shift
            ;;
        --all)
            RUN_E2E=true
            RUN_INTEGRATION=true
            shift
            ;;
        --only-e2e)
            RUN_E2E=true
            RUN_UNIT=false
            shift
            ;;
        --coverage)
            COVERAGE=true
            shift
            ;;
        -v|--verbose)
            VERBOSE="-v"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --e2e           Run E2E tests (costs LLM tokens)"
            echo "  --integration   Run integration tests"
            echo "  --all           Run all test types"
            echo "  --only-e2e      Run only E2E tests"
            echo "  --coverage      Generate coverage report"
            echo "  -v, --verbose   Verbose output"
            echo "  -h, --help      Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Install test dependencies if needed
if ! python -m pytest --version > /dev/null 2>&1; then
    echo -e "${YELLOW}Installing test dependencies...${NC}"
    pip install -r requirements-test.txt
fi

# Build pytest command
PYTEST_CMD="python -m pytest $VERBOSE"

if [ "$COVERAGE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --cov=src/aigent --cov-report=term-missing --cov-report=html"
fi

# Run unit tests
if [ "$RUN_UNIT" = true ]; then
    echo -e "${GREEN}Running Unit Tests...${NC}"
    $PYTEST_CMD tests/unit/ || true
    echo ""
fi

# Run integration tests
if [ "$RUN_INTEGRATION" = true ]; then
    echo -e "${GREEN}Running Integration Tests...${NC}"
    $PYTEST_CMD tests/integration/ --run-integration || true
    echo ""
fi

# Run E2E tests
if [ "$RUN_E2E" = true ]; then
    echo -e "${YELLOW}⚠️  Running E2E Tests (will use LLM tokens)...${NC}"
    read -p "Continue? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then

        # Install playwright browsers if needed
        if ! playwright --version > /dev/null 2>&1; then
            echo "Installing Playwright browsers..."
            playwright install chromium
        fi

        # Run E2E tests
        $PYTEST_CMD tests/e2e/ --e2e || true
    else
        echo "Skipping E2E tests"
    fi
    echo ""
fi

# Run critical CLI rendering tests
echo -e "${GREEN}Running Critical CLI Rendering Tests...${NC}"
$PYTEST_CMD tests/unit/test_cli_rendering.py -v || true

# Summary
echo ""
echo "==================="
echo "Test Run Complete!"

if [ "$COVERAGE" = true ]; then
    echo ""
    echo "Coverage report generated at: htmlcov/index.html"
    echo "Run 'open htmlcov/index.html' to view the report"
fi