## Purpose

Defines how the application connects to the router's HiLink API when the router is reached over an
intermittent or relayed network link: every attempt is bounded in time, one poller's failure does
not affect another, and reported errors never disclose internal addressing.

## ADDED Requirements

### Requirement: Every router connection is time-bounded

Each attempt to query the router MUST be limited by a configured connection and read timeout. No
polling iteration may block indefinitely on a stalled, half-open or relayed connection, and the
limit SHALL apply equally to the presence poller and the internal device-count poller.

#### Scenario: A stalled connection does not block the poller

- **WHEN** a router query receives no response
- **THEN** the attempt fails after the configured timeout, the polling iteration completes, and the next iteration is scheduled normally

#### Scenario: The limit is operator-configurable

- **WHEN** no timeout value is configured
- **THEN** a documented default applies, and a configured value replaces it for every router query

### Requirement: A poller failure does not stop subsequent polls

A failed router query MUST be isolated to the polling iteration that produced it. The failure is
logged with its detail, the poller records that the attempt failed, and the polling loop continues
so that recovery needs no restart.

#### Scenario: Recovery after a transient failure

- **WHEN** a poll attempt fails and the following attempt succeeds
- **THEN** the recorded error is cleared and the poller publishes fresh data from the successful attempt

#### Scenario: Repeated failures keep the service running

- **WHEN** every poll attempt fails for an extended period
- **THEN** each failure is logged, the pollers remain active, and the service continues to serve requests

### Requirement: Router errors exposed over the API do not disclose internal addressing

Any failure detail derived from a third-party connection error MUST NOT be returned to API callers
when that text may embed an internal host name, address or port. The API SHALL return a stable,
client-safe message while full detail is retained in the server log.

#### Scenario: Presence failure field is sanitized

- **WHEN** the presence poll fails and a client reads the public status response
- **THEN** the presence error field contains a generic message with no address, host name or port

#### Scenario: Internal failure field is sanitized

- **WHEN** the internal poll fails and an authenticated reader fetches the internal details response
- **THEN** the internal error field contains a generic message with no address, host name or port

#### Scenario: A successful poll reports no error

- **WHEN** the most recent poll succeeded
- **THEN** the corresponding error field is null
