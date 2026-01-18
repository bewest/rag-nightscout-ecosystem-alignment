# Quick Reference: Tooling for AI Agents and Interactive Use

## TL;DR - Most Common Commands

```bash
# Interactive exploration
make cli

# Quick validation
make workflow TYPE=quick

# Search documentation
make query TERM="authentication"

# Trace a requirement
make trace ID=REQ-001

# Generate traceability reports
make traceability

# Validate all JSON/YAML
make validate-json
```

## For AI Agents (JSON Output)

### Query Operations

```bash
# What tests cover a requirement?
python3 tools/query_workspace.py --tests-for REQ-001 --json

# Find all docs mentioning a term
python3 tools/query_workspace.py --search "sync" --json

# Get requirement details
python3 tools/query_workspace.py --req REQ-001 --json

# Get gap details
python3 tools/query_workspace.py --gap GAP-SYNC-001 --json
```

### Validation Operations

```bash
# Validate all files
python3 tools/validate_json.py --json

# Quick validation workflow
python3 tools/run_workflow.py --workflow quick --json

# Full validation workflow
python3 tools/run_workflow.py --workflow full --json
```

### Traceability Operations

```bash
# Generate full traceability matrix
python3 tools/gen_traceability.py --json

# Get requirements matrix only
python3 tools/gen_traceability.py --type requirements --json

# Get gaps matrix only
python3 tools/gen_traceability.py --type gaps --json
```

### Common Patterns

```bash
# Check if requirement has tests (exit code 0 = has tests)
python3 tools/query_workspace.py --tests-for REQ-001 --json | \
  jq -e 'length > 0'

# Find untested requirements
python3 tools/gen_traceability.py --type requirements --json | \
  jq '.gaps.untested[]'

# Get test coverage percentage
python3 tools/gen_traceability.py --type requirements --json | \
  jq '.coverage.testing'

# List all requirements
python3 tools/query_workspace.py --json <<< "list reqs"
```

## Interactive Mode

### Workspace CLI

```bash
python3 tools/workspace_cli.py
# or
make cli

# Then use commands:
workspace> status
workspace> validate
workspace> query authentication
workspace> trace REQ-001
workspace> coverage
workspace> help
workspace> exit
```

### Query Tool Interactive

```bash
python3 tools/query_workspace.py

# Then use commands:
> req REQ-001
> gap GAP-SYNC-001
> search authentication
> tests REQ-001
> term basal
> list reqs
> list gaps
> quit
```

## Workflow Types

| Workflow | Speed | Coverage | Use Case |
|----------|-------|----------|----------|
| `quick` | Fast | Basic | Pre-commit check |
| `validation` | Medium | Files | Validate JSON/YAML |
| `verification` | Medium | Static | Code refs, coverage |
| `coverage` | Slow | Full | Generate reports |
| `full` | Slowest | Complete | CI/CD pipeline |

## Output Formats

### Human-Readable (Default)

```bash
python3 tools/query_workspace.py --req REQ-001
# Outputs formatted text
```

### Machine-Readable (JSON)

```bash
python3 tools/query_workspace.py --req REQ-001 --json
# Outputs structured JSON
```

### Both

```bash
# Human-readable to console, JSON to file
python3 tools/gen_traceability.py | tee /dev/tty | \
  python3 tools/gen_traceability.py --json > report.json
```

## Integration Examples

### Pre-Commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit

echo "Running quick validation..."
python3 tools/run_workflow.py --workflow quick

if [ $? -ne 0 ]; then
  echo "Validation failed. Commit aborted."
  exit 1
fi
```

### CI/CD Integration

```yaml
# .github/workflows/custom.yml
- name: Run validation
  run: python3 tools/run_workflow.py --workflow full --json > results.json

- name: Check results
  run: |
    python3 -c "
    import json, sys
    data = json.load(open('results.json'))
    sys.exit(0 if data['success'] else 1)
    "
```

### Agent Prompt Template

```
Before making changes to documentation:
1. Run: python3 tools/query_workspace.py --search "<topic>" --json
2. Review existing coverage
3. Make minimal changes
4. Validate: python3 tools/run_workflow.py --workflow quick --json
```

## Error Handling

### Check Exit Codes

```bash
python3 tools/validate_json.py
if [ $? -eq 0 ]; then
  echo "All valid"
else
  echo "Validation errors found"
fi
```

### Parse JSON Errors

```bash
python3 tools/validate_json.py --json | \
  jq '.results[] | select(.valid == false)'
```

### Fail Fast

```bash
# Stop on first error
python3 tools/run_workflow.py --workflow full --fail-fast
```

## Tips

1. **Always use `--json` for automation** - Easier to parse
2. **Use `jq` for JSON processing** - Filter and extract data
3. **Check exit codes** - Non-zero = error
4. **Start with `quick` workflow** - Fast feedback
5. **Generate traceability regularly** - Track coverage over time

## File Locations

| Type | Location |
|------|----------|
| Tools | `tools/*.py` |
| Traceability Reports | `traceability/*.md` and `traceability/*.json` |
| Workflows | `.github/workflows/*.yml` |
| Documentation | `docs/` |
| Requirements | `traceability/requirements.md` |
| Gaps | `traceability/gaps.md` |
| Assertions | `conformance/assertions/*.yaml` |
| Schemas | `specs/jsonschema/*.schema.json` |
| Shapes | `specs/shape/*.shape.json` |
| OpenAPI | `specs/openapi/*.yaml` |

## Common Issues

### "Tool not found"

```bash
# Make sure you're in workspace root
cd /path/to/rag-nightscout-ecosystem-alignment

# Or use absolute paths
python3 /absolute/path/tools/query_workspace.py
```

### "Module not found"

```bash
# Optional dependencies
pip install pyyaml jsonschema

# But tools work without them (fallback mode)
```

### "No results found"

```bash
# Check if files exist
ls -la traceability/requirements.md
ls -la conformance/assertions/

# Generate if missing
make traceability
```

## Learning Path

1. **Start here**: `make cli` (interactive exploration)
2. **Try searching**: `make query TERM="sync"`
3. **Check a requirement**: `make trace ID=REQ-001`
4. **Run validation**: `make workflow TYPE=quick`
5. **Generate reports**: `make traceability`
6. **Read full guide**: `docs/TOOLING-GUIDE.md`

## Support

- Full documentation: `docs/TOOLING-GUIDE.md`
- Tool help: `python3 tools/<tool>.py --help`
- Makefile targets: `make help`
- Roadmap: `docs/tooling-roadmap.md`
