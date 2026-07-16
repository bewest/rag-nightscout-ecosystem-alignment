# Nightscout Telemetry Deployment Lifecycle Examples

Date: 2026-07-16

## Purpose

These examples translate the telemetry lifecycle policy into deployable storage rules and operational checks. They are examples, not a final provider decision.

## Required lifecycle behavior

| Prefix | Retention | Public |
|--------|-----------|--------|
| `raw/accepted/nightscout/` | 60 days | No |
| `raw/rejected/nightscout/` | disabled by default; shortest practical retention if enabled | No |
| `exports/nightscout/monthly/` | long-lived | Yes, after review |
| `reports/nightscout/` | long-lived | Yes, after review |

## Provider-neutral object storage policy

```yaml
bucket: nightscout-telemetry
rules:
  - id: expire-raw-accepted-nightscout
    prefix: raw/accepted/nightscout/
    action: expire
    days: 60
  - id: expire-raw-rejected-nightscout-if-enabled
    prefix: raw/rejected/nightscout/
    action: expire
    days: 7
  - id: keep-exports-and-reports
    prefixes:
      - exports/nightscout/
      - reports/nightscout/
    action: retain
```

## AWS S3-style lifecycle JSON

```json
{
  "Rules": [
    {
      "ID": "expire-raw-accepted-nightscout",
      "Status": "Enabled",
      "Filter": { "Prefix": "raw/accepted/nightscout/" },
      "Expiration": { "Days": 60 }
    },
    {
      "ID": "expire-raw-rejected-nightscout-if-enabled",
      "Status": "Enabled",
      "Filter": { "Prefix": "raw/rejected/nightscout/" },
      "Expiration": { "Days": 7 }
    }
  ]
}
```

## Terraform AWS S3 example

```hcl
resource "aws_s3_bucket_lifecycle_configuration" "nightscout_telemetry" {
  bucket = aws_s3_bucket.nightscout_telemetry.id

  rule {
    id     = "expire-raw-accepted-nightscout"
    status = "Enabled"

    filter {
      prefix = "raw/accepted/nightscout/"
    }

    expiration {
      days = 60
    }
  }

  rule {
    id     = "expire-raw-rejected-nightscout-if-enabled"
    status = "Enabled"

    filter {
      prefix = "raw/rejected/nightscout/"
    }

    expiration {
      days = 7
    }
  }
}
```

## Scaleway/S3-compatible example

Scaleway Object Storage is S3-compatible. The lifecycle rule should be equivalent to:

```text
Bucket: nightscout-telemetry
Rule: expire raw accepted Nightscout payloads
Prefix: raw/accepted/nightscout/
Expiration: 60 days
```

For Terraform, use the provider/resource available in the selected Scaleway stack. The important invariant is the prefix and expiration behavior, not the exact provider syntax.

## Operational checks

Before default-on activation:

1. Verify lifecycle rules are active on `raw/accepted/nightscout/`.
2. Upload a test object to a non-production bucket and confirm rule attachment.
3. Confirm exports and reports prefixes are not covered by raw expiration rules.
4. Confirm application logs do not include IP, user-agent, raw URL, query string, authorization header, or request body.
5. Confirm public dashboard output does not contain `monthly_` installation IDs.
6. Confirm incident owner and deletion procedure are documented.

## Local prototype gap

The local `crm-telemetry` filesystem backend cannot enforce time-based lifecycle deletion by itself. For local development this is acceptable. Production deployment must enforce raw-payload expiration at the storage layer or via a scheduled cleanup job.

