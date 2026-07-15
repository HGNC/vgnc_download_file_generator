# Spec: Fix pubmed_id (null + render as array)

> Status: planning
> Branch: `gcp` (follow-up to `fix-vgnc-data-correctness`)

## Problem

`pubmed_id` ships as `null` in the download files even when the gene has PubMed
xrefs. Example: gene **VGNC:112953** has the PubMed xref
(`xref.id=1159817`, `external_db_id=23`, `xref=40407593`, `status=Current`) but
its JSON row is `"pubmed_id": null`.

Additionally, a gene may carry **several** PubMed references, so `pubmed_id`
must render as an **array** in JSON (mirroring `uniprot_ids`), not a single value.

## Root cause

Two independent bugs, both in the xrefs pipeline:

1. **Null pubmed.** `build_xrefs_query` filters `WHERE ghx.created_by = 1`.
   That filter is shared by all xref types, yet only PubMed comes back null.
   PubMed links are created by a different editor id, so `created_by = 1`
   excludes them entirely. (Confirmed: `database_resource.id=23` has
   `db_name='pubmed'`, so the `CASE WHEN` match is correct; the editor filter is
   the only remaining cause.) The filter is a stale legacy constraint — the
   aggregations (`MAX` / `GROUP_CONCAT DISTINCT`) already collapse duplicate
   links, so dropping it is safe.
2. **Single value, not array.** `pubmed_id` uses `MAX(...)`, which keeps one
   value. It must use `GROUP_CONCAT(... SEPARATOR '|')` (like `uniprot_ids`),
   be added to `_array_json_fields()`, and the runtime validator must validate
   each pipe-separated segment instead of the whole string.

## Scope of change

- `src/vgnc_download_file_generator/database/queries_split.py` — `build_xrefs_query`:
  - Drop `WHERE ghx.created_by = 1`; make the `genefam_id IN ...` clause a
    standalone conditional `WHERE`.
  - Switch `pubmed_id` from `MAX(...)` to `GROUP_CONCAT(DISTINCT ... SEPARATOR '|')`.
- `src/vgnc_download_file_generator/generators/vgnc_public.py`
  - `_array_json_fields()`: add `"pubmed_id"` so JSON renders a list
    (`["40407593"]`, `[]` for empty, `null` for None). TSV unchanged
    (pipe-separated string).
- `src/vgnc_download_file_generator/validation.py`
  - `VgncIdRecord.pubmed_id`: validate each `|`-segment as digits (mirror
    `uniprot_ids`), not the whole string.

## Tasks

### Task 1 — Drop the `created_by = 1` filter (fixes the null)
- **Change:** in `build_xrefs_query`, remove `WHERE ghx.created_by = 1`; the
  only remaining predicate becomes a conditional `WHERE ghx.genefam_id IN ...`
  when `genefam_ids` is supplied.
- **Verify:** `test_xrefs_has_no_created_by_filter` asserts the rendered SQL
  contains no `created_by`; existing xref-column / db_name tests still pass.

### Task 2 — `pubmed_id` as an array end-to-end
- **Change:** `MAX(...)` → `GROUP_CONCAT(DISTINCT ... SEPARATOR '|')` for
  `pubmed_id`; add `"pubmed_id"` to `_array_json_fields()`; validator validates
  pipe-separated PubMed segments.
- **Verify:** `test_xrefs_pubmed_uses_group_concat` (SQL uses GROUP_CONCAT +
  `SEPARATOR '|'` + `AS pubmed_id`, not MAX); `test_json_pubmed_id_rendered_as_array`
  feeds `"40407593|123"` and asserts JSON `["40407593","123"]`;
  `test_json_pubmed_id_none_is_null` and `..._empty_string_is_empty_array`;
  `test_pubmed_id_single_and_multi` validator accepts `40407593` and
  `40407593|123`, rejects `PMID:1`.

## Risks

- Removing `created_by = 1` applies to **all** xref types. De-duplication is
  handled by `MAX` / `GROUP_CONCAT DISTINCT`, so no duplicate columns appear;
  but the live DB should be spot-checked after deploy that no draft/stale xref
  leaks into ncbi/ensembl/etc. (Task 7-style pre-deploy gate).
- `GROUP_CONCAT` has a MySQL `group_concat_max_len` default of 1024; genes with
  very many PubMed refs could truncate. Mitigate with `DISTINCT` (already used)
  and verify against the gene with the most PubMed xrefs at the pre-deploy gate.
