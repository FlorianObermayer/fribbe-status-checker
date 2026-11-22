## Purpose

Defines what the published presence level means: it reflects only successful observation of the
router's client list, it distinguishes "nobody is here" from "we currently do not know", and it
gates arrival notifications on genuinely fresh observations.

## ADDED Requirements

### Requirement: The published presence level originates from a successful observation

The presence level reported by the service MUST only be changed as the result of a successful
router query. `empty` SHALL mean that a query succeeded and reported no eligible client devices; it
MUST NOT be used to represent a failed or missing observation.

#### Scenario: Successful query with no eligible devices reports empty

- **WHEN** a router query succeeds and no client device remains after ignored addresses are excluded
- **THEN** the reported level is `empty`, the level is marked fresh, and no error is reported

#### Scenario: Failed query does not report empty

- **WHEN** a router query fails
- **THEN** the reported level is unchanged from the last successful observation rather than being set to `empty`

### Requirement: The presence level carries a freshness indication

The service SHALL expose whether the reported level is current. A level is fresh when the most
recent successful observation is within a configured maximum age and stale otherwise, so that a
poller which stops making progress (rather than raising) is also surfaced as stale. Before any
observation has succeeded, the level MUST be reported as stale with no last-updated timestamp.

#### Scenario: No successful observation yet

- **WHEN** the service has not completed a successful router query since start
- **THEN** the reported level is marked stale and the last-updated timestamp is absent

#### Scenario: Recent successful observation is fresh

- **WHEN** the last successful observation is younger than the configured maximum age
- **THEN** the reported level is marked fresh and carries that observation's timestamp

#### Scenario: Aged observation becomes stale without a failure

- **WHEN** the last successful observation is older than the configured maximum age
- **THEN** the reported level is marked stale even though no query reported an error

#### Scenario: A later success restores freshness

- **WHEN** a stale level is followed by a successful observation
- **THEN** the level is marked fresh, the timestamp advances, and any recorded error is cleared

### Requirement: The public status response distinguishes unknown from empty

The unauthenticated status response SHALL let a client determine both the level and its freshness,
so that a stale or unknown level is not presented as a confirmed current state.

#### Scenario: Stale level is identifiable by an unauthenticated client

- **WHEN** the presence level is stale and an unauthenticated client requests the status endpoint
- **THEN** the response conveys that the level is not current in addition to returning the last known level

#### Scenario: Fresh level is identifiable by an unauthenticated client

- **WHEN** the presence level is fresh
- **THEN** the response conveys that the level is current

### Requirement: Arrival notifications require fresh consecutive observations

The first-arrival notification MUST only be produced from observations that are fresh and belong to
the regular polling sequence. A non-empty result that follows a stale or unknown period MUST NOT be
treated as somebody arriving, because it may simply be the first successful observation after an
outage.

#### Scenario: Arrival after a stale period does not notify

- **WHEN** the previous published level was stale or unknown and a successful observation reports a non-empty level
- **THEN** no arrival notification is sent for that observation

#### Scenario: Arrival between fresh polls notifies once per day

- **WHEN** a fresh observation reports `empty` and the next fresh observation reports a non-empty level, and no arrival notification has been sent for that day
- **THEN** exactly one arrival notification is sent and no further arrival notification is sent for the same day

#### Scenario: The first observation after start does not notify

- **WHEN** the first successful observation after service start reports a non-empty level
- **THEN** no arrival notification is sent
