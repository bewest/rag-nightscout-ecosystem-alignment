# Nightscout PR Coherence Review Protocol

> **Purpose**: Systematic methodology for reviewing cgm-remote-monitor PRs  
> **Parent**: [tooling.md](../sdqctl-proposals/backlogs/tooling.md) #17  
> **Last Updated**: 2026-01-30

## Executive Summary

This protocol defines a repeatable process for reviewing Nightscout (cgm-remote-monitor) PRs against the ecosystem alignment workspace. It ensures coherence between PR changes and documented gaps, requirements, and proposals.

---

## Quick Reference Checklist

Use this checklist for each PR review:

```markdown
## PR #NNNN Review Checklist

### Identification
- [ ] PR number and title
- [ ] Author and date
- [ ] Files changed (count and key paths)

### Gap Alignment
- [ ] Search `traceability/` for related GAP-* IDs
- [ ] Check if PR addresses any documented gaps
- [ ] Note gaps that become RESOLVED or PARTIAL

### Requirement Alignment
- [ ] Search `traceability/` for related REQ-* IDs
- [ ] Check if PR implements any requirements
- [ ] Note requirements verified by this PR

### Proposal Alignment
- [ ] Check `docs/sdqctl-proposals/` for related proposals
- [ ] Verify PR aligns with proposed approach
- [ ] Note any divergence from proposals

### Ecosystem Impact
- [ ] Which AID systems affected? (Loop, AAPS, Trio, xDrip+)
- [ ] API compatibility (breaking/non-breaking)
- [ ] Sync behavior changes

### Recommendation
- [ ] Safe to merge / Needs review / Conflicts with alignment
- [ ] Priority (P1-P3)
- [ ] Dependencies on other PRs
```

---

## Detailed Review Process

### Step 1: PR Identification

Gather basic metadata:

```bash
# Get PR details from GitHub
gh pr view NNNN --repo nightscout/cgm-remote-monitor --json title,author,files,additions,deletions
```

| Field | Purpose |
|-------|---------|
| Title | Brief description of change |
| Author | Contributor context |
| Files | Scope of change |
| Size | Complexity indicator |

### Step 2: Gap Alignment Search

Search for related gaps in the workspace:

```bash
# Search for keywords from PR title/description
grep -r "keyword" traceability/

# Search specific gap categories
grep -r "GAP-API" traceability/
grep -r "GAP-SYNC" traceability/
grep -r "GAP-TZ" traceability/
```

**Gap Categories Relevant to Nightscout PRs**:

| Category | Description | File |
|----------|-------------|------|
| GAP-API-* | API behavior gaps | `traceability/api-gaps.md` |
| GAP-SYNC-* | Sync/identity gaps | `traceability/sync-identity-gaps.md` |
| GAP-TZ-* | Timezone handling | `traceability/api-gaps.md` |
| GAP-TREAT-* | Treatment handling | `traceability/treatment-gaps.md` |
| GAP-DB-* | Database/storage | `traceability/api-gaps.md` |

**Document findings**:

```markdown
### Gaps Addressed

| Gap ID | Status Before | Status After | Notes |
|--------|---------------|--------------|-------|
| GAP-TZ-001 | OPEN | RESOLVED | PR fixes timezone display |
| GAP-API-003 | OPEN | PARTIAL | Pagination improved, not complete |
```

### Step 3: Requirement Alignment Search

Check if PR implements documented requirements:

```bash
# Search requirements
grep -r "REQ-API" traceability/
grep -r "REQ-SYNC" traceability/
```

**Relevant Requirement Categories**:

| Category | Description | File |
|----------|-------------|------|
| REQ-API-* | API behavior | `traceability/api-requirements.md` |
| REQ-SYNC-* | Sync semantics | `traceability/sync-requirements.md` |
| REQ-TREAT-* | Treatment handling | `traceability/treatment-requirements.md` |

### Step 4: Proposal Alignment Check

Verify PR aligns with existing proposals:

```bash
# List relevant proposals
ls docs/sdqctl-proposals/*.md | xargs grep -l "keyword"

# Check specific proposals
cat docs/sdqctl-proposals/state-ontology-proposal.md
cat docs/sdqctl-proposals/lsp-integration-proposal.md
```

**Key Proposals to Check**:

| Proposal | Relevant PRs |
|----------|--------------|
| `state-ontology-proposal.md` | Sync behavior changes |
| `pr-adoption-sequencing.md` | Already sequenced PRs |
| `node-lts-upgrade.md` | Node.js version changes |
| `nocturne-modernization-analysis.md` | Architecture changes |

### Step 5: Ecosystem Impact Assessment

Evaluate impact on AID ecosystem:

| System | Check For |
|--------|-----------|
| **Loop** | Treatment sync, devicestatus format, prediction curves |
| **AAPS** | Treatment upload, profile sync, pump status |
| **Trio** | Same as Loop (oref1 algorithm) |
| **xDrip+** | CGM upload, treatment sync, follower mode |
| **Nightguard** | Alarm thresholds, data access |

