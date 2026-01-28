# Live Backlog

**Purpose**: Midflight task queue for active sdqctl processing sessions.

This file is the dynamic work surface used by `backlog-cycle.conv` to track:
- Currently active task (exactly 1)
- Immediate next items (2-3)
- Open questions surfaced during processing
- Findings ready to integrate

---

## Active Task

> The backlog processor selects ONE task here and works it to completion.

**None** - Ready for task selection.

---

## Immediate Queue (Next 3)

Items staged for immediate work. Processor promotes one to Active Task.

1. **[P1] Compare remote bolus command handling**
   - Source: `ECOSYSTEM-BACKLOG.md` Ready Queue
   - Repos: Loop, AAPS, Trio, Nightscout
   - Focus: Validation, execution, safety interlocks
   - Workflow: `compare-feature.conv`

2. **[P1] Extract AAPS NSClient upload schema**
   - Source: `ECOSYSTEM-BACKLOG.md` Ready Queue  
   - Path: `externals/AndroidAPS/core/nssdk/`
   - Focus: Document all Nightscout upload fields
   - Workflow: `extract-spec.conv`

3. **[P1] Compare override/profile switch semantics**
   - Source: `ECOSYSTEM-BACKLOG.md` Ready Queue
   - Repos: Loop, AAPS, Trio
   - Focus: Loop overrides vs AAPS ProfileSwitch
   - Workflow: `compare-feature.conv`

---

## Open Questions

Questions surfaced during processing that need human review.

> None yet.

---

## Findings to Integrate

Work completed that needs archival or integration into project docs.

| Finding | Source Task | Destination | Status |
|---------|-------------|-------------|--------|
| (none yet) | | | |

---

## Related Backlogs

Other backlogs to consult when generating new tasks or priorities:

| Backlog | Location | Purpose |
|---------|----------|---------|
| **ECOSYSTEM-BACKLOG** | `docs/sdqctl-proposals/ECOSYSTEM-BACKLOG.md` | Primary prioritized queue |
| (future) | `docs/sdqctl-proposals/UPSTREAM-BACKLOG.md` | Contributions to upstream repos |
| (future) | `docs/OPEN-QUESTIONS.md` | Blocked items needing research |

---

## Backlog Processor Rules

1. **Active Task**: Exactly 1 at a time. Work to completion or block.
2. **Immediate Queue**: Keep at 3 items. Replenish from related backlogs.
3. **Open Questions**: Surface here. Human clears or archives.
4. **Findings**: Document here, then integrate to permanent locations.
5. **Stale Items**: If untouched >3 cycles, demote or archive.
6. **New Discoveries**: Add to `ECOSYSTEM-BACKLOG.md` at appropriate priority.

---

## Session Log

| Timestamp | Action | Details |
|-----------|--------|---------|
| (new) | Backlog created | Ready for first cycle |

