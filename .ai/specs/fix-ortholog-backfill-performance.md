# Spec: Fix hgnc_orthologs backfill performance regression (unindexed `vgnc_b` join)

> Status: IN PROGRESS — T1 (tests) and T2 (implementation) complete. T3 (EXPLAIN verification) remains.

> Branch: `gcp` (local commits ahead of origin/gcp)

> Format note: This is a **one-off**. It is the only spec in `.ai/specs/` using the
> `- [ ] Task:` checkbox format; the six sibling specs (`fix-streaming-…`,
> `fix-vgnc-data-…`, etc.) still use the `### Task N — title` header style. The
> repo convention is **not** changed by this file.

---

## Objective

The `vgnc-download-files` Cloud Run Job became dramatically slower after commit
`e7c3aa3` ("backfill hgnc orthologs from ortholog table"). The regression is
localized to `build_xrefs_query()` (`queries_split.py`), which runs once per
species plus once for the cross-species pass, so the cost stacks across the whole
job.

**Success = the ortholog fallback join uses an indexed access path** (an
`EXPLAIN` index lookup, not a full table scan) **with byte-exact output parity**
for covered genes — achieved by re-keying the join onto an already-indexed
foreign key, with **no schema migration**.

User / consumer: downstream pipelines that read the generated VGNC download
files; operators of the shared Cloud SQL instance the job runs against.

## Context — root cause & fix (all claims grounded)

> Every claim below is labeled **[Confirmed]** (verified against `gcp` HEAD +
> the committed `vgnc_public_2026_07_05` snapshot), **[Target]** (what we will
> build), or **[Proposed]**.

### Problem [Confirmed]

`e7c3aa3` added an ortholog-fallback join to `build_xrefs_query()`. Current code
(`queries_split.py:273-277`):

```sql
JOIN genefam gf        ON ghx.genefam_id = gf.genefam_id
LEFT JOIN genefam_orthologs go
    ON go.vgnc_b   = gf.assigned_id      -- ← unindexed leading column
   AND go.taxon_b  = gf.taxon_id
   AND go.taxon_a  = 9606
```

[Confirmed] `genefam_orthologs` keys are: PK `go_id`, `unique_ortholog`,
`genefam_orthologs_idx_genefam_id_b`, `taxon_b`, `symbol_a`, `db_id_a`. **There
is no index on `vgnc_b`** (snapshot DDL line 671 region). For every gene, MySQL
full-scans the ~410K-row table → (genes × 410K) rows of work per query.

### Fix [Target]

Re-key the fallback join onto the already-indexed `genefam_id_b` foreign key and
drop the redundant `JOIN genefam gf` (link directly to `ghx.genefam_id`):

```sql
-- [Target]
LEFT JOIN genefam_orthologs go
    ON go.genefam_id_b = ghx.genefam_id   -- ← uses genefam_orthologs_idx_genefam_id_b
   AND go.taxon_a      = 9606
   AND go.vgnc_b IS NOT NULL              -- preserve current row set (excludes ~44K NULL-vgnc_b rows)
```

[Confirmed] `genefam_id_b` is a populated FK → `genefam.genefam_id`
(`ghx.genefam_id`), so it pins the gene exactly and `taxon_b` becomes redundant.
`taxon_a = 9606` keeps the human→VGNC direction. `AND go.vgnc_b IS NOT NULL` is a
cheap post-index predicate that preserves today's output (the old
`vgnc_b = assigned_id` match already required a non-null `vgnc_b`), so it
reintroduces no scan. `COALESCE(MAX(hgnc_ortholog xref), MAX(go.db_id_a …))` and
the `MAX`/`GROUP_CONCAT` aggregation are unchanged.

This turns a per-gene full table scan into an index `ref` lookup. **No schema
migration is required** — the supporting index already exists.

### Evidence the re-key is safe and lossless [Confirmed]

Measured across the committed snapshot (410,285 `genefam_orthologs` rows):

| metric | count |
|---|---|
| `genefam_id_b` IS NULL | **1** |
| `vgnc_b` IS NULL | 44,436 |
| `vgnc_b` SET but `genefam_id_b` NULL (rows LOST by re-keying) | **0** |

`genefam_id_b` is far more reliably populated than `vgnc_b`. Because we keep
`AND go.vgnc_b IS NOT NULL`, the matched row set equals today's: the ~44K
NULL-`vgnc_b` rows stay excluded, and zero currently-matched row is lost.

> Byte-exact parity note: the new join matches by FK + non-null `vgnc_b`, whereas
> the old join matched by string equality (`vgnc_b = assigned_id`). These coincide
> whenever `vgnc_b` holds the b-side gene's own accession (the normal case). Task
> 1's parity guard and Task 3's snapshot cross-check confirm output parity for
> covered genes.

