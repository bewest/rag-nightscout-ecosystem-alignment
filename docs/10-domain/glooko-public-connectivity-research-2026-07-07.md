# Glooko Public Connectivity Research (2026-07-07)

## Scope

This note records public evidence used to make `nightscout-connect` Glooko web-login and v3 graph support deterministic enough for a feature-flagged release path. It distinguishes what can be implemented from public behavior versus what still needs live account validation.

## Public Evidence Reviewed

| Source | Evidence |
|--------|----------|
| Glooko developer portal | Public site exists for official API/EHR integrations, but detailed API access is gated behind Glooko relationships. This means community use remains unofficial unless covered by a direct integration agreement. |
| `itconor/glooko-nightscout-eu` | Documents EU JSON API login failure via Rails CSRF 422, and a working browser form login: GET `/users/sign_in?locale=en-GB`, scrape `authenticity_token`, POST `/users/sign_in?id=login_form`, then use the session cookie for `/api/v3/session/users` and v2 pump endpoints. |
| `spamsch/glooko-reader` | Documents no public API, browser login with CSRF/cookies, `get_graph_data()`, `get_statistics()`, `get_device_settings()`, regional routing, full ISO timestamps, and literal `series[]` graph parameters. |
| `lsandini/glooko2nightscout` | Uses browser/Puppeteer login, `/api/v3/session/users`, `/api/v3/graph/data`, `cgmLow`/`cgmNormal`/`cgmHigh`, profile/unit extraction, and regional endpoint handling. |
| `GlycemicGPT/GlycemicGPT` | Contains a clean-room web-session auth implementation and capture tooling. Search snippets explicitly describe web Devise session login, CSRF token, cookie replay, `/api/v3/session/users`, `/api/v3/graph/data`, and v2 cursor endpoints. |
| `nightscout/nocturne` | Implements Glooko regions, v2/v3 sign-in constants, `/api/v3/session/users`, `/api/v3/graph/data`, `cgmHigh`/`cgmNormal`/`cgmLow`, device metadata, web-origin resolution, and timezone timeline services. |
| `nightscout/GlookoServiceKit` | Upload-oriented Loop/Trio plugin, not a Nightscout downloader, but confirms Glooko has multiple product backends. Its Classic backend uses region resolution, `/api/v2/users/sign_in`, `_logbook-web_session`, 2FA support, `x-timezone`, local timestamps, and retry after 401/421. |

## Deterministic Design Points

The following are now supported by enough public evidence to implement behind flags:

1. **Auth mode separation**: API login and web login are different paths. API login can keep working for some accounts; web login is needed for EU/web-only accounts that reject JSON API login with 422.
2. **Web login shape**: The web path is a standard Rails/Devise-style flow: GET sign-in page, extract `authenticity_token`, POST form-encoded credentials, retain `_logbook-web_session`.
3. **Auto fallback**: Trying API login first and falling back to web login on 422 is deterministic and release-safe because it preserves existing behavior unless the known CSRF failure occurs.
4. **Session profile lookup**: `/api/v3/session/users` can provide `glookoCode` when web login does not return the older `userLogin.glookoCode` shape.
5. **CGM graph fallback**: `/api/v3/graph/data` with `series[]=cgmHigh`, `series[]=cgmNormal`, and `series[]=cgmLow` is a documented pattern across multiple public clients and Nocturne.
6. **Regional separation**: API hosts and web origins must be tracked separately. Examples include `api.glooko.com`/`my.glooko.com`, `eu.api.glooko.com`/`eu.my.glooko.com`, and custom regional hosts like `de-fr.api.glooko.com`.
7. **Backend distinction**: GlookoServiceKit shows Classic and XT are different upload backends. That should not be conflated with Nightscout's downloader path. The downloader should stay on the web/API session path unless a separate XT upload feature is explicitly designed.

## Implemented in nightscout-connect dev

`nightscout-connect` `origin/dev` now includes:

- `CONNECT_GLOOKO_AUTH_MODE=api|web|auto`
- `CONNECT_GLOOKO_WEB_ORIGIN`
- `CONNECT_GLOOKO_USE_V3_GRAPH=true`
- CSRF web-form login tests.
- API-to-web auto fallback on 422 tests.
- `/api/v3/session/users` patient-code resolution tests.
- `/api/v3/graph/data` CGM fallback tests for `cgmHigh`, `cgmNormal`, and `cgmLow`.

Implementation commit:

- `c06c037 feat(glooko): add flagged web login and v3 graph fallback`
- `2d733c9 fix(glooko): harden web auth and v3 graph handling`

## Remaining Uncertainties

These should remain explicit release notes and future test targets:

1. **Unofficial interface**: Public sources agree this is not a stable public Glooko API. Web form and internal API behavior may change.
2. **2FA/CAPTCHA**: Current implementation does not handle 2FA, CAPTCHA, or SSO variations.
3. **Timezone correctness**: Fixed offset support remains. Public sources and Nocturne indicate Glooko timestamps can be fake-UTC/local-wall-clock and should eventually use named timezone or a timeline service.
4. **Unit conversion**: v3 graph data may use user-preferred units in `y` and mg/dL x 100 in `value`. Current implementation prefers `value` when present and falls back to `y`, which needs live validation for mmol/L accounts.
5. **Pump enrichments**: v3 graph exposes bolus, pump mode, basal, alarm, site/reservoir, and profile series. Current release path only uses v3 graph as a CGM fallback.
6. **2FA handling**: GlookoServiceKit confirms Classic sign-in can require 2FA. The current `nightscout-connect` web-login path detects 2FA-required responses and fails clearly, but does not implement OTP flows.
7. **Retry semantics**: GlookoServiceKit retries Classic requests after 401/421 by invalidating the cookie and signing in again. `nightscout-connect` should add this as a future connector-status/backoff feature.
8. **Live fixtures**: Fake-server tests cover protocol shape. Real-account captures, sanitized and fixture-backed, are still needed before defaulting to web/v3 behavior.

## Recommendation

Keep the Glooko enrichment in the 0.0.13 dev line only as feature-flagged functionality:

- Default: `CONNECT_GLOOKO_AUTH_MODE=api`, `CONNECT_GLOOKO_USE_V3_GRAPH=false`.
- EU/web-only users: try `CONNECT_GLOOKO_AUTH_MODE=auto` and `CONNECT_GLOOKO_USE_V3_GRAPH=true`.
- If successful in real accounts, promote to documented recommendation for EU Glooko.

Do not make web login or v3 graph the default until sanitized live fixtures cover EU, US, mmol/L, mg/dL, Omnipod 5, and CamAPS accounts.
