# Nightscout Alignment Workspace Makefile
# Convenience wrapper for common operations

.PHONY: bootstrap status freeze clean help

# Default target
help:
	@echo "Nightscout Alignment Workspace"
	@echo ""
	@echo "Available targets:"
	@echo "  make bootstrap  - Clone/update all external repositories"
	@echo "  make status     - Show status of all repositories"
	@echo "  make freeze     - Pin all repos to current commit SHAs"
	@echo "  make clean      - Remove all external checkouts (DESTRUCTIVE)"
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
