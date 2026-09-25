## Purpose

Session-identifier lifecycle guarantees so that a superseded or signed-out session cookie
can no longer be replayed to authenticate.

## ADDED Requirements

### Requirement: Superseded session identifiers are revoked on rotation

When the system rotates a session identifier — after a successful sign-in and when a
session is created from an API-key header — it SHALL remove the superseded server-side
session record, so a cookie issued earlier in that session is no longer accepted.

#### Scenario: Previous cookie is rejected after re-authentication

- **WHEN** a client authenticates, receives a session cookie, then authenticates again and receives a new cookie
- **THEN** a request replaying the earlier cookie is rejected as unauthenticated, while the newly issued cookie authenticates successfully

#### Scenario: Sign-out terminates the current and superseded identifiers

- **WHEN** a client signs in twice and then signs out
- **THEN** both issued cookies are rejected as unauthenticated

#### Scenario: A session without prior identifier rotates without error

- **WHEN** an API-key header request creates a session where no session identifier existed before
- **THEN** the request succeeds and a usable session cookie is issued

#### Scenario: Unrelated concurrent sessions are unaffected

- **WHEN** one client rotates its session identifier while another client holds a separate valid session
- **THEN** the other client's session continues to authenticate successfully
