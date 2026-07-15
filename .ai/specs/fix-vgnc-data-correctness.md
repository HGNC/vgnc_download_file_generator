# Spec: Fix VGNC download-file data correctness

> Status: review-fixes-applied + runtime ID validation + partial-file cleanup + Ensembl-default-source pin (pending pre-deploy DB validation)
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
  AND assembly.is_vgnc_default = 1
  AND assembly.source = 'Ensembl';
```

Key: filter `gene_has_location` down to the row whose assembly is the species'
default (`assembly.is_vgnc_default = 1` and `assembly.taxon_id = gf.taxon_id`).
`is_vgnc_default` is NOT unique per species: VGNC:6926 (Pan troglodytes) carries
two default assemblies -- `NCBI` `Pan_tro_3.0` (chr 14) and `Ensembl`
`Pan_tro_3.0` (chr 1) -- so the Task 1 fan-out recurred. The canonical default is
the Ensembl-sourced one, so also require `assembly.source = 'Ensembl'` (Task 7).

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
- **Change:** restrict `gene_has_location` itself to the default assembly via a
  correlated EXISTS on the `ghl` JOIN condition
  (`EXISTS (SELECT 1 FROM assembly a WHERE a.id = ghl.assembly_id AND a.is_vgnc_default = 1 AND a.taxon_id = gf.taxon_id AND a.source = 'Ensembl')`).
  - **Why EXISTS, not a bare `LEFT JOIN assembly a ...`:** a bare assembly join is
    INERT — no `a.*` column is selected and `gene_location`/`chromosomes` join off
    `ghl` directly, so every `gene_has_location` row still emits one output row
    (the original 4-rows-per-gene bug). Reviewer reproduction confirmed 4 rows for
    the bare-join shape and 1 row for the EXISTS shape. The EXISTS lives on the
    `ghl` JOIN (not WHERE) so genes with no default-assembly location are preserved.
- **Verify:** `test_build_gene_data_query_filters_ghl_to_default_assembly` (EXISTS
  structure) and `test_build_gene_data_query_has_no_inert_assembly_join` (no bare
  `LEFT JOIN assembly a ON ghl.assembly_id = a.id`); plus behavioral
  `test_default_assembly_filter_collapses_to_one_row_per_gene` (in-memory SQLite:
  a gene with 4 locations across 4 assemblies yields 1 row; a locationless gene is
  preserved with NULL location).

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


## Review outcomes (parallel review pass)

Three fresh-context reviewers ran. Synthesis:

- **BLOCKER (Reviewer 1, correctness):** the first Task 1 attempt used a bare
  `LEFT JOIN assembly a ...` which is inert (no `a.*` selected; `gl`/`c` join off
  `ghl`). Confirmed by reproduction: 4 rows for ABHD12, not 1. **Fixed** by moving
  the filter to a correlated EXISTS on the `ghl` JOIN. The original RED test was a
  substring check that passed against the broken SQL — replaced with a structural
  test for the EXISTS shape + a regression guard against the inert join + a
  behavioral SQLite test.
- **BLOCKER (Reviewer 2, tests):** `VgncEnsembl` JSON-array path and the TSV
  pipe-separated `uniprot_ids` path were untested. **Fixed** — added
  `TestVgncEnsemblUniprotArray` and `TestVgncPublicTsvUniprotPipe`.
- **Note (Reviewer 3):** `assembly` schema is unverified in-repo (no schema file).
  Correctness rests on invariants: (i) exactly one default assembly per species,
  (ii) at most one location per default assembly. **Gated on pre-deploy validation
  (below).** Invariant (i) is now known to be VIOLATED in the live DB (VGNC:6926
  has two default assemblies, NCBI + Ensembl); Task 7 pins `source = 'Ensembl'`
  to restore a deterministic canonical location without relying on (i).
- **Note (Reviewer 3):** `GROUP_CONCAT` for uniprot has no `ORDER BY` →
  non-deterministic element order. Accepted (low severity; most genes have 0-1
  UniProt IDs). Adding `ORDER BY` inside `GROUP_CONCAT(DISTINCT CASE ...)` carries
  MySQL-syntax risk that cannot be validated without a live DB, so it is deferred.

## Pre-deploy validation (read-only, run against the VGNC DB before shipping to GCS)

Gate the GCS ship on all of these:

```sql
-- (A) Confirm the assembly / gene_has_location columns the JOIN depends on exist.
SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'assembly' AND COLUMN_NAME IN ('id','is_vgnc_default','taxon_id');
-- and: COLUMN_NAME = 'assembly_id' for TABLE_NAME = 'gene_has_location'