### Why the suite missed it [Confirmed]

The `e7c3aa3` tests assert the backfill *result* is correct (the right HGNC id
appears), which passes regardless of whether the join uses an index — they prove
the query is *right*, never that it is *fast*. The minimal fixtures
(`tests/test_split_queries.py:599`, `tests/test_query_data_contracts.py:63-64`)
`CREATE TABLE genefam_orthologs (go_id, taxon_a, taxon_b, db_id_a, vgnc_b)` — they
omit `genefam_id_b` entirely, so they cannot represent or guard the access path.

## Related Specs

- Related: `.ai/specs/fix-streaming-connection-drop.md` — same module
  (`build_xrefs_query` / `stream_rows`), unrelated defect (idle-connection drop).
- Related: `.ai/specs/fix-vgnc-data-correctness.md` — establishes the
  `### Task N` + `- **Verify:**` convention this file deliberately departs from.

## Tech Stack

[Confirmed] Python `>=3.13`; SQLAlchemy `>=2.0`; mysqlclient `>=2.2.0`;
google-cloud-storage `>=2.17.0`; click; rich; pydantic `>=2.0`.
Dev: pytest `>=7.4` (+ pytest-mock, pytest-benchmark, pytest-timeout), mypy,
ruff. Package manager: `uv`. Source DB: read-only consumer of `vgnc_public`
(MySQL/Cloud SQL).

## Commands

[Confirmed]

```
Test (unit):       uv run pytest -m "not integration"
Test (integration, needs MySQL on MYSQL_TEST_DSN, default root:root@127.0.0.1:3306):
                   uv run pytest --integration
One suite:         uv run pytest tests/test_split_queries.py --integration
Lint:              uv run ruff check
Types:             uv run mypy src
```

## Project Structure

[Confirmed]

```
src/vgnc_download_file_generator/
  database/        → SQL query builders (queries_split.py: build_xrefs_query)
  generators/      → per-format generators (vgnc_public.py consumes build_xrefs_query)
  models/ writers/ utils/
tests/
  test_split_queries.py        → query-builder + ortholog-fallback tests (touched)
  test_query_data_contracts.py → xref routing fixture (touched)
.ai/specs/                     → specs + the committed vgnc_public_2026_07_05[_data].sql snapshot
```

## Code Style

[Confirmed pattern, from `build_xrefs_query`] SQL is authored as a Python
f-string and returned as a SQLAlchemy `TextClause`; expanding `IN` lists use
`bindparam(..., expanding=True)`:

```python
def build_xrefs_query(genefam_ids: list[int] | None = None) -> TextClause:
    sql = f"""
        SELECT ... ,
            COALESCE(
                MAX(CASE WHEN dr.db_name = 'hgnc_ortholog' THEN x.xref END),
                MAX(CASE WHEN go.db_id_a LIKE 'HGNC:%%' THEN go.db_id_a END)   # %% = literal % (SQLAlchemy escaping)
            ) AS hgnc_orthologs
        FROM gene_has_xrefs ghx
        ...
    """
    if genefam_ids:
        query = text(sql).bindparams(
            bindparam("genefam_ids", value=tuple(genefam_ids), expanding=True)
        )
    else:
        query = text(sql)
    return query
```

Conventions relevant here: literal `%` in f-string SQL is written `%%` (do not
"fix" it to a single `%`); `--strict-markers` is on, so every `@pytest.mark.*`
must be a declared marker (`unit` / `integration` / `e2e`).

## Testing Strategy

[Confirmed] pytest, markers `unit` / `integration` / `e2e`; DB tests are gated
behind the `--integration` flag and an ephemeral MySQL reachable at
`MYSQL_TEST_DSN`. Integration fixtures follow the `mysql_*_schema` pattern
(`CREATE TABLE …` → seed → assert). Coverage: new/changed code must be covered;
no regression in the existing `_process_batch` / xref-routing suites.

This defect's specific gap: existing tests proved the query *right*, not *fast*.
The new guard therefore asserts the **access path** (indexed join + an index
whose leading column is `genefam_id_b`), not a wall-clock threshold.

## Boundaries

- **Always:** write the failing test first (RED); run the full suite before
  advancing; keep `COALESCE`/`MAX`/`GROUP_CONCAT` semantics identical.
- **Ask first:** any change to the `vgnc_public` source schema (none is needed or
  intended here); adding the ortholog lookup as a separate Python-merged query.
