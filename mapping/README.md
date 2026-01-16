# Project Mappings

This directory contains detailed behavior documentation and Nightscout API mappings for each AID ecosystem project.

## Project Index

| Project | Directory | Description |
|---------|-----------|-------------|
| **Nightscout** | [nightscout/](nightscout/) | Core Nightscout CGM Remote Monitor |
| **Loop** | [loop/](loop/) | iOS closed-loop system (LoopKit) |
| **AAPS** | [aaps/](aaps/) | Android closed-loop system |
| **Trio** | [trio/](trio/) | iOS closed-loop (formerly FreeAPS X) |
| **oref0** | [oref0/](oref0/) | OpenAPS reference algorithm |
| **xDrip4iOS** | [xdrip4ios/](xdrip4ios/) | iOS CGM data management app |
| **xDrip+ (Android)** | [xdrip-android/](xdrip-android/) | Android CGM data hub (comprehensive) |

## Cross-Project Analysis

| Document | Purpose |
|----------|---------|
| [cross-project/terminology-matrix.md](cross-project/terminology-matrix.md) | Rosetta stone mapping equivalent concepts across all projects |
| [cross-project/cgm-apps-comparison.md](cross-project/cgm-apps-comparison.md) | Detailed comparison of xDrip+ vs xDrip4iOS |

## Documentation Structure

Each project mapping follows a consistent structure:

```
{project}/
├── README.md           # Overview, architecture, key source files
├── data-models.md      # Entity definitions and Nightscout field mappings
├── nightscout-sync.md  # Upload/download patterns and API interactions
└── [feature].md        # Feature-specific documentation
```

## Source Code References

All mappings reference source code from `externals/` submodules:

| External | Path | Description |
|----------|------|-------------|
| xDrip+ | `externals/xDrip/` | Android xDrip+ source |
| xDrip4iOS | `externals/xdripswift/` | iOS xDrip source |
| AAPS | `externals/AndroidAPS/` | AAPS source |
| Loop | `externals/LoopWorkspace/` | Loop source |
| Trio | `externals/Trio/` | Trio source |
| Nightscout | `externals/cgm-remote-monitor/` | Nightscout source |
| oref0 | `externals/oref0/` | OpenAPS algorithm |

## Citation Format

Source citations follow the pattern:
```
{project}:{path/to/file}#L{start}-L{end}
```

Example:
```
xdrip-android:models/Treatments.java#L76
```

Maps to:
```
externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/models/Treatments.java
```
