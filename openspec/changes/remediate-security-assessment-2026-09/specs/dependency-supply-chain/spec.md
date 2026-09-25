## Purpose

Supply-chain hygiene for the production dependency set so that the shipped image does not
include unused packages affected by published advisories, while keeping the test-only
dependencies the framework's test client requires.

## ADDED Requirements

### Requirement: Advisory-affected packages are not shipped in production

The production dependency set SHALL NOT include a package that no application code imports
while that package is affected by a published advisory. A package that is required only for
testing (and therefore absent from the production image because the image is built with
`uv sync --no-dev`) MUST be pinned above the advisory range.

#### Scenario: Advisory-affected package is absent from the production dependency set

- **WHEN** the production dependencies and lockfile are inspected after this change
- **THEN** `httpx2` is no longer a runtime dependency and the production image does not install it

#### Scenario: Test-only dependency is patched above the advisories

- **WHEN** the test dependency set is inspected
- **THEN** `httpx2` is present only in the development dependency group at a version above the published advisory range

#### Scenario: Imported HTTP client is declared directly

- **WHEN** application code imports an HTTP client for push delivery
- **THEN** that client is declared as a direct production dependency

#### Scenario: Repository dependency audit reports no advisories

- **WHEN** the repository dependency audit runs against the updated lockfile
- **THEN** it reports no known vulnerabilities