-- (B) Invariant (i): each species has EXACTLY ONE default assembly.
--     Any row here means the location join can still fan out.
SELECT taxon_id, COUNT(*) AS n_default FROM assembly
WHERE is_vgnc_default = 1 GROUP BY taxon_id HAVING COUNT(*) <> 1;
-- KNOWN VIOLATION (VGNC:6926: a species can have a default NCBI + default Ensembl
-- assembly). Task 7 pins the canonical default to source = 'Ensembl'. The
-- per-source gate that actually matters now:
SELECT taxon_id, COUNT(*) AS n_ensembl_default FROM assembly
WHERE is_vgnc_default = 1 AND source = 'Ensembl'
GROUP BY taxon_id HAVING COUNT(*) <> 1;
-- expect 0 rows; a species with 0 Ensembl defaults would lose ALL locations.

-- (C) ABHD12 / VGNC:14936 must now yield exactly ONE row (was 4).
SELECT gf.assigned_id, gf.assigned_symbol, c.display_name AS chr, gl.start, gl.end, gl.strand
FROM genefam gf
LEFT JOIN gene_has_location ghl ON gf.genefam_id = ghl.gene_id
    AND EXISTS (SELECT 1 FROM assembly a WHERE a.id = ghl.assembly_id
                AND a.is_vgnc_default = 1 AND a.taxon_id = gf.taxon_id
                AND a.source = 'Ensembl')
LEFT JOIN gene_location gl ON ghl.location_id = gl.id
LEFT JOIN chromosomes c ON gl.chr_id = c.chr_id
WHERE gf.assigned_id IN ('VGNC:14936', 'VGNC:6926');

-- (D) Confirm external_db_id semantics: 1 = Ensembl, 2 = NCBI/Entrez.
SELECT x.external_db_id, ed.name, COUNT(*) AS n
FROM gene_has_xrefs ghx JOIN xref x ON ghx.xref_id = x.id
JOIN external_db ed ON x.external_db_id = ed.id
WHERE x.external_db_id IN (1,2) GROUP BY x.external_db_id, ed.name;

