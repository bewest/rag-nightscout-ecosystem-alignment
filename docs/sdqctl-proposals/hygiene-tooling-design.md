# Autonomous Workflow Hygiene Tooling - Design Specification

> **Purpose**: Tools to help sdqctl workflows maintain document hygiene  
> **Created**: 2026-01-29  
> **Status**: Design Phase

---

## Design Decisions

| Decision | Choice |
|----------|--------|
| Chunking strategy | Align with domain backlogs |
| File structure | Index + sibling domain files |
| Traceability threshold | 800 lines |
| Backlog/progress threshold | 500 lines |
| Trigger action | Refactor/reorganize/chunk |

---

## Target File Structure

### Gaps (after chunking)
```
traceability/
├── gaps.md                    # Index + recent/active gaps (< 800 lines)
├── cgm-sources-gaps.md        # GAP-CGM-*, GAP-G7-*, GAP-LIBRE-*
├── sync-identity-gaps.md      # GAP-SYNC-*, GAP-BATCH-*, GAP-TZ-*
├── nightscout-api-gaps.md     # GAP-API-*, GAP-AUTH-*, GAP-UI-*
├── aid-algorithms-gaps.md     # GAP-ALG-*, GAP-OREF-*, GAP-PRED-*
├── treatments-gaps.md         # GAP-TREAT-*, GAP-OVERRIDE-*, GAP-REMOTE-*
└── resolved-gaps.md           # Archived/resolved gaps
```

### Requirements (after chunking)
```
traceability/
├── requirements.md            # Index + core requirements (< 800 lines)
├── sync-requirements.md       # REQ-030-039
├── treatment-requirements.md  # REQ-040-049
├── cgm-requirements.md        # REQ-050-059
├── api-requirements.md        # REQ-API-*
└── archived-requirements.md   # Deprecated/superseded
```

### Progress (after chunking)
```
├── progress.md                # Last 30 days (< 500 lines)
└── progress-archive/
    ├── 2026-01.md             # January 2026 entries
    └── ...
```

---

## Tool 1: `queue_stats.py`

### Purpose
Quick one-line status for workflow Phase 0 state checks.

### Interface
```bash
# One-line output (default)
python tools/queue_stats.py

# JSON output for programmatic use
python tools/queue_stats.py --json

# Full dashboard
python tools/queue_stats.py --dashboard
```

### Output Formats

**One-line** (for RUN integration):
```
Queues: LIVE=0/30 Ready=5/10 | Files: gaps=4403⚠️ reqs=2596⚠️ prog=1519⚠️ | Uncommitted: 11
```

**JSON**:
```json
{
  "queues": {
    "live_pending": 0,
    "live_processed": 30,
    "ready_queue": 5
  },
  "files": {
    "gaps.md": {"lines": 4403, "threshold": 800, "over": true},
    "requirements.md": {"lines": 2596, "threshold": 800, "over": true},
    "progress.md": {"lines": 1519, "threshold": 500, "over": true}
  },
  "git": {
    "uncommitted": 11,
    "untracked": 6
  },
  "health": "warning",
  "recommendations": [
    "Chunk gaps.md (4403 > 800)",
    "Chunk requirements.md (2596 > 800)",
    "Archive old progress entries (1519 > 500)"
  ]
}
```

