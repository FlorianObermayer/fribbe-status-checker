## Purpose

Persistence guarantees for the API key store so that a whole-store replacement is never
observable in a partial state by concurrent readers.

## ADDED Requirements

### Requirement: API key store replacement is a single atomic write

When the system replaces the contents of the persisted API key store, it SHALL persist the
replacement as a single write, so that a concurrent reader observes either the complete
previous contents or the complete new contents and never an empty or partial store.

#### Scenario: Concurrent authentication is not invalidated during a replacement

- **WHEN** the API key store is replaced while requests authenticate with a key that is present both before and after the replacement
- **THEN** those requests are authenticated successfully and none is rejected with `401`

#### Scenario: A single write carries the replacement

- **WHEN** the store is replaced with a new list of keys
- **THEN** exactly one persist operation occurs and the resulting stored contents equal the new list
