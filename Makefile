# Nightscout Alignment Workspace Makefile
# Convenience wrapper for common operations

.PHONY: bootstrap status freeze clean help validate conformance coverage inventory ci check submodules verify verify-refs verify-coverage verify-terminology verify-assertions query trace traceability validate-json workflow cli venv sdqctl-verify sdqctl-gen sdqctl-analysis conversions mock-nightscout

# Default target
help:
	@echo "Nightscout Alignment Workspace"
	@echo ""
	@echo "Available targets:"
	@echo ""
	@echo "Repository management:"
	@echo "  make bootstrap  - Clone/update all external repositories"
	@echo "  make submodules - Checkout submodules for repos with submodules flag"
	@echo "  make status     - Show status of all repositories"
	@echo "  make freeze     - Pin all repos to current commit SHAs"
	@echo "  make clean      - Remove all external checkouts (DESTRUCTIVE)"
	@echo ""
	@echo "Validation & Testing:"
	@echo "  make validate   - Validate fixtures against shape specs"
	@echo "  make conformance- Run conformance assertions (offline)"
	@echo "  make conversions- Run unit conversion tests"
	@echo "  make coverage   - Generate coverage matrix"
	@echo "  make inventory  - Generate workspace inventory"
	@echo "  make check      - Run all checks (linkcheck + validate + conformance)"
	@echo "  make ci         - Run full CI pipeline locally"
	@echo "  make mock-nightscout - Start mock Nightscout server (port 5555)"
	@echo ""
	@echo "Static Verification:"
	@echo "  make verify     - Run all static verification tools"
	@echo "  make verify-refs        - Verify code references resolve to files"
	@echo "  make verify-coverage    - Analyze requirement/gap coverage"
	@echo "  make verify-terminology - Check terminology consistency"
	@echo "  make verify-assertions  - Trace assertions to requirements"
	@echo ""
	@echo "New Tools (Enhanced Traceability):"
	@echo "  make query TERM=<term>  - Search documentation for term"
	@echo "  make trace ID=<id>      - Trace requirement or gap"
	@echo "  make traceability       - Generate full traceability matrix"
	@echo "  make validate-json      - Validate JSON/YAML files"
	@echo "  make workflow TYPE=<type> - Run automated workflow (quick/full/validation/verification)"
	@echo "  make cli                - Launch interactive workspace CLI"
	@echo ""
	@echo "  make help       - Show this help message"
	@echo ""
	@echo "To add a new repo:"
	@echo "  ./tools/bootstrap.py add <name> <url> [ref]"
	@echo ""
	@echo "To remove a repo:"
	@echo "  ./tools/bootstrap.py remove <name> [--delete]"

# Clone/update all repositories from lockfile
bootstrap:
	@echo "Bootstrapping workspace..."
	@python3 tools/bootstrap.py bootstrap

# Show status of all repositories
status:
	@python3 tools/bootstrap.py status

# Checkout submodules for repos with submodules flag
submodules:
	@echo "Checking out submodules..."
	@python3 tools/checkout_submodules.py all

# Freeze current SHAs to lockfile
freeze:
	@echo "Freezing repository states..."
	@python3 tools/bootstrap.py freeze

# Remove all external checkouts
clean:
	@echo "This will delete all cloned repositories in externals/"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	@rm -rf externals/*
	@touch externals/.keep
	@echo "Cleaned externals/"

# Validate fixtures against shape specs
validate:
	@echo "Validating fixtures..."
	@python3 tools/validate_fixtures.py

# Run conformance assertions (offline mode)
conformance:
	@echo "Running conformance tests..."
	@python3 tools/run_conformance.py

# Generate coverage matrix
coverage:
	@echo "Generating coverage matrix..."
	@python3 tools/gen_coverage.py

# Generate workspace inventory
inventory:
	@echo "Generating workspace inventory..."
	@python3 tools/gen_inventory.py

# Run all checks (quick validation)
check: validate conformance
	@echo "Running link check..."
	@python3 tools/linkcheck.py
	@echo ""
	@echo "All checks passed!"

# Run unit conversion tests
conversions:
	@echo "Running unit conversion tests..."
	@python3 tools/test_conversions.py

# Start mock Nightscout server
mock-nightscout:
	@echo "Starting mock Nightscout server on port 5555..."
	@python3 tools/mock_nightscout.py --port 5555

# Full CI pipeline
ci: check coverage verify
	@echo ""
	@echo "Checking Python syntax..."
	@python3 -m compileall tools/
	@echo ""
	@echo "CI pipeline complete!"

# Static verification tools (no external runtime required)
# Uses - prefix to continue even if individual tools find issues
verify:
	@echo "Running static verification suite..."
	@echo ""
	@echo "=== Verifying code references ==="
	-@python3 tools/verify_refs.py
	@echo ""
	@echo "=== Analyzing coverage ==="
	-@python3 tools/verify_coverage.py
	@echo ""
	@echo "=== Checking terminology consistency ==="
	-@python3 tools/verify_terminology.py
	@echo ""
	@echo "=== Tracing assertions ==="
	-@python3 tools/verify_assertions.py
	@echo ""
	@echo "Verification complete. See traceability/*.md for detailed reports."

# Individual verification targets (will fail on issues for CI use)
verify-refs:
	@echo "Verifying code references..."
	@python3 tools/verify_refs.py

verify-coverage:
	@echo "Analyzing coverage..."
	@python3 tools/verify_coverage.py

verify-terminology:
	@echo "Checking terminology consistency..."
	@python3 tools/verify_terminology.py

verify-assertions:
	@echo "Tracing assertions..."
	@python3 tools/verify_assertions.py

# New tooling targets

# Interactive query tool
query:
	@python3 tools/query_workspace.py --search "$(TERM)"

# Trace requirement or gap
trace:
	@python3 tools/query_workspace.py --req "$(ID)" || python3 tools/query_workspace.py --gap "$(ID)"

# Generate full traceability matrix
traceability:
	@echo "Generating traceability matrix..."
	@python3 tools/gen_traceability.py

# Validate JSON and YAML files
validate-json:
	@echo "Validating JSON/YAML files..."
	@python3 tools/validate_json.py

# Run automated workflows
workflow:
	@echo "Running $(TYPE) workflow..."
	@python3 tools/run_workflow.py --workflow $(TYPE)

# Interactive CLI
cli:
	@python3 tools/workspace_cli.py

# Python venv with sdqctl
venv:
	@if [ ! -d .venv ]; then \
		echo "Creating venv..."; \
		python3 -m venv .venv; \
		.venv/bin/pip install --quiet click pyyaml rich pydantic; \
	fi
	@echo "Activate with: source activate-sdqctl.sh"

# sdqctl workflow targets
sdqctl-verify:
	@echo "Running verification workflows..."
	@source activate-sdqctl.sh && sdqctl run workflows/full-verification.conv

sdqctl-gen:
	@echo "Running generation workflows..."
	@source activate-sdqctl.sh && sdqctl flow workflows/gen-*.conv

sdqctl-analysis:
	@echo "Running analysis workflows..."
	@source activate-sdqctl.sh && sdqctl flow workflows/gap-detection.conv workflows/cross-project-alignment.conv