### Implementation Sketch
```python
#!/usr/bin/env python3
"""Quick queue and file status for workflow integration."""

import json
import subprocess
import re
from pathlib import Path

THRESHOLDS = {
    "traceability/gaps.md": 800,
    "traceability/requirements.md": 800,
    "progress.md": 500,
    "docs/sdqctl-proposals/ECOSYSTEM-BACKLOG.md": 500,
    "LIVE-BACKLOG.md": 100,
}

def count_lines(path):
    try:
        return sum(1 for _ in open(path))
    except FileNotFoundError:
        return 0

def count_live_pending():
    """Count bullet points before ## Processed section."""
    content = Path("LIVE-BACKLOG.md").read_text()
    # Find content before ## Processed
    match = re.search(r'^(.*?)^## Processed', content, re.MULTILINE | re.DOTALL)
    if match:
        header_section = match.group(1)
        return len(re.findall(r'^\* ', header_section, re.MULTILINE))
    return 0

def count_live_processed():
    """Count rows in Processed table."""
    content = Path("LIVE-BACKLOG.md").read_text()
    return len(re.findall(r'^\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|$', content, re.MULTILINE)) - 1  # minus header

def count_ready_queue():
    """Count items in Ready Queue section."""
    content = Path("docs/sdqctl-proposals/ECOSYSTEM-BACKLOG.md").read_text()
    return len(re.findall(r'^### \d+\.', content, re.MULTILINE))

def git_status():
    """Get uncommitted file counts."""
    result = subprocess.run(["git", "status", "--short"], capture_output=True, text=True)
    lines = result.stdout.strip().split('\n') if result.stdout.strip() else []
    modified = sum(1 for l in lines if l.startswith(' M') or l.startswith('M '))
    untracked = sum(1 for l in lines if l.startswith('??'))
    return modified + untracked, untracked

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--dashboard', action='store_true')
    args = parser.parse_args()
    
    # Collect stats
    live_pending = count_live_pending()
    live_processed = count_live_processed()
    ready = count_ready_queue()
    uncommitted, untracked = git_status()
    
    files = {}
    recommendations = []
    for path, threshold in THRESHOLDS.items():
        lines = count_lines(path)
        over = lines > threshold
        files[path] = {"lines": lines, "threshold": threshold, "over": over}
        if over:
            recommendations.append(f"Chunk {path} ({lines} > {threshold})")
    
    if args.json:
        print(json.dumps({
            "queues": {"live_pending": live_pending, "live_processed": live_processed, "ready_queue": ready},
            "files": files,
            "git": {"uncommitted": uncommitted, "untracked": untracked},
            "health": "warning" if recommendations else "healthy",
            "recommendations": recommendations
        }, indent=2))
    else:
        # One-line format
        gaps = files.get("traceability/gaps.md", {})
        reqs = files.get("traceability/requirements.md", {})
        prog = files.get("progress.md", {})
        
        g = "⚠️" if gaps.get("over") else ""
        r = "⚠️" if reqs.get("over") else ""
        p = "⚠️" if prog.get("over") else ""
        
        print(f"Queues: LIVE={live_pending}/{live_processed} Ready={ready}/10 | "
              f"Files: gaps={gaps.get('lines', 0)}{g} reqs={reqs.get('lines', 0)}{r} prog={prog.get('lines', 0)}{p} | "
              f"Uncommitted: {uncommitted}")

if __name__ == "__main__":
    main()
```

---

## Tool 2: `backlog_hygiene.py`

### Purpose
Validate and maintain backlog queue structure.

### Interface
```bash
# Check queue health
python tools/backlog_hygiene.py --check

# Validate structure (markdown tables, sections)
python tools/backlog_hygiene.py --validate

# Archive completed items older than N days
python tools/backlog_hygiene.py --archive-completed --days 14

# Demote stale items (not touched in N cycles)
python tools/backlog_hygiene.py --demote-stale --cycles 3

# Dry run (show what would change)
python tools/backlog_hygiene.py --archive-completed --days 14 --dry-run
```

### Validation Rules

1. **LIVE-BACKLOG.md**:
   - No pending items (bullet points before Processed)
   - Processed table has valid structure
   - All items have dates

2. **ECOSYSTEM-BACKLOG.md**:
   - Ready Queue has 5-10 items
   - Each item has Type, Effort, Source
   - Completed table entries have dates and outcomes

3. **Domain backlogs**:
   - Active Items table has Priority, Effort columns
   - Completed table exists

### Output
```json
{
  "live_backlog": {
    "pending_count": 0,
    "processed_count": 30,
    "issues": []
  },
  "ecosystem_backlog": {
    "ready_queue_count": 5,
    "ready_queue_target": [5, 10],
    "issues": ["Ready queue below target (5 < 5)"]
  },
  "domain_backlogs": {
    "cgm-sources.md": {"active": 8, "completed": 3, "issues": []},
    "sync-identity.md": {"active": 7, "completed": 3, "issues": []}
  },
  "recommendations": [
    "Replenish Ready Queue from P1 backlog"
  ]
}
```

---

## Tool 3: `doc_chunker.py`

### Purpose
Analyze and chunk oversized documentation files.

### Interface
```bash
# Check which files need chunking
python tools/doc_chunker.py --check

# Analyze a specific file's structure
python tools/doc_chunker.py --analyze traceability/gaps.md

# Preview chunk plan (dry run)
python tools/doc_chunker.py --plan traceability/gaps.md

# Execute chunking
python tools/doc_chunker.py --chunk traceability/gaps.md

# Archive old progress entries
python tools/doc_chunker.py --archive-progress --keep-days 30
```

### Chunking Logic

**For gaps.md**:
1. Parse all `### GAP-XXX-NNN` headings
2. Map prefix to domain:
   - `GAP-CGM-*`, `GAP-G7-*`, `GAP-LIBRE-*` → `cgm-sources-gaps.md`
   - `GAP-SYNC-*`, `GAP-BATCH-*`, `GAP-TZ-*` → `sync-identity-gaps.md`
   - `GAP-API-*`, `GAP-AUTH-*`, `GAP-UI-*` → `nightscout-api-gaps.md`
   - `GAP-ALG-*`, `GAP-OREF-*`, `GAP-PRED-*` → `aid-algorithms-gaps.md`
   - `GAP-TREAT-*`, `GAP-OVERRIDE-*`, `GAP-REMOTE-*` → `treatments-gaps.md`