**API Compatibility Matrix**:

| Change Type | Breaking? | Action |
|-------------|-----------|--------|
| New optional field | No | Document in specs |
| Required field change | Yes | Major version bump |
| Endpoint deprecation | Yes | Migration path needed |
| Response format change | Maybe | Check client parsers |

### Step 6: Generate Recommendation

Based on findings, provide recommendation:

```markdown
## Recommendation

**Verdict**: Safe to merge / Needs review / Conflicts with alignment

**Priority**: P1 (critical) / P2 (important) / P3 (nice-to-have)

**Dependencies**: 
- Requires PR #XXXX first
- Blocks PR #YYYY

**Action Items**:
1. Update GAP-XXX-NNN status in traceability/
2. Add PR to ecosystem-pr-analysis.md
3. Cross-reference in progress.md
```

---

## PR Review Output Template

Use this template for documenting reviews:

```markdown
# PR #NNNN Review: [Title]

**Reviewed**: YYYY-MM-DD  
**Reviewer**: [name]  
**PR**: https://github.com/nightscout/cgm-remote-monitor/pull/NNNN

## Summary

Brief description of what the PR does.

## Gap Alignment

| Gap ID | Status | Notes |
|--------|--------|-------|
| GAP-XXX-NNN | RESOLVED | Fully addresses gap |

## Requirement Alignment

| Req ID | Verified | Notes |
|--------|----------|-------|
| REQ-XXX-NNN | Yes | Implements requirement |

## Proposal Alignment

- Aligns with: [proposal name]
- Diverges from: [proposal name] because [reason]

## Ecosystem Impact

| System | Impact | Notes |
|--------|--------|-------|
| Loop | None | No sync changes |
| AAPS | Low | New optional field |

## Recommendation

**Verdict**: Safe to merge

**Priority**: P2

**Notes**: Ready for maintainer review.
```

---

## Integration with Workspace Tools

### Automated Gap Search

```bash
# Add to Makefile
pr-review-gaps:
	@echo "Searching for gaps related to PR..."
	@grep -r "$(KEYWORD)" traceability/ --include="*.md" | head -20

# Usage: make pr-review-gaps KEYWORD="timezone"
```

### PR Tracking in Backlogs

When reviewing a PR, update relevant backlogs:

1. **nightscout-api.md**: Add PR to triage section
2. **ECOSYSTEM-BACKLOG.md**: Update Recently Completed if merged
3. **progress.md**: Add review entry

### Cross-Reference Pattern

```markdown
**See also**:
- PR #8405: [Timezone display fix](https://github.com/nightscout/cgm-remote-monitor/pull/8405)
- GAP-TZ-001: Documented in `traceability/api-gaps.md`
- REQ-TZ-001: Documented in `traceability/api-requirements.md`
```

---

## Review Cadence

| Trigger | Action |
|---------|--------|
| New high-priority PR | Immediate review |
| Weekly triage | Review new PRs, update status |
| Pre-merge | Full checklist review |
| Post-merge | Update gaps, requirements, progress |

---

## Examples

### Example 1: PR #8405 Timezone Fix

```markdown
# PR #8405 Review: Fix timezone display

**Reviewed**: 2026-01-30  
**PR**: https://github.com/nightscout/cgm-remote-monitor/pull/8405

## Summary
Fixes timezone display to show device timezone for caregivers.

## Gap Alignment
| Gap ID | Status | Notes |
|--------|--------|-------|
| GAP-TZ-001 | RESOLVED | Display now shows device TZ |
| GAP-TZ-007 | PARTIAL | Server-side still uses local |

## Recommendation
**Verdict**: Safe to merge  
**Priority**: P2  
**Notes**: UX improvement for caregivers.
```

### Example 2: PR #8421 MongoDB 5x

```markdown
# PR #8421 Review: MongoDB 5x Support

**Reviewed**: 2026-01-30  
**PR**: https://github.com/nightscout/cgm-remote-monitor/pull/8421

## Summary
Updates MongoDB driver for 5.x compatibility.

## Gap Alignment
| Gap ID | Status | Notes |
|--------|--------|-------|
| GAP-DB-001 | RESOLVED | Driver updated |
| GAP-NODE-001 | PARTIAL | Enables but doesn't require Node 20 |

## Ecosystem Impact
| System | Impact | Notes |
|--------|--------|-------|
| All | High | Prerequisite for modern deployments |

## Recommendation
**Verdict**: Safe to merge (after testing)  
**Priority**: P1  
**Dependencies**: Should merge before #7791 (Lodash removal)
```

---

## References

- [cgm-remote-monitor PR Analysis](cgm-remote-monitor-pr-analysis.md)
- [PR Adoption Sequencing](../sdqctl-proposals/pr-adoption-sequencing.md)
- [Nightscout Maintainer Recommendations](nightscout-maintainer-recommendations.md)
- [Gap Tracking](../../traceability/gaps.md)
