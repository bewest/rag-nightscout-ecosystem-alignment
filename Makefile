# Nightscout Alignment Workspace Makefile
# Convenience wrapper for common operations

.PHONY: bootstrap status freeze clean help validate conformance coverage ci check submodules

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
	@echo "  make coverage   - Generate coverage matrix"
	@echo "  make check      - Run all checks (linkcheck + validate + conformance)"
	@echo "  make ci         - Run full CI pipeline locally"
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

# Run all checks (quick validation)
check: validate conformance
	@echo "Running link check..."
	@python3 tools/linkcheck.py
	@echo ""
	@echo "All checks passed!"

# Full CI pipeline
ci: check coverage
	@echo ""
	@echo "Checking Python syntax..."
	@python3 -m compileall tools/
	@echo ""
	@echo "CI pipeline complete!"
