## 1. Web Push surface (vuln-0010, vuln-0005, vuln-0011)

- [x] 1.1 Add the destination validator (scheme, userinfo, resolved-address `is_global`), the request timeout constant, the redirect-free `requests.Session`, and the store capacity constant to `app/services/push_subscription_service.py`
- [x] 1.2 Apply the timeout and redirect-free session to the outbound `webpush()` call
- [x] 1.3 Reject new subscriptions once the store is at capacity in `PushSubscriptionService.add`
- [x] 1.4 Surface the capacity rejection as a client error (not a 500) in `app/routers/push.py`
- [x] 1.5 Wrap the delivery call in `run_in_threadpool` at every async caller: notification create/update routes, the notification activity poll, and the presence poll
- [x] 1.6 Declare `requests` as a direct dependency in `pyproject.toml`

## 2. Redirect validation (vuln-0004)

- [x] 2.1 Normalize and validate `next` against its resolved origin in `AuthRedirectQuery.sanitize_url`
- [x] 2.2 While assessing the finding, fully percent-encode the application-generated `/auth?next=...` redirect in `app/main.py` and `tests/conftest.py` (the bundle recommended this but emitted no patch)

## 3. Anonymous notification reads (vuln-0006)

- [x] 3.1 Add the keyword-only `only_active` flag to `NotificationService.get` and apply it to the explicit-ID branch
- [x] 3.2 Pass `only_active=api_key is None` from the two unauthenticated notification routes

## 4. Bounded input (vuln-0007)

- [x] 4.1 Bound `for_date` before parsing in `OccupancyService.get_occupancy`, falling back to the current date

## 5. Session revocation (vuln-0009)

- [x] 5.1 Add a rotation helper that removes the superseded session record
- [x] 5.2 Use the helper at the API-key-header rotation site and after successful sign-in

## 6. Atomic API key store replacement (vuln-0008)

- [x] 6.1 Add a single-write `replace` method to `PersistentList`
- [x] 6.2 Use it in `EphemeralAPIKeyStore.save`

## 7. Information disclosure (vuln-0012)

- [x] 7.1 Store a generic, client-safe presence failure message while retaining the exception in the server log

## 8. Dependency remediation (vuln-0001, vuln-0002, vuln-0003)

- [x] 8.1 Move `httpx2` out of the production dependency set into the `dev` group at `>=2.12.0` (removal broke `starlette`'s `TestClient` under `filterwarnings=error`)
- [x] 8.2 Regenerate `uv.lock` and `app/licenses.json`
- [x] 8.3 Run the repository dependency audit (`uv run security-check`) — no advisories

## 9. Regression tests

- [x] 9.1 Push destination rejection (internal forms, userinfo, non-resolving) and acceptance of a public host
- [x] 9.2 Push store cap: new rejected at capacity, existing replaceable, freed slot reusable
- [x] 9.3 Session invalidation after rotation and sign-out
- [x] 9.4 Redirect bypass variants plus a legitimate path with a query string
- [x] 9.5 Anonymous notification read matrix (inactive hidden, active visible, authenticated sees inactive)
- [x] 9.6 Bounded `for_date`
- [x] 9.7 Generic presence error field (no address/port)

## 10. Validation

- [x] 10.1 `uv run lint` (also fixes a pre-existing markdownlint failure by scoping ignores to OpenSpec/vendor docs)
- [x] 10.2 `uv run test` (578 Python tests + 13 JS tests green)
- [x] 10.3 `uv run security-check` (no advisories)
- [ ] 10.4 Open the pull request (archive this change after merge)
