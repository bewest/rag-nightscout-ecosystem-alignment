---
name: sdqctl-verify
description: Validate and inspect sdqctl workflow files without LLM calls
tools:
  - bash
---

# sdqctl Verification Skill

Use this skill to validate, inspect, and dry-run sdqctl workflows.
All commands in this skill run **without LLM calls** and are safe for CI/CD.

## Validate Workflow Syntax

Check that a `.conv` file has valid syntax:

```bash
sdqctl validate <workflow.conv>
```

Returns validation status and any syntax errors.

## Show Parsed Structure

Display the internal representation of a workflow:

```bash
sdqctl show <workflow.conv>
```

Shows: model, adapter, mode, prompts, context patterns, output config.

## Preview Execution (Dry Run)

See what would happen without actually running:

```bash
sdqctl run <workflow.conv> --dry-run
```

Shows configuration and prompts that would be sent.

## Test with Mock Adapter

Run the full workflow mechanics without LLM calls:

```bash
sdqctl run <workflow.conv> --adapter mock --verbose
```

Uses canned responses to test workflow flow, checkpoints, and output.

## Check System Status

```bash
# Overview
sdqctl status

# Available adapters
sdqctl status --adapters

# Active sessions
sdqctl status --sessions
```

## Validate All Workflows

```bash
for f in workflows/*.conv; do
  sdqctl validate "$f" || echo "FAILED: $f"
done
```

## When to Use This Skill

- **Before committing**: Validate new/modified `.conv` files
- **In CI/CD**: Verify workflow definitions are valid
- **During review**: Inspect what a workflow will do
- **Debugging**: Test workflow mechanics with mock adapter
