# Settings Optimization Reports

Curated, cross-referenced reports on AID therapy settings optimization.

Unlike `docs/60-research/` (270+ AI-generated session drafts), reports here
are **verified against source code and experiment data** with explicit
file:line citations. Each claim can be independently checked.

## Documents

| Document | Audience | Description |
|----------|----------|-------------|
| [capabilities-guide.md](capabilities-guide.md) | **Tool users, clinicians** | What each advisory does, maturity matrix, practical sequencing, inputs/outputs |
| [research-foundations.md](research-foundations.md) | **Researchers, developers** | Paradoxes, evidence inventory, autotune comparison, disproved hypotheses, promising directions |
| [best-of-breed-settings-capabilities.md](best-of-breed-settings-capabilities.md) | **Reference** | Comprehensive source-cited reference with per-patient data and [SOURCE] citations |

**Start here**: If you want to *use* the pipeline → [Capabilities Guide](capabilities-guide.md).
If you want to *understand* the research → [Research Foundations](research-foundations.md).

## Other Reports

| Report | Date | Scope |
|--------|------|-------|
| [cr-sanity-check-contrast-report.md](cr-sanity-check-contrast-report.md) | 2026-04-18 | CR validation via detected meals + residual-integral estimation (EXP-2670) |

## Source Material

- **Research drafts**: `docs/60-research/therapy-settings-synthesis-2026-04-11.md` (primary synthesis)
- **Production code**: `tools/cgmencode/production/` (settings_advisor, settings_optimizer, etc.)
- **R&D experiments**: `tools/cgmencode/exp_*_26*.py` (EXP-2621 through EXP-2667)
- **Production experiments**: `tools/cgmencode/production/exp_*.py` (101 validation scripts)

## Verification Convention

Every quantitative claim in the comprehensive reference includes a **[SOURCE]** citation:
```
[SOURCE: file:line] or [SOURCE: file:line — "quoted constant or docstring"]
```
Readers can verify any claim by checking the cited file and line number.
