## Why

The app is moving off the router's LAN: the LTE router now sits behind carrier-grade NAT, so
presence data is fetched over Tailscale through a forwarder on a site anchor instead of over a
direct Ethernet link. That makes a previously exceptional condition — the router is briefly
unreachable — a routine one, and the current polling code handles it badly in two ways: one poller
can block indefinitely on a stalled connection, and any connection failure is reported to users as
an empty beach.

## What Changes

- Give every router connection a bounded timeout, including the internal device-count poller
  (`InternalService`), which currently passes none and can therefore pin its polling thread
  indefinitely on a half-open or relayed connection. The timeout becomes configurable through
  `app/config.py` rather than being duplicated as a literal in two services.
- Stop treating transport failures as presence. When a poll fails, the last successfully observed
  presence level is retained and marked stale instead of being overwritten with `empty`. A genuine
  successful poll that returns no devices still reports `empty`.
- Expose staleness on the public status response so clients can distinguish "no one is here" from
  "we do not currently know". Data freshness is derived from the last successful poll and a
  configurable maximum age, so a wedged poller (which never raises) also surfaces as stale rather
  than silently serving days-old data.
- Do not fire the first-active push notification from stale data, and do not use a value recovered
  from staleness as the "previous level" of an empty→active transition.
- Sanitize the internal poller's error field the way the presence error field already is, since
  `/api/internal/details` is readable by any authenticated reader and the raw exception embeds the
  router's internal host and port.

Not **BREAKING**: `level` keeps its existing values and existing consumers keep working; the new
fields are additive and `empty` keeps meaning "a poll succeeded and found nobody".

## Capabilities

### New Capabilities

- `router-polling`: how the app connects to the router's HiLink API — bounded connection duration,
  failure isolation per poller, and error reporting that does not leak internal addressing.
- `presence-detection`: how a poll result becomes the published presence level, including the
  distinction between a genuinely empty result and unknown/stale data, and when arrival pushes may
  fire.

### Modified Capabilities

None — `openspec/specs/` contains no established capabilities yet.

## Impact

- `app/services/presence_level_service.py` — retain the last level on failure, track staleness, gate
  the arrival push on freshness.
- `app/services/internal/internal_service.py` — add the missing connection timeout, sanitize
  `last_error`.
- `app/config.py`, `.env.template`, `examples/docker-compose.yml` — new timeout / staleness settings.
- `app/api/responses.py`, `app/routers/status.py` — additive stale/freshness fields on the presence
  status response.
- `tests/` — failure-path, staleness and push-gating tests; existing "error implies empty"
  expectations change.
- Operator behaviour: with no poll ever succeeding after start, the status page shows an unknown
  state instead of `empty`. This is the intended change, but it is externally visible.
