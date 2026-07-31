# ADR 0002: Re-key HGNC ortholog fallback join to indexed relationship

- **Status:** Accepted
- **Date:** 2026-07-31
- **Owners:** Data pipeline engineering

## Context

The ortholog fallback path for HGNC data previously depended on a string-based equality
join that was difficult for MySQL to optimize and vulnerable to performance regressions
on larger snapshots.

## Decision

Use the indexed foreign-key path in `genefam_orthologs` for fallback matching:

- Join on `go.genefam_id_b = ghx.genefam_id`
- Keep taxon and non-null constraints needed to preserve intended row coverage
- Continue preferring explicit `hgnc_ortholog` xrefs when present, with fallback only
  when that xref is unavailable

## Consequences

### Positive
- Improves query planner friendliness and runtime performance characteristics.
- Reduces risk of full scans in the fallback branch.
- Preserves semantic behavior while improving scalability.

### Trade-offs
- Requires explicit verification against production-like data snapshots.
- Introduces stronger coupling to relational integrity assumptions.

## Validation

- Targeted tests for fallback behavior pass.
- Query contract tests pass.
- Pre-launch checks include benchmark/verification notes for this join path.
