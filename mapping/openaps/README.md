# OpenAPS Mapping

**Repository**: openaps/openaps  
**Purpose**: OpenAPS toolkit for DIY closed-loop insulin delivery  
**Language**: Python

## Overview

OpenAPS is the core toolkit that provides device communication and data formatting for the OpenAPS closed-loop system. It works with oref0 (the algorithm) and provides:

- Medtronic pump communication via USB
- Dexcom CGM receiver communication
- Data formatting for Nightscout and oref0

## Relationship to oref0

OpenAPS provides **device drivers and data access**, while oref0 provides the **dosing algorithm**.

```
OpenAPS (device I/O) → oref0 (algorithm) → OpenAPS (pump commands)
                    ↓
              Nightscout (monitoring)
```

## Key Files

| File | Purpose |
|------|---------|
| `openaps/vendors/dexcom.py` | Dexcom receiver interface |
| `openaps/vendors/medtronic.py` | Medtronic pump interface |

## Related Documents

- [nightscout-formats.md](nightscout-formats.md) - Data format conversions
- [device-protocols.md](device-protocols.md) - Device communication
- See also: `mapping/oref0/` for algorithm documentation
