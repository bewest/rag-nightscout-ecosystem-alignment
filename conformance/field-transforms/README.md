# Field Transform Test Suite

Tests cross-system field mappings and transformations in the Nightscout ecosystem.

## Overview

Unlike unit conversion tests (`test_conversions.py`) which validate mg/dL ↔ mmol/L transformations, the transform test suite validates:

- **Field renaming**: `glucoseValue` → `sgv`
- **Nested extraction**: `devicestatus.loop.iob.iob` → `iob`
- **Type coercion**: `"120"` → `120`
- **Default values**: Add `eventType` if missing
- **Computed fields**: `duration / 60` → `durationMinutes`

## Usage

```bash
# Run all tests
python tools/test_transforms.py

# Verbose output (show passing tests)
python tools/test_transforms.py -v

# Filter by source system
python tools/test_transforms.py --source loop
python tools/test_transforms.py --source aaps

# Filter by target system
python tools/test_transforms.py --target nightscout

# Filter by test ID pattern
python tools/test_transforms.py --id "bolus-*"

# List tests without running
python tools/test_transforms.py --list

# JSON output for CI
python tools/test_transforms.py --json
```

## Test File Structure

```yaml
tests:
  - id: unique-test-id
    description: Human-readable description
    source_system: Loop
    target_system: Nightscout
    input:
      fieldA: value1
      nested:
        fieldB: value2
    transforms:
      - type: rename
        from: fieldA
        to: fieldC
      - type: extract
        from: nested.fieldB
        to: fieldD
    expected:
      fieldC: value1
      fieldD: value2
```

## Transform Types

### `rename`
Change a field name:
```yaml
- type: rename
  from: glucoseValue
  to: sgv
```

### `extract`
Pull nested field to top level:
```yaml
- type: extract
  from: loop.iob.iob
  to: iob
```

Supports array indexing:
```yaml
- type: extract
  from: predicted.values[0]
  to: currentPrediction
```

### `coerce`
Convert field type:
```yaml
- type: coerce
  field: sgv
  to_type: integer  # or: string, number, boolean
```

### `default`
Set value if field missing:
```yaml
- type: default
  field: eventType
  value: "sgv"
```

### `compute`
Calculate from other fields:
```yaml
- type: compute
  to: durationMinutes
  expression: "${duration} / 60000"
```

## Test Files

| File | Coverage |
|------|----------|
| `transforms.yaml` | Core transform patterns, DeviceStatus extraction |
| `entries.yaml` | SGV, MBG, direction arrows, noise levels |
| `treatments.yaml` | Bolus, carbs, temp basal, profile switch, overrides |

## Adding New Tests

1. Identify the source and target system
2. Document the field mapping needed
3. Create test with input, transforms, expected output
4. Run `python tools/test_transforms.py --id your-test-id`

### Example: New CGM Source

```yaml
- id: libre3-to-nightscout
  description: LibreLink Up glucose to Nightscout
  source_system: LibreLinkUp
  target_system: Nightscout
  input:
    ValueInMgPerDl: 120
    TrendArrow: 3
    Timestamp: "2024-01-29T14:54:56.000Z"
  transforms:
    - type: rename
      from: ValueInMgPerDl
      to: sgv
    - type: rename
      from: Timestamp
      to: dateString
    - type: default
      field: type
      value: "sgv"
  expected:
    sgv: 120
    dateString: "2024-01-29T14:54:56.000Z"
    type: "sgv"
```

## Related Files

- `tools/test_conversions.py` - Unit conversion tests
- `conformance/unit-conversions/` - Conversion test vectors
- `mapping/*/` - Per-project field mapping documentation

## Cross-References

- [Interoperability Spec](../../specs/interoperability-spec-v1.md)
- [Terminology Matrix](../../mapping/cross-project/terminology-matrix.md)
- [Treatment eventTypes](../../mapping/nightscout/v3-treatments-schema.md)
