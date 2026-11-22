## 1. Configuration

- [x] 1.1 Add `ROUTER_CONNECTION_TIMEOUT_SECONDS` (default `10`) to `app/config.py` with the same `os.environ` pattern as the neighbouring presence variables, and verify `uv run python -c "from app.config import cfg; print(cfg.ROUTER_CONNECTION_TIMEOUT_SECONDS)"` prints `10`
- [x] 1.2 Add `PRESENCE_STALE_AFTER_SECONDS`, defaulting to three times `PRESENCE_POLLING_INTERVAL_SECONDS` when unset (resolved in `cfg`, not at the call site), and verify with an env override plus one without it
- [x] 1.3 Document both variables in `.env.template` and pass them through in `examples/docker-compose.yml`, and verify `npx markdownlint-cli2` and `uv run lint` pass

## 2. Bounded router connections (router-polling)

- [x] 2.1 Pass `timeout=cfg.ROUTER_CONNECTION_TIMEOUT_SECONDS` in `InternalService._run_internal_query` and verify a test asserting the `Connection` call receives the configured timeout passes
- [x] 2.2 Replace the literal `timeout=10` in `PresenceLevelService._run_presence_detection` with the same config value and verify the existing presence tests still pass
- [x] 2.3 Sanitize `InternalService`'s stored error to a generic `RuntimeError("internal refresh failed")` while keeping the exception in the log, and verify a test asserting `/api/internal/details` contains neither the router address nor the port passes

## 3. Presence semantics (presence-detection)

- [x] 3.1 Remove the `PresenceLevel.EMPTY` assignment from the failure path in `PresenceLevelService._run_presence_detection` so the last successful level is retained, and verify a test that seeds a non-empty level, forces a connection failure, and asserts the level is unchanged passes
- [x] 3.2 Add a derived freshness accessor to `PresenceLevelService` based on `last_updated` plus `cfg.PRESENCE_STALE_AFTER_SECONDS`, and verify tests cover: never observed → stale, within window → fresh, older than window → stale without any error, later success → fresh again
- [x] 3.3 Gate `_try_send_first_active_push` on the previous successful observation being fresh, and verify tests cover: arrival after a stale gap sends nothing, a fresh empty→non-empty transition still sends exactly once per virtual day, and the cold-start guard still suppresses the first observation
- [x] 3.4 Add `stale: bool` to `PresenceResponse` and populate it in `app/routers/status.py`, and verify an API test asserts the field is present and flips with the fixture's last-updated timestamp

## 4. Presentation

- [x] 4.1 Render a staleness notice on the status page and in any status fragment when `stale` is set, leaving `MessageService` text unchanged, and verify a template/route test asserts the notice appears only for a stale level
- [x] 4.2 Update `README.md` to describe `empty` versus unknown/stale and the new variables, and verify `npx markdownlint-cli2` passes

## 5. Regression coverage

- [x] 5.1 Update `tests/presence_level_service_tests.py::test_failed_poll_stores_generic_error_without_address` to assert retention semantics (level unchanged, stale true) instead of `EMPTY`, and verify the full file passes
- [x] 5.2 Add internal-service tests for the timeout argument and the sanitized error, and verify `tests/internal_service_tests.py` passes
- [x] 5.3 Confirm no other test depends on "failure implies empty" (`grep -rn "get_level() == PresenceLevel.EMPTY" tests`), and verify the suite passes unchanged where the expectation is still correct

## 6. Validation

- [x] 6.1 Run `uv run lint --fix` and verify `ruff format`/`ruff check` and the frontend linters report no findings
- [x] 6.2 Run `uv run test` and verify the Python and JS suites pass with coverage above the configured thresholds
- [ ] 6.3 Run `uv run security-check` and verify no advisories are reported — blocked by 30 pre-existing `aiohttp` advisories (fixed in 3.14.4, unrelated to this change); see follow-up below
- [ ] 6.4 After deployment, verify `/api/status` reports `stale: false` with an advancing `last_updated`, and that stopping the forwarder flips `stale` to true without changing the level to `empty` during the first staleness window
