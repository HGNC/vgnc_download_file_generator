# Spec: Fix VGNC download-file data correctness

> Status: in-progress
> Branch: `fix/vgnc-data-correctness` (off `gcp`)

## Problem

The last production run on Airflow/GCP produced VGNC download files with
incorrect data. Confirmed bugs (reported against gene ABHD12 / VGNC:14936):

1. **Duplicate rows per gene.** A gene with locations on multiple genome
   assemblies produced one row *per assembly* (4 rows for ABHD12). There must
   be exactly **one row per gene**, using the species' default VGNC assembly.
2. **`location` / `location_sortable` incorrect.** A consequence of (1): the
   emitted location is not the canonical (default-assembly) location.
3. **`ncbi_id` and `ensembl_gene_id` are swapped.** In the VGNC DB,
   `external_db_id = 1` is the **Ensembl** Gene ID and `external_db_id = 2` is
   the **NCBI** Gene ID. The code maps them the other way around, so `ncbi_id`
   shipped Ensembl IDs and `ensembl_gene_id` shipped NCBI IDs.
4. **`uniprot_ids` must be an array.** Today it is a single value (`MAX(...)`).
   A gene can have multiple UniProt IDs (external_db_id IN (3, 15)); these must
   be collected into an array — JSON: `["Q12345","P67890"]`, TSV: pipe-separated
   `Q12345|P67890`. `ensembl_gene_id` remains a plain string (not an array).

## Reference (location)

The location join must be equivalent in intent to (INNER-join semantics in the
reference; we use LEFT JOIN + ON-conditions to preserve genes that have no
default-assembly location):

```sql
SELECT genefam.*, gene_has_location.*, chromosomes.*, assembly.*
FROM genefam
JOIN gene_has_location ON genefam.genefam_id = gene_has_location.gene_id
JOIN assembly          ON gene_has_location.assembly_id = assembly.id
JOIN gene_location     ON gene_has_location.location_id = gene_location.id
JOIN chromosomes       ON gene_location.chr_id = chromosomes.chr_id
WHERE genefam.assigned_id = 'VGNC:14936'
  AND genefam.taxon_id = assembly.taxon_id
  AND assembly.is_vgnc_default = 1;
```

Key: filter `gene_has_location` down to the row whose assembly is the species'
default (`assembly.is_vgnc_default = 1` and `assembly.taxon_id = gf.taxon_id`).

## Scope of change

- `src/vgnc_download_file_generator/database/queries_split.py`
  - `build_gene_data_query`: add the `assembly` join + default-assembly filter.
  - `build_xrefs_query`: swap ncbi/ensembl external_db_id mapping; switch
    `uniprot_ids` from `MAX(...)` to `GROUP_CONCAT(... SEPARATOR '|')`; update
    the docstring.
- `src/vgnc_download_file_generator/generators/vgnc_public.py`
  - JSON serialization: render `uniprot_ids` as a JSON array; keep
    `ensembl_gene_id` a plain string. TSV unchanged (pipe-separated string).
- `src/vgnc_download_file_generator/generators/vgnc_ensembl.py`
  - JSON serialization: render `uniprot_ids` as a JSON array for consistency.
- Tests: RED-first additions in `tests/test_split_queries.py`,
  `tests/test_vgnc_public_json.py`, `tests/test_vgnc_ensembl.py`.

## Out of scope

- "All chromosomes" per-species files excluding locationless genes (pre-existing
  behavior of `c.taxon_id = gf.taxon_id`); not part of this bug.
- Multiple locations on the *same* default assembly (rare); reference query has
  the same characteristic.
- Chromosome discovery (`db_query_helper.py`) query shape (already scoped to a
  species and unaffected).

## Tasks (each Task.Verify line IS the RED test)

### Task 1 — Location: one row per gene on the default assembly
- **Change:** add `LEFT JOIN assembly a ON ghl.assembly_id = a.id AND a.is_vgnc_default = 1 AND a.taxon_id = gf.taxon_id` to `build_gene_data_query`.
- **Verify:** `test_build_gene_data_query_filters_default_assembly` asserts the generated SQL joins `assembly` on `ghl.assembly_id = a.id` and contains `a.is_vgnc_default = 1` and `a.taxon_id = gf.taxon_id`.

### Task 2 — Xrefs: swap ncbi_id / ensembl_gene_id
- **Change:** in `build_xrefs_query`, map `external_db_id = 2 → ncbi_gene_id` and `external_db_id = 1 → ensembl_gene_id`.
- **Verify:** `test_xrefs_ncbi_uses_external_db_id_2` and `test_xrefs_ensembl_uses_external_db_id_1` assert the correct CASE-WHEN branch per output column.

### Task 3 — Xrefs + serialization: uniprot_ids as an array
- **Change:** `build_xrefs_query` uses `GROUP_CONCAT(DISTINCT CASE WHEN x.external_db_id IN (3,15) THEN x.xref END SEPARATOR '|') AS uniprot_ids`; JSON output splits the pipe string into a JSON array (empty → `[]`, None → `null`).
- **Verify:** `test_xrefs_uniprot_uses_group_concat` (SQL uses GROUP_CONCAT, not MAX); `test_json_uniprot_ids_rendered_as_array` feeds `"Q9H0A9|P12345"` and asserts JSON `["Q9H0A9","P12345"]`; `test_json_uniprot_ids_empty_is_empty_array` and `..._none_is_null`.

## Risks

- `assembly` table/column names assumed from the reference query (`assembly`,
  `assembly.id`, `assembly.assembly_id` join via `gene_has_location.assembly_id`,
  `assembly.is_vgnc_default`, `assembly.taxon_id`). No schema file in repo;
  confirmed by the user-provided reference query.
- Splitting the pipe string relies on UniProt IDs never containing `|` (true).
