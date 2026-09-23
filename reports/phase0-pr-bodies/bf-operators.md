> **Details withheld.** This PR fixes security issues, and part of the related report is still open in a private GitHub security advisory. The fix is merged into `dev`, but no release contains it yet. We removed the detailed description on purpose, and will restore it once a fixed release is out and the advisory is published.

## What changes for you

**Your stored data is not touched.** What changes is which requests the API answers at all.

- API v1 query filters now accept a fixed, documented set of MongoDB operators. The API refuses anything else with HTTP 400 and an error that names the operator. Ordinary filters work as before: date ranges, event types, glucose thresholds, `$exists` and text matching. A survey of 14 Nightscout client projects found 157 filter uses, and none of them uses a refused operator.
- The undocumented `pipeline` parameter on `/api/v1/count/…` is now refused.
- A refused filter now returns `400` instead of a `500` that looks like the server is down.

**If a report, dashboard or script you use starts returning a 400 after this change, the request used a filter condition the API does not support. It does not mean your data is gone.** The error names the condition and lists the supported ones.

Nightscout is not a medical device, and this is not medical advice. If a tool you rely on breaks, raise it with that tool's author. If a gap in your data worries you, talk it through with your care team.

## The accept set

```
on a field   $eq $ne $gt $gte $lt $lte $in $nin $exists $type $regex (with $options)
at the top   $and $or, and their branches
```

This list is a superset of every operator in the client survey. `$expr` on `/api/v1/profiles/` used to work and is now refused. `$type` stays allowed so that #8737 keeps working.

## Verifying it

```
TEST=mongo-query-javascript npm run test-single
TEST=api-v1-operator-allowlist npm run test-single
TEST=api-v1-count-pipeline npm run test-single
npm test                                             # 2223 passing, 3 pending, 0 failing
```

Ablating each guard makes its tests fail.

## Semver: minor

This removes reachable but undocumented behaviour. No route is removed, no documented contract breaks, and no operator action or configuration change is needed. The "What changes for you" section above is the source for the release notes.

## Follow-ups

The private advisory tracks the remaining related items.