-- (E) Spot-check ABHD12 xrefs land in the right columns.
SELECT x.external_db_id, x.xref FROM genefam gf
JOIN gene_has_xrefs ghx ON gf.genefam_id = ghx.genefam_id
JOIN xref x ON ghx.xref_id = x.id
WHERE gf.assigned_id = 'VGNC:14936' AND x.external_db_id IN (1,2,3,15);
-- expect: ext_db 1 values look like ENSxxx (Ensembl),
--         ext_db 2 values look like integers (NCBI Entrez).
```

Acceptance: (B)=0 rows, (C)=1 row, (D) labels match (Ensembl/NCBI), (E) value
shapes match.

## Known limitations

- `uniprot_ids` element order in output is non-deterministic (DB row order); the
  set of IDs is correct. See Review outcomes.
- `_pipe_string_to_list` keeps whitespace-only segments (e.g. `" "`); UniProt IDs
  never contain stray whitespace, so practical impact is nil.
- `generate_json_rows` is duplicated between `VgncPublic` and `VgncEnsembl`
  (pre-existing); the new array-rendering block is duplicated too. TODO: hoist
  `generate_json_rows` + the `_array_json_fields` loop into `BaseFileGenerator`.

### Task 4 — Runtime ID-format validation (pydantic) — prevention of recurrence

**Goal:** a swap or malformed ID must fail the run in production, not just in
tests. Add runtime validation of each record's ID fields against authoritative
formats, applied to every streamed record before it is mapped/yielded.

**Authoritative formats (from web research + schema):**
- `assigned_id` (VGNC ID): `^VGNC:\d+$`
- `ncbi_gene_id` (Entrez): `^\d+$`
- `ensembl_gene_id`: `^ENS[A-Z]{0,4}G\d{11}$` (ENS + ≤4-letter species prefix + G + 11 digits)
- `uniprot_ids` (each pipe segment): `^([OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2})$`
- `pubmed_id`: `^\d+$`

**Design:**
- `validation.py`: pydantic v2 `VgncIdRecord` (per-record format check, `extra="ignore"`,
  None/"" allowed) + `RecordValidator` enforcing a per-field **grace threshold**.
- Failure mode via env `VGNC_VALIDATION_MODE` = `strict` (default) | `warn`;
  `VGNC_VALIDATION_GRACE` (default 50).
- **Why grace < chunk_size (5000):** `stream_rows` only yields a chunk every
  `chunk_size` rows, so a systematic violation (e.g. a swap = 100% bad) raises at
  row `grace+1` (<< 5000) — before any data chunk is yielded, so no bad data rows
  reach GCS (only the header). Legacy outliers (≤ grace) are tolerated + logged.
- Wired into both generators' `_process_batch` on the pre-mapping merged dict
  (DB column names), so it covers all output formats regardless of header naming.

**Verify (RED first):** `tests/test_validation.py` — valid IDs pass; swapped
(ncbi=ENS…, ensembl=digits) and malformed values raise; None/"" pass; UniProt
multi-segment. `RecordValidator` raises in strict after grace exceeded, tolerates
≤ grace, never raises in warn. Generator `_process_batch` raises on a systematic
swap.

### Task 5 — GCS writer deletes partial files on failure

**Goal:** a failed generation (e.g. runtime validation aborting a swapped column)
must not leave a partial object in GCS.

**Change:** `GCSStreamWriter.open_write_stream` now tracks success and, on any
exception in the write body:
- non-compressed path: closes the stream, then best-effort deletes the blob
  (`_safe_delete`, errors logged not raised);
- compressed path: skips `upload_from_filename` entirely (the partial gzip temp
  is cleaned up), so nothing is uploaded.

Successful writes are unchanged (compressed uploads exactly once; non-compressed
never deleted).

**Verify:** `TestPartialFileCleanup` -- non-compressed deletes on exception and
not on success; compressed skips upload on exception and uploads once on success.

### Task 6 — `location_sortable` is the zero-padded chromosome only (no coordinates)

**Goal:** shipped `location_sortable` must match the documented definition ("Same
as `location` but single-digit chromosomes are prefixed with a 0 … e.g. `02q34`"),
restricted to the VGNC design where `location` is the bare chromosome. Genomic
coordinates must NOT appear in the field.

**Confirmed vs. live production data** (`cattle_vgnc_gene_set_All.tsv`):
`location` = bare chromosome (e.g. `18`, `5`, `X`); the old pipeline (and the
rewrite before this task) shipped `location_sortable` = `chromosome:start`
(e.g. `18:65641103`, `5:101040473`) with **no zero-padding at all** — so the field
wasn't even sortable (`1:...` sorts after `18:...` lexicographically). This task
fixes the FORMAT of bug #2, which Task 1 only addressed row-wise.

**Rule (per user):** `location_sortable` = `location` (the chromosome) with **only
single-digit numeric chromosomes** zero-padded: `1`-`9` -> `01`-`09`. Two-digit
numerics (`10`...`29`) and non-numeric labels (`X`, `Y`, `MT`, `Un`) are
unchanged. `None`/empty -> unchanged.

**Design:** derive in Python from the mapped `location`, not in SQL.
* New pure fn `format_location_sortable(chromosome)` in `generators/vgnc_public.py`
  (zero-pad iff `len==1 and isdigit()`). Real-behavior tested; DB-dialect-free.
* `VgncPublic._process_batch` injects `location_sortable` from mapped `location`.
* Remove the dead `CONCAT(display_name, ':', CAST(gl.start AS CHAR)) AS
  location_sortable` from `build_gene_data_query`.

**Verify (RED first):** `tests/test_vgnc_public.py` pads `1`->`01` ... `9`->`09`,
leaves `10`/`18`/`X`/`Y`/`MT`/`Un` and `None`/`""` unchanged.
`tests/test_vgnc_public_stream.py` `_process_batch` -> `"05"` for `chromosome="5"`,
`"X"` for `"X"`, `None` for a locationless gene.


### Task 7 - Location: pin the default assembly to `source = 'Ensembl'`

**Problem (observed in production):** `assembly.is_vgnc_default = 1` is NOT
unique per species. Confirmed for VGNC:6926 (Pan troglodytes, taxon 9598): two
default assemblies coexist -- assembly 3 `NCBI` `Pan_tro_3.0` (chr 14) and
assembly 23 `Ensembl` `Pan_tro_3.0` (chr 1), both `is_vgnc_default = 1`. The
Task 1 EXISTS matched both, so the gene emitted two location rows; the chr 14
NCBI row is wrong. This is exactly the fan-out the pre-deploy invariant (B) /
Reviewer-3 invariant (i) were meant to catch -- invariant (i) is violated in the
live DB.

**Change:** add `AND a.source = 'Ensembl'` to the `assembly` EXISTS in
`build_gene_data_query`, so the canonical location is the Ensembl-sourced default
assembly. (In the observed data the Ensembl default is also `is_current = 1`; the
chosen discriminator is `source`, per user direction.)

**Verify (RED first):** `test_build_gene_data_query_pins_default_assembly_to_ensembl_source`
asserts `a.source = 'Ensembl'` is present in the production SQL; the behavioral
`test_default_assembly_filter_collapses_to_one_row_per_gene` is updated to model
the two-default-assembly case (NCBI + Ensembl, mirroring the VGNC:6926
diagnostic) and assert a single chr-1 row.

**Pre-deploy gate:** each species must have exactly one Ensembl default assembly
-- see the per-source query added under invariant (B). A species with 0 Ensembl
defaults would lose ALL locations under this filter; investigate before shipping.