3. Create domain files with gaps
4. Update gaps.md to be index only:
   - Keep header/intro
   - Add links to domain files
   - Keep "Recently Added" section (last 10)

**For requirements.md**:
1. Parse all `### REQ-NNN` headings
2. Map by number range to domain
3. Similar chunking approach

**For progress.md**:
1. Parse all `### Title (YYYY-MM-DD)` entries
2. Keep entries from last 30 days in progress.md
3. Move older entries to `progress-archive/YYYY-MM.md`

### Output (--plan)
```json
{
  "source": "traceability/gaps.md",
  "current_lines": 4403,
  "threshold": 800,
  "plan": {
    "index": {
      "file": "traceability/gaps.md",
      "estimated_lines": 150,
      "content": "Header + links + recent gaps"
    },
    "chunks": [
      {"file": "traceability/cgm-sources-gaps.md", "gaps": 25, "estimated_lines": 600},
      {"file": "traceability/sync-identity-gaps.md", "gaps": 30, "estimated_lines": 720},
      {"file": "traceability/nightscout-api-gaps.md", "gaps": 45, "estimated_lines": 1080},
      {"file": "traceability/aid-algorithms-gaps.md", "gaps": 20, "estimated_lines": 480},
      {"file": "traceability/treatments-gaps.md", "gaps": 35, "estimated_lines": 840}
    ]
  },
  "warnings": [
    "nightscout-api-gaps.md will be over threshold (1080 > 800) - consider sub-chunking"
  ]
}
```

---

## Tool 4: sdqctl Plugin Directives

### .sdqctl/directives.yaml additions
```yaml
version: 1
directives:
  # Existing...
  
  HYGIENE:
    queue-stats:
      handler: python tools/queue_stats.py --json
      description: "Get queue and file size statistics"
      timeout: 10
    
    check-queues:
      handler: python tools/backlog_hygiene.py --check --json
      description: "Validate backlog queue health"
      timeout: 30
    
    check-sizes:
      handler: python tools/doc_chunker.py --check --json
      description: "Check file sizes against thresholds"
      timeout: 30
    
    archive-old:
      handler: python tools/backlog_hygiene.py --archive-completed --days 14
      description: "Archive completed items older than 14 days"
      timeout: 60
    
    chunk-plan:
      handler: python tools/doc_chunker.py --plan-all --json
      description: "Generate chunking plan for oversized files"
      timeout: 60
```

### Workflow Integration (backlog-cycle-v3.conv)
```conv
# Phase 0: Hygiene Check
PROMPT ## Phase 0: State & Hygiene Check

RUN python tools/queue_stats.py 2>/dev/null || echo "Stats: unavailable"
RUN git --no-pager status --short

PROMPT Review the status above:
1. Are any files over threshold (⚠️)?
2. Are there uncommitted changes?
3. Is the Ready Queue at target (5-10)?

If files are over threshold:
- Add "Chunk {file}" to Ready Queue if not present
- Consider this a P1 maintenance task

# ... rest of workflow ...

# Phase 6: Post-cycle hygiene
PROMPT ## Phase 6: Cycle Summary & Hygiene

RUN python tools/queue_stats.py 2>/dev/null || echo "Stats: unavailable"

PROMPT Verify:
- [ ] All work committed
- [ ] No new files over threshold
- [ ] Ready Queue replenished
```

---

## Implementation Plan

### Phase 1: Core Tools (P0)
- [ ] Create `tools/queue_stats.py` - one-line status
- [ ] Add to backlog-cycle-v2.conv Phase 0

### Phase 2: Validation (P1)
- [ ] Create `tools/backlog_hygiene.py` - queue validation
- [ ] Create `tools/doc_chunker.py --check` - size checking

### Phase 3: Automation (P1)
- [ ] Add chunking logic to `doc_chunker.py`
- [ ] Add archive logic to `backlog_hygiene.py`

### Phase 4: Integration (P2)
- [ ] Add HYGIENE directives to `.sdqctl/directives.yaml`
- [ ] Create `backlog-cycle-v3.conv` with full hygiene integration

---

## Testing Strategy

### Unit Tests
```python
def test_count_live_pending():
    # Test with sample LIVE-BACKLOG content
    
def test_gap_prefix_mapping():
    # Verify GAP-CGM-001 maps to cgm-sources-gaps.md
    
def test_chunking_preserves_content():
    # Verify no content lost during chunk
```

### Integration Tests
```bash
# Verify one-liner works in workflow
RUN python tools/queue_stats.py

# Verify JSON parseable
RUN python tools/queue_stats.py --json | python -c "import sys,json; json.load(sys.stdin)"
```

---

## Success Criteria

1. **Visibility**: Workflow always shows current queue/file status
2. **Prevention**: Warnings before files exceed threshold
3. **Automation**: One command to chunk oversized files
4. **Consistency**: Domain alignment between backlogs and traceability files
