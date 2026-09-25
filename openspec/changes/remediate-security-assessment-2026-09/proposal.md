## Why

An authorized security assessment of the Fribbe Status Checker (September 2026) filed
12 issues: 1 high, 6 medium, 2 low and 3 informational. The high and most of the medium
findings concentrate
on the unauthenticated Web Push subscription surface, which today accepts arbitrary
endpoints, delivers to them without a timeout or off-loop dispatch, grows without bound,
and permits server-side requests to internal hosts. Fixing these closes an
attacker-triggerable denial of service, an SSRF primitive, unbounded resource growth, and
several access-control, session, redirect and information-disclosure defects.

## What Changes

- **BREAKING (operator-visible):** push subscriptions whose endpoint host resolves to a
  non-public address (loopback, RFC1918, link-local, CGNAT, multicast) or that carry
  userinfo are rejected at registration. A deployment that intentionally points
  subscriptions at a private push relay must be updated.
- **BREAKING (operator-visible):** signing in no longer leaves the previous session cookie
  valid, and signing out now terminates sessions that earlier rotations superseded.
- Push delivery is bounded by a request timeout and is dispatched off the ASGI event loop
  from every asynchronous entry point that reaches it.
- The push subscription store is capped, and the registration handler surfaces capacity
  rejection as a client error instead of a server error.
- Push requests are no longer redirected, so a validated public endpoint cannot bounce the
  server to an internal address.
- The `next` redirect parameter of `/auth` is normalized the way a browser normalizes a
  URL and validated against its resolved origin; the value the application itself embeds in
  a redirect is fully percent-encoded.
- Unauthenticated notification reads via explicit `nid-*` identifiers are restricted to
  active notifications; authenticated callers are unchanged.
- The free-form `for_date` parameter is length-bounded before it reaches the date parser.
- The unauthenticated `/api/status` presence error field no longer carries raw third-party
  exception text (and therefore no internal address); detail is retained in server logs.
- The API key store is replaced with a single atomic persisted write.
- The application-generated `/auth?next=...` redirect fully percent-encodes the value, so a
  crafted `next` query cannot inject additional parameters.
- The advisory-affected `httpx2` package is removed from the production dependency set; it
  remains a **test-only** dependency at a patched version because the framework's
  `TestClient` requires it. `requests` is declared as a direct dependency of the push
  service.
- Markdownlint ignores are scoped for OpenSpec artifacts and the CLI-generated
  agent/prompt/skill docs (their schema-defined `##` first heading and formatting do not
  satisfy MD041/MD036), unblocking the pre-existing lint failure on the default branch.

## Capabilities

### New Capabilities

- `web-push-security`: abuse controls on the public push subscription surface — destination
  validation, bounded and off-loop delivery, and a bounded subscription store.
- `session-security`: signing in and signing out must invalidate superseded session
  identifiers.
- `public-api-hardening`: safe redirect handling, restriction of anonymous notification
  reads, bounded input, and non-disclosing error fields on unauthenticated endpoints.
- `api-key-store-integrity`: API key store replacement must be atomic with respect to
  concurrent readers.
- `dependency-supply-chain`: production dependencies must not include unused packages
  affected by published advisories.

### Modified Capabilities

None — no main specs exist yet, so every capability is introduced here.

## Impact

- **Code**: `app/services/push_subscription_service.py`, `app/routers/push.py`,
  `app/api/requests.py`, `app/api/hybrid_auth.py`, `app/routers/auth.py`, `app/main.py`,
  `app/routers/notifications.py`, `app/routers/notification_ui.py`,
  `app/services/notification_service.py`, `app/services/presence_level_service.py`,
  `app/services/occupancy/occupancy_service.py`, `app/services/persistent_collections.py`,
  `app/api/ephemeral_api_key_store.py`, `tests/conftest.py`.
- **Dependencies**: add `requests` as a direct dependency (imported by the push service for
  the redirect-free session); move `httpx2` out of the runtime set into the `dev` group at
  `>=2.12.0` (the production image builds with `uv sync --no-dev`). `uv.lock` and
  `app/licenses.json` are regenerated, and `uv run security-check` reports no advisories.
- **Configuration**: `.markdownlint-cli2.yaml` ignores `openspec/**`, `strix-reports/**`,
  `.github/agents/**`, `.github/prompts/**` and `.github/skills/**`.
- **APIs**: `POST /api/push/subscribe` accepts fewer inputs and can return an error when the
  store is full; `GET /auth` and `POST /auth` normalize/validate `next`; anonymous
  `GET /api/notifications` and `GET /notifications/content` may return fewer items;
  `GET /api/status` bounds `for_date` and returns a generic `presence.last_error`.
- **Tests**: new regression coverage for destination rejection, the store cap, session
  invalidation, redirect bypass variants, the anonymous notification read matrix, the
  bounded date parameter and the generic error field.
- **Operators**: release notes must call out the private-endpoint rejection and the session
  invalidation behaviour changes.
