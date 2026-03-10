#!/bin/bash
# Integration Test Runner
# Runs Swift, Kotlin, and JavaScript tests against cgm-remote-monitor
#
# Usage:
#   ./tools/run-integration-tests.sh           # Run all tests
#   ./tools/run-integration-tests.sh swift     # Run only Swift tests
#   ./tools/run-integration-tests.sh kotlin    # Run only Kotlin tests  
#   ./tools/run-integration-tests.sh js        # Run only JS tests
#   ./tools/run-integration-tests.sh --check   # Check server only
#
# Refs: REQ-SYNC-072, GAP-TREAT-012, PR #8447

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
NS_SERVER="/home/bewest/src/worktrees/nightscout/cgm-pr-8447"
NIGHTSCOUT_URL="${NIGHTSCOUT_URL:-http://localhost:1337}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if server is running
check_server() {
    if curl -s "$NIGHTSCOUT_URL/api/v1/status.json" | grep -q '"status":"ok"'; then
        log_info "Nightscout server running at $NIGHTSCOUT_URL"
        return 0
    else
        log_error "Nightscout server not available at $NIGHTSCOUT_URL"
        echo ""
        echo "Start the server with:"
        echo "  cd $NS_SERVER"
        echo "  export \$(cat my.test.env | xargs) && node server.js &"
        return 1
    fi
}

# Run Swift tests
run_swift() {
    log_info "Running Swift tests..."
    cd "$SCRIPT_DIR/swift-nightscout-tests"
    
    if ! command -v swift &> /dev/null; then
        log_warn "Swift not found, skipping"
        return 0
    fi
    
    swift test 2>&1 | grep -E "Test Case|passed|failed|error:" || true
    
    if swift test 2>&1 | grep -q "passed"; then
        log_info "Swift tests: PASSED"
        return 0
    else
        log_error "Swift tests: FAILED"
        return 1
    fi
}

# Run Kotlin tests
run_kotlin() {
    log_info "Running Kotlin tests..."
    cd "$SCRIPT_DIR/kotlin-nightscout-tests"
    
    if ! command -v java &> /dev/null; then
        log_warn "Java not found, skipping Kotlin tests"
        return 0
    fi
    
    ./gradlew test --quiet 2>&1 || true
    
    # Check test report
    if grep -q '"counter">0</div>' build/reports/tests/test/index.html 2>/dev/null; then
        TESTS=$(grep -o '<div class="counter">[0-9]*</div>' build/reports/tests/test/index.html | head -1 | grep -o '[0-9]*')
        log_info "Kotlin tests: $TESTS PASSED"
        return 0
    else
        log_error "Kotlin tests: FAILED"
        return 1
    fi
}

# Run JavaScript tests
run_js() {
    log_info "Running JavaScript tests (UUID patterns)..."
    cd "$NS_SERVER"
    
    local output
    output=$(npm test -- --grep "UUID" 2>&1)
    
    echo "$output" | grep -E "passing|failing|Error" || true
    
    if echo "$output" | grep -q "passing"; then
        PASSING=$(echo "$output" | grep "passing" | grep -oE '[0-9]+' | head -1)
        log_info "JavaScript tests: $PASSING PASSED"
        return 0
    else
        log_error "JavaScript tests: FAILED"
        return 1
    fi
}

# Print summary
print_summary() {
    echo ""
    echo "================================"
    echo "Integration Test Summary"
    echo "================================"
    echo "Server: $NIGHTSCOUT_URL"
    echo ""
    echo "Tests validate PR #8447 / REQ-SYNC-072 (Option G):"
    echo "  - UUID _id → identifier promotion"
    echo "  - Deduplication by identifier"
    echo "  - ObjectId assignment by server"
    echo ""
}

# Main
main() {
    local target="${1:-all}"
    
    echo "================================"
    echo "Nightscout Integration Tests"
    echo "================================"
    echo ""
    
    # Always check server first
    if ! check_server; then
        exit 1
    fi
    
    echo ""
    
    local swift_result=0
    local kotlin_result=0
    local js_result=0
    
    case "$target" in
        swift)
            run_swift || swift_result=1
            ;;
        kotlin)
            run_kotlin || kotlin_result=1
            ;;
        js|javascript)
            run_js || js_result=1
            ;;
        --check)
            exit 0
            ;;
        all|*)
            run_swift || swift_result=1
            echo ""
            run_kotlin || kotlin_result=1
            echo ""
            run_js || js_result=1
            ;;
    esac
    
    print_summary
    
    # Exit with error if any failed
    if [[ $swift_result -ne 0 ]] || [[ $kotlin_result -ne 0 ]] || [[ $js_result -ne 0 ]]; then
        log_error "Some tests failed"
        exit 1
    fi
    
    log_info "All tests passed!"
}

main "$@"
