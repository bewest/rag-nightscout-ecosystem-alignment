# Nightscout Telemetry Scheduling and Dedupe Model

Date: 2026-07-16

## Recommendation

Use **weekly jittered send attempts** with a **monthly rotating installation ID** and **backend monthly deduplication**.

This is better than exactly-once-per-month sending because it tolerates downtime, network failures, and backend outages while still producing a monthly active installation count without overcounting.

## Model

```text
cgm-remote-monitor
  persistent telemetry secret
  monthly ID = HMAC(secret, YYYY-MM)
  local counters since last successful send
  next_due_at with jitter
        |
        v
weekly-ish send attempts
  success: next_due_at = now + 7d + jitter(0..24h)
  failure: next_due_at = now + jitter(6h..24h)
        |
        v
crm-telemetry backend
  raw accepted payload retention: 60d
  aggregate monthly active by (month, installation_id)
  do not expose raw installation IDs
```

## Why weekly attempts

Monthly active installation estimates should not depend on one fragile monthly send. Weekly attempts provide:

- Recovery when an instance is offline during the first due window.
- Recovery when the telemetry endpoint is down.
- Better release regression visibility without high event volume.
- Natural confirmation that an instance is still active during a month.

The backend still reports monthly active installations by deduping on `(month, installation_id)`.

## Thundering herd avoidance

Avoid fixed calendar timestamps. Do not send at midnight UTC on the first day of the month.

Rules:

1. First due time: `now + random(5 minutes..7 days)`.
2. After success: `now + 7 days + random(0..24 hours)`.
3. After failure: `now + random(6..24 hours)`.
4. Do not attempt while `NIGHTSCOUT_TELEMETRY=off`.
5. Do not attempt before the server is booted and stable.
6. Do not block startup or request handling.

## Counter retention

Do not discard feature-use counters every day if reports are sent weekly. The client-side counter window should cover activity since the last successful telemetry send, with UTC day only used as the `reporting_period` label and for health bucketing.

The backend can still aggregate by month:

- If an installation reports weekly, feature-active installation counts are deduped by `(month, installation_id, counter_name)`.
- Counter sums are treated as approximate reported activity over the client reporting window.
- A successful send can reset local counters after the payload is accepted.
- Failed sends should keep counters so activity is not lost before retry.

Daily counter reset is only appropriate if the sender also sends daily.

## Persistent state

cgm-remote-monitor should persist telemetry-specific state separate from API and JWT secrets:

```json
{
  "schema": 1,
  "secret": "random-base64url-32-byte-secret",
  "created_at": "2026-07-16T20:00:00.000Z",
  "counters_since": "2026-07-16T20:00:00.000Z",
  "last_attempt_at": "2026-07-16T20:30:00.000Z",
  "last_success_at": "2026-07-16T20:30:01.000Z",
  "last_status": 204,
  "next_due_at": "2026-07-23T23:12:01.000Z"
}
```

In the current branch this state starts in a telemetry-specific cache file. A later production decision can move it to MongoDB if maintainers prefer state that survives rebuilds and ephemeral filesystems.

## Backend aggregation

The backend should derive:

- `report_month = reporting_period.slice(0, 7)`
- `installation_key = (report_month, installation_id)`

Monthly active installations:

```sql
COUNT(DISTINCT installation_id)
WHERE report_month = ?
```

Feature-enabled installations:

```sql
COUNT(DISTINCT installation_id)
GROUP BY report_month, feature_name
```

Feature-active installations:

```sql
COUNT(DISTINCT installation_id)
WHERE counter_value > 0
GROUP BY report_month, counter_name
```

Counter sums can be reported separately, but installation counts should dedupe by month.

## Open decision: cache file versus MongoDB

MongoDB advantages:

- Survives rebuilds and many ephemeral filesystems.
- Naturally follows the Nightscout installation database.
- Can persist `next_due_at`, last attempt, and last success.

Cache-file advantages:

- Simple and avoids adding telemetry documents to Mongo.
- Works for stable filesystem deployments.
- Already mirrors the existing `randomString` generated-key pattern, but with a separate telemetry secret.

Recommendation: keep cache-file persistence for the disabled prototype branch, but document MongoDB as the likely production target for installations where filesystem state is not durable.

## Acceptance criteria for scheduling helper

- Same monthly installation ID for dates in the same month.
- Different monthly installation ID across months.
- Initial due time is not immediate and is spread over up to 7 days.
- Missing schedule state initializes `next_due_at`; it does not send immediately.
- Success due time is about weekly with 0 to 24 hours jitter.
- Failure retry is 6 to 24 hours.
- Disabled telemetry is never due.
- Scheduling helper is pure and testable before any automatic timer is added.
