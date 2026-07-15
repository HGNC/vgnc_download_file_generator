# Spec: Fix horde_id (missing) + drop primary_db_id

> Status: Tasks 1-2 implemented + unit tests green (344 passed); pre-deploy DB spot-check pending
> Branch: `gcp` (follow-up to pubmed fix)

## Problem

Two download-file column bugs:

1. **`horde_id` is always empty.** It is listed in `_STANDARD_HEADERS`
   (`vgnc_public.py`) but is **never fetched** — `build_xrefs_query` has no
   `CASE WHEN` for it. So every row ships `horde_id` blank. The HORDE resource
   is `database_resource.id=31` / `db_name='horde'` (confirmed from the live
   `database_resource` table). The user's instinct ("wrong external_db_id,
   should be 31") is the right column; the deeper issue is that the column was
   never added to the SELECT at all.
2. **`primary_db_id` must not be shipped.** It is appended to the header row
   for the "All" species files (`get_headers`) but is never populated. Per
   request, remove it from TSV and JSON output entirely.

## Scope of change

- `src/vgnc_download_file_generator/database/queries_split.py` —
  `build_xrefs_query`: add
  `MAX(CASE WHEN dr.db_name = 'horde' THEN x.xref END) AS horde_id` (a gene has
  one HORDE id, so `MAX`, not `GROUP_CONCAT`); update the docstring (7 xref
  types).
- `src/vgnc_download_file_generator/generators/vgnc_public.py`
  - `_get_column_map`: add the explicit `"horde_id": "horde_id"` mapping
    (consistent with `bgd_id`/`hgnc_orthologs`).
  - `get_headers`: remove `headers.append("primary_db_id")` and its comment.
- Tests: assert `horde_id` is fetched via `db_name='horde'`; assert
  `primary_db_id` is absent from headers; update the stale header-count
  assertions.

## Tasks

### Task 1 — Fetch `horde_id`
- **Change:** add the `horde` CASE-WHEN to `build_xrefs_query`; map
  `horde_id` in `_get_column_map`.
- **Verify:** `test_xrefs_horde_uses_horde_resource_name` asserts
  `MAX(CASE WHEN dr.db_name = 'horde' THEN x.xref END) AS horde_id`; the
  all-columns test asserts `horde_id` is present (7 types).

### Task 2 — Drop `primary_db_id` from output
- **Change:** remove `headers.append("primary_db_id")` in `get_headers`.
- **Verify:** `test_all_species_does_not_include_primary_db_id` asserts
  `"primary_db_id" not in headers`; the All-species header count drops to 25
  (24 standard + taxon_id); the zebrafish+All count drops to 26; the last
  header is `hgnc_orthologs`.

## Risks

- HORDE applies to olfactory-receptor genes (a subset); most genes legitimately
  have no HORDE id → `horde_id` stays NULL, matching HGNC's treatment.
- Removing `primary_db_id` changes the "All" species header set (one fewer
  column) — downstream consumers keyed on that trailing column must update.