- **Never:** add a schema index on `genefam_orthologs(vgnc_b, …)` (unnecessary —
  indexed FK covers it; this module doesn't own the source DB schema); commit a
  `pytest-benchmark` numeric baseline as the gate; change the `%%` literal to `%`.

## Tasks

- [x] **Task: RED — access-path guard + output-parity guard**
  - **Acceptance:** `@pytest.mark.integration` tests in `tests/test_split_queries.py`.
    (1) Access-path guard: the `genefam_orthologs` fixture is created **with** a
    `genefam_id_b` column **and** `CREATE INDEX … ON genefam_orthologs(genefam_id_b)`
    (the fixture itself must supply the index so the test fails for the *right*
    reason — the join predicate — not a missing index); assert
    `build_xrefs_query().text` joins on `genefam_id_b` **and** that an index whose
    leading column is `genefam_id_b` exists (`information_schema.statistics`).
    (2) Output-parity guard: extend
    `test_falls_back_to_genefam_orthologs_when_xref_missing` to populate
    `genefam_id_b` → gene's `genefam_id`; keep the backfill assertion, and add a
    second gene whose ortholog row has `vgnc_b = NULL` but `genefam_id_b` set,
    asserting its `hgnc_orthologs` does **not** backfill (pins
    `AND go.vgnc_b IS NOT NULL`).
  - **Verify:** `uv run pytest tests/test_split_queries.py -k "ortholog_explain or falls_back_to_genefam_orthologs" --integration`
    — the access-path guard **fails on current `gcp` HEAD** (joins on unindexed
    `vgnc_b`); the parity guard passes on HEAD and must stay green after the re-key.
  - **Files:** `tests/test_split_queries.py`; `tests/test_query_data_contracts.py`
    (add `genefam_id_b` column + seeded value to the xref fixture).

- [x] **Task: GREEN — re-key the join onto `genefam_id_b` + `vgnc_b IS NOT NULL`**
  - **Acceptance:** in `build_xrefs_query` (`queries_split.py`), replace the
    `vgnc_b`/`genefam` join block with
    `LEFT JOIN genefam_orthologs go ON go.genefam_id_b = ghx.genefam_id AND go.taxon_a = 9606 AND go.vgnc_b IS NOT NULL`;
    remove the now-redundant `JOIN genefam gf`. Update the docstring (fallback now
    keyed by FK with a non-null `vgnc_b` guard, preserving current output). Keep
    `COALESCE(MAX(hgnc_ortholog xref), MAX(go.db_id_a LIKE 'HGNC:%%'))` identical
    — **do not** change the doubled `%%`.
  - **Verify:** Task 1 tests pass (access-path guard now green);
    `uv run pytest tests/test_split_queries.py tests/test_query_data_contracts.py --integration`
    green (xref routing cross-check unchanged → byte-exact parity for covered
    genes); `uv run pytest` full suite green.
  - **Files:** `src/vgnc_download_file_generator/database/queries_split.py`.

- [ ] **Task: Confirm indexed access at real scale (one-off `EXPLAIN`)**
  - **Acceptance:** load the committed snapshot
    (`.ai/specs/vgnc_public_2026_07_05[_data].sql`, 410K ortholog rows) into a
    local MySQL; run `EXPLAIN` on the compiled `build_xrefs_query()`. Confirm the
    `genefam_orthologs` row reports `type` ∈ {`ref`, `eq_ref`, `range`} with
    `key = genefam_orthologs_idx_genefam_id_b` (i.e. **not** `type=ALL`). Capture
    the output in the task notes.
  - **Verify:** scripted `EXPLAIN` output for `genefam_orthologs` shows index
    access (not `ALL`) using `genefam_orthologs_idx_genefam_id_b`.
    > Why a one-off, not a CI gate: `EXPLAIN` plans depend on table statistics; a
    > tiny CI fixture can report a misleading plan. The 410K-row snapshot yields
    > the truthful production-equivalent plan (loading the full dump per CI run is
    > too heavy; Task 1's `information_schema` guard is the cheap permanent check).
  - **Files:** none (verification only; load snapshot into ephemeral MySQL).

## Success Criteria

- [Confirmed target] `build_xrefs_query()` joins `genefam_orthologs` on
  `genefam_id_b` with `go.vgnc_b IS NOT NULL`; the `JOIN genefam gf` is gone.
- [Confirmed target] A permanent `information_schema`-based test guards that an
  index whose leading column is `genefam_id_b` exists and is used by the join.
- [Confirmed target] Output parity: covered genes backfill identically;
  `vgnc_b IS NULL` rows stay excluded (parity test green before and after).
- [Confirmed target] Real-scale `EXPLAIN` reports index access
  (`genefam_orthologs_idx_genefam_id_b`), not `ALL`.
- No schema migration, no new index, no `pytest-benchmark` baseline added.

## Open Questions

- None blocking. (Both items from the prior review — the `%%` literal and the
  fixture-must-create-its-own-index detail — are now encoded as explicit
  Acceptance/Verify constraints above.)
