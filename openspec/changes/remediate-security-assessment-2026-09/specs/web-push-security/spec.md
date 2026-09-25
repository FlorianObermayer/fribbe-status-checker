## Purpose

Abuse controls on the unauthenticated Web Push subscription surface so that anonymous
callers cannot cause outbound requests to internal hosts, stall the application, or grow
server-side state without bound.

## ADDED Requirements

### Requirement: Push subscription destinations are restricted to public HTTPS hosts

The system SHALL accept a push subscription endpoint only when it is an absolute `https`
URL, carries no userinfo, and resolves exclusively to globally routable addresses. The
system MUST reject endpoints whose scheme is not `https`, that have no host, that carry
userinfo, that cannot be resolved, or that resolve to at least one non-globally-routable
address (including loopback, private, link-local, shared/CGNAT, multicast and unspecified
ranges).

#### Scenario: Public push service endpoint is accepted

- **WHEN** an unauthenticated client submits a subscription whose endpoint is an `https` URL resolving only to globally routable addresses
- **THEN** the subscription is stored and the response is `201`

#### Scenario: Internal address forms are rejected

- **WHEN** a subscription endpoint points at `127.0.0.1`, `::1`, an RFC1918 address, a link-local address, or a numeric notation that resolves to a loopback address
- **THEN** the request is rejected with `422` and no subscription is stored

#### Scenario: Userinfo-bearing endpoint is rejected

- **WHEN** a subscription endpoint contains userinfo, for example `https://user:pass@127.0.0.1/x`
- **THEN** the request is rejected with `422` and no subscription is stored

#### Scenario: Non-resolving host is rejected

- **WHEN** a subscription endpoint host cannot be resolved
- **THEN** the request is rejected with `422` and no subscription is stored

#### Scenario: Non-HTTPS scheme is rejected

- **WHEN** a subscription endpoint uses a scheme other than `https`
- **THEN** the request is rejected with `422` and no subscription is stored

### Requirement: Push delivery is time-bounded and off the event loop

The system SHALL bound the duration of every outbound push request with a finite timeout,
MUST NOT follow HTTP redirects when delivering a push, and MUST perform push delivery
without blocking the ASGI event loop from any asynchronous entry point that reaches it.

#### Scenario: Unresponsive endpoint does not stall the service

- **WHEN** a stored subscription points at a host that accepts the connection and never responds, and a push event occurs
- **THEN** the delivery attempt is abandoned after the configured timeout and unrelated requests continue to be served during the attempt

#### Scenario: Redirecting endpoint does not reach an internal host

- **WHEN** a stored endpoint responds with a redirect to an internal plain-HTTP address
- **THEN** the redirect is not followed and no request reaches the internal address

#### Scenario: Notification creation does not block the event loop

- **WHEN** an operator creates a notification while a stored endpoint is slow to respond
- **THEN** other requests continue to be served while delivery is in progress

### Requirement: The push subscription store is bounded

The system SHALL limit the number of stored push subscriptions to a fixed maximum and SHALL
reject registration of a new subscription once the store is at capacity, surfacing the
condition to the client as an error response rather than accepting the write. Replacing an
existing subscription MUST remain possible when the store is at capacity.

#### Scenario: New subscription is rejected at capacity

- **WHEN** the store already holds the maximum number of subscriptions and a client registers a subscription under a new auth value
- **THEN** the request is rejected with an error status and the store size is unchanged

#### Scenario: Existing subscription can be replaced at capacity

- **WHEN** the store is at capacity and a client re-registers using an existing auth value
- **THEN** the request succeeds and the store size is unchanged

#### Scenario: A slot freed by unsubscribe can be reused

- **WHEN** a subscription is removed while the store is at capacity and a new subscription is then registered
- **THEN** the new subscription is accepted
