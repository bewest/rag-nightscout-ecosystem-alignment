# Settings Optimization Reports

Curated, cross-referenced reports on AID therapy settings optimization.

Unlike `docs/60-research/` (270+ AI-generated session drafts), reports here
are **verified against source code and experiment data** with explicit
file:line citations. Each claim can be independently checked.

## Reports

| Report | Date | Scope |
|--------|------|-------|
| [best-of-breed-settings-capabilities.md](best-of-breed-settings-capabilities.md) | 2026-04-18 | Complete capability map: ISF, CR, basal advisories across Loop/Trio/AAPS/oref0 |

## Source Material

- **Research drafts**: `docs/60-research/therapy-settings-synthesis-2026-04-11.md` (primary synthesis)
- **Production code**: `tools/cgmencode/production/` (settings_advisor, settings_optimizer, etc.)
- **R&D experiments**: `tools/cgmencode/exp_*_26*.py` (EXP-2621 through EXP-2662)
- **Production experiments**: `tools/cgmencode/production/exp_*.py` (101 validation scripts)

## Verification Convention

Every quantitative claim includes a **[SOURCE]** citation in the format:
```
[SOURCE: file:line] or [SOURCE: file:line — "quoted constant or docstring"]
```
Readers can verify any claim by checking the cited file and line number.
