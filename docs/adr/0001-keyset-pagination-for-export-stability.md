# ADR 0001: Use keyset pagination with short-lived DB connections for export stability

- **Status:** Accepted
- **Date:** 2026-07-31
- **Owners:** Data pipeline engineering

## Context

Large VGNC exports previously relied on a single long-lived server-side cursor while rows
were streamed and uploaded to GCS. In production-like conditions, this allowed one MySQL
connection to remain open across prolonged I/O windows and increased exposure to connection
staleness and timeout-related failures.

## Decision

Adopt keyset pagination over `genefam_id` and process exports in bounded pages:

- Fetch one page of IDs (`genefam_id > last_id ORDER BY genefam_id LIMIT N`)
- Fetch full rows and sub-query data for that page
- Release DB connection before yielding/uploading the page data
- Repeat until no IDs remain

## Consequences

### Positive
- Reduces connection lifetime per page and minimizes timeout exposure.
- Preserves stable, lossless traversal because `genefam_id` is a primary key.
- Keeps memory bounded while maintaining streaming behavior.

### Trade-offs
- Additional query orchestration complexity.
- Requires careful parity validation to ensure row output semantics remain unchanged.

## Validation

- Full automated test suite passes.
- Query/data contract checks cover behavioral parity assumptions.
- Build and static checks pass in pre-launch gate.
