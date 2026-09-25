## Purpose

Hardening of the unauthenticated HTTP surface so that redirect parameters, anonymous
notification reads, free-form input used for parsing, and error fields cannot be abused to
navigate users off-origin, read withdrawn content, exhaust processing, or disclose internal
addressing.

## ADDED Requirements

### Requirement: The `next` redirect parameter is validated against its resolved origin

The system SHALL normalize the `next` value the way a browser normalizes a URL before
validating it — removing ASCII tab, line-feed and carriage-return characters and treating
`\` as a path separator — and SHALL accept the value only when it is an absolute path that
resolves to the application's own origin. Rejected values MUST be replaced with `/`. The
system SHALL percent-encode the value fully when it builds an application-generated
redirect URL that embeds `next`.

#### Scenario: Backslash and control-character variants resolve on-origin

- **WHEN** a client supplies `/\evil.com`, a tab-prefixed `//evil.com`, or `/\@evil.com` as `next`
- **THEN** the value the application stores and emits is `/`

#### Scenario: Protocol-relative and absolute URLs are rejected

- **WHEN** a client supplies `//evil.com`, `https://evil.com` or a non-HTTP scheme as `next`
- **THEN** the value the application stores and emits is `/`

#### Scenario: Legitimate application path is preserved

- **WHEN** a client supplies a legitimate same-origin path with a query string, such as `/notification-create?n_ids=nid-1`
- **THEN** the value is returned unchanged in the login page, the cancel link and the post-login redirect

#### Scenario: Application-generated redirect encodes the parameter

- **WHEN** the application builds an `/auth?next=...` redirect for an unauthenticated request to a protected page
- **THEN** the embedded `next` value is fully percent-encoded so it cannot introduce an additional parameter

### Requirement: Anonymous notification reads are restricted to active notifications

When a caller is not authenticated, the system SHALL return only notifications that are
active, including when the caller requests specific `nid-*` identifiers. Authenticated
callers SHALL retain access to inactive, disabled and out-of-window notifications.

#### Scenario: Anonymous read of an inactive notification yields no content

- **WHEN** an unauthenticated client requests a notification identifier whose notification is disabled or outside its validity window
- **THEN** the response contains no notification content

#### Scenario: Anonymous read of an active notification still succeeds

- **WHEN** an unauthenticated client requests an active notification identifier
- **THEN** the response contains that notification

#### Scenario: Authenticated read of an inactive notification still succeeds

- **WHEN** an authenticated client requests a disabled or out-of-window notification identifier
- **THEN** the response contains that notification

### Requirement: The `for_date` parameter is bounded before parsing

The system SHALL bound the length of the free-form `for_date` value before it is passed to
the date parser, falling back to the current date when the bound is exceeded, so that an
unbounded value cannot impose unbounded parsing work.

#### Scenario: Oversized value falls back to the current date

- **WHEN** a client supplies a `for_date` value longer than the accepted maximum
- **THEN** the system treats the date as the current date instead of parsing the value

#### Scenario: Normal date value is unaffected

- **WHEN** a client supplies a normal date value such as `2025-06-01`
- **THEN** that exact date is used

### Requirement: Unauthenticated error fields do not disclose internal addressing

The unauthenticated status response SHALL NOT contain raw third-party exception text that
could embed internal host names, addresses or ports. The system SHALL return a stable,
client-safe failure message on the public endpoint while retaining full detail in
server-side logs.

#### Scenario: Failing presence poll does not disclose an internal address

- **WHEN** the presence poll fails because the configured router is unreachable and a client reads `/api/status`
- **THEN** the presence error field contains a generic message with no address or port

#### Scenario: Successful poll reports no error

- **WHEN** the presence poll has succeeded
- **THEN** the presence error field is null
