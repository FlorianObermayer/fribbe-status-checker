## Context

Two pollers in `app/services/` query the same router API through `huawei_lte_api.Connection`:
`PresenceLevelService` (derives `PresenceLevel`, drives arrival pushes) and `InternalService`
(tracks device counts, wardens and first/last arrival timestamps). See `proposal.md — Why` for the
motivation.

Constraints that shape the approach:

- `PresenceLevel` is a `StrEnum` used in the public `/api/status` response, in `MessageService`, and
  in the templates. Adding a value would affect every exhaustive consumer.
- `InternalService` already behaves the way the presence poller should: on failure it records the
  error and keeps the last known counts. Only the presence poller overwrites its state with `EMPTY`.
- `PresenceLevelService` already sanitizes its error to `RuntimeError("presence detection failed")`
  before it reaches `/api/status`; `InternalService` stores the raw exception and `/api/internal/details`
  renders it with `str()`, exposing the router host and port to any reader.
- Polling runs in a dedicated thread per service with its own event loop (`PollingService`), so a
  blocking connection call stalls that poller only — but does stall it indefinitely.
- Timestamps are wall-clock (`datetime.now(tz=ZoneInfo(cfg.TZ))`), matching the existing
  `last_updated` contract.
- All configuration is declared in `app/config.py` only, with `.env.template` as the canonical
  variable list.

## Goals / Non-Goals

**Goals:**

- Make a remote-link outage degrade a single polling iteration, never the poller or the reported
  state.
- Give consumers an unambiguous way to tell "empty" from "unknown".
- Keep the change additive for API consumers.

**Non-Goals:**

- Retry or backoff-with-jitter inside an iteration. The poll interval already acts as the retry
  cadence; adding in-iteration retries would multiply connection attempts against a flaky relay.
- A circuit breaker, health endpoint, or alerting integration.
- Changing the internal poller's derived statistics (first/last arrival) beyond keeping its current
  retain-last-value behaviour.
- Exposing staleness for occupancy or weather; both have their own timestamp/error fields.

## Decisions

### D1 — One configurable connection timeout, applied to both services

Add `ROUTER_CONNECTION_TIMEOUT_SECONDS` (default `10`) to `app/config.py` and pass it as
`timeout=` to every `huawei_lte_api.Connection`. The literal `10` in `PresenceLevelService` moves
to the config default; `InternalService` gains the argument it lacked.

*Alternatives considered:* two values (connect vs. read) — `requests` supports it but the observed
failure mode (relayed path stalls after connect) does not justify the extra knob; a socket-level
default — invisible to operators and inconsistent between services.

### D2 — Staleness is derived at read time, not stored

Compute staleness from the last **successful** observation rather than flagging it on failure:

```text
stale = last_updated is None or (now - last_updated) > stale_after
```

Add `PRESENCE_STALE_AFTER_SECONDS`, defaulting to three times
`PRESENCE_POLLING_INTERVAL_SECONDS` computed in `cfg`, so operators who lengthen the interval do not
have to remember a second variable. Expose `is_stale()` (or an equivalent accessor) on the service.

*Rationale:* a failure path flag only covers raises. A connection that hangs (bounded now by D1, but
still up to the timeout) or a thread that dies leaves `last_updated` frozen — derived staleness
catches that too, with no extra state to keep in sync.

*Alternatives considered:* a stored `_stale` boolean set on exception — simpler to read but wrong
for silent stalls and needs resetting on success; per-read TTL caching of the level — mixes caching
concerns into the poller.

### D3 — Keep `PresenceLevel` unchanged; add a `stale` flag

`PresenceResponse` gains a required `stale: bool`; `PresenceLevel` keeps `empty` / `few` / `many`.
`empty` continues to mean "a successful observation found nobody", and a stale level carries
whatever was last observed.

*Rationale:* adding `UNKNOWN` to the enum is a breaking change for `MessageService`,
`PresenceThresholds`, the templates and any external consumer of `/api/status`. The flag is additive
and carries strictly more information: `(empty, stale=true)` already encodes "unknown, last seen
empty" without a new enum value.

*Alternatives considered:* `level: empty|few|many|unknown` — semantically clean but breaking; a
separate `data_state` enum — redundant with the boolean for a two-state distinction.

### D4 — The status message stays a pure function of the level; the UI renders the staleness

`MessageService.get_status_message` keeps its current signature. Templates and the status page
render a staleness notice when `stale` is set, next to the unchanged message.

*Rationale:* German message text remains a pure function of `(level, occupancy, weather)` and stays
covered by its existing unit tests; presentation of freshness belongs in the template layer.

### D5 — Arrival pushes require a fresh consecutive pair

Track the timestamp of the last successful observation alongside the level. When a successful
observation produces a non-empty level, fire an arrival notification only if all of the following
hold: a previous successful observation exists, that observation is within `stale_after`, its level
was `empty`, and no arrival notification was sent for the current virtual day. The existing "skip the
first poll after start" guard stays.

*Rationale:* after an outage the first successful observation is not evidence that somebody just
arrived — it is evidence that we can see again. Requiring the previous observation to be fresh is a
single comparison and needs no new persisted state (per-day suppression already exists via
`_last_push_virtual_date`).

*Alternatives considered:* suppress pushes for one interval after any failure — coarse and racy;
require two consecutive successful non-empty observations — delays every legitimate arrival by one
poll interval.

### D6 — `InternalService` mirrors the presence poller's error contract

Store a generic `RuntimeError("internal refresh failed")` and keep the full exception in the log
entry, exactly as `PresenceLevelService` does. Its retain-last-value behaviour already matches the
new presence semantics, so no other change is needed there. Staleness is **not** added to the
internal details response in this change — `last_updated` is already present there.

## Risks / Trade-offs

- **Consumers that relied on "error implies empty"** now see the last known level → the `stale` flag
  is the replacement signal; the UI shows a notice, and the change is documented in `README.md`.
  This is the intended behavioural improvement, not an accident.
- **Wall-clock staleness is vulnerable to clock jumps** (NTP step, VM restore) → a forward jump marks
  data stale until the next successful poll; a backwards jump delays staleness detection. Both
  resolve within one poll interval, and the alternative (monotonic timestamps) cannot be compared
  against the persisted `last_updated` already exposed to clients.
- **Threshold too tight for a relayed link** → flapping between fresh and stale at 3× interval.
  Default is deliberately generous; operators can raise `PRESENCE_STALE_AFTER_SECONDS`, and the
  signal is advisory rather than destructive.
- **Timeout too low over DERP** → individual polls fail where they previously crawled. Default
  matches the value already proven in production on the presence poller and is configurable.
- **Two services now share a timeout but still poll independently** → two connections per interval,
  as today; unchanged.
- **Arrival push under-reporting** → a genuine arrival that coincides with an outage produces no
  notification. Accepted: a false "someone is here" after a tailnet blip is worse than a missed
  arrival push, and the status page still shows the level.

## Migration Plan

1. Deploy with no new variables set — defaults keep today's interval and timeout behaviour.
2. Verify `/api/status` returns `stale` and that `last_updated` advances every poll interval.
3. Confirm no arrival push fires from the first observation after a container restart.
4. Rollback is a revert: no schema, data or volume migration is involved; the added response field is
   additive and safe for an older client to receive.

## Open Questions

None blocking. Whether the staleness notice should also suppress the arrival push body's occupancy
and weather context can be decided during implementation without affecting the specs.
