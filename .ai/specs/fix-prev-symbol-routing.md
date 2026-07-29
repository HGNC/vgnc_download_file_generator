# Spec: Fix prev_symbol / prev_name routing into alias fields

> Status: FIXED + verified on prod; synthetic + real-data tests green
> Branch: `task-fix-prev-symbol-routing` (off `gcp`)

## Problem (client report)

> "The prev_symbol and prev_name fields are completely empty. It looks like
> prev_symbol and prev_name are ending up in the alias_symbol and alias_name
> fields. One example is VGNC:10098 where C17orf75 should be the prev_symbol but
> ends up in the alias_symbol field."

`prev_symbol` and `prev_name` ship **empty** for every gene, while those values
are misrouted into `alias_symbol` / `alias_name`.

## Root cause (confirmed against production)

`build_aliases_query` (`queries_split.py`) splits alternative symbols/names into
"previous" vs "alias" using a hard-coded nomenclature_type literal that **does
not exist in the database**:

```sql
WHERE nt.type = 'Previous'    -- previous symbols/names
WHERE nt.type != 'Previous'   -- alias symbols/names
```

The real `nomenclature_type` rows (queried from `vgnc_public` on the live DB) are:

| id | type             |
|----|------------------|
| 1  | `previous_symbol`|
| 2  | `previous_name`  |
| 3  | `alias_symbol`   |
| 4  | `alias_name`     |

Zero rows equal `'Previous'`, so:
- The previous subqueries (`nt.type = 'Previous'`) match **nothing** → `prev_symbol`
  and `prev_name` are empty.
- The alias subqueries (`nt.type != 'Previous'`) match **all four** types → previous
  symbols/names leak into `alias_symbol` / `alias_name`.

Example verified on prod: VGNC:10098's `C17orf75` is `nomenclature_type =
previous_symbol`, so it lands in `alias_symbol` and `prev_symbol` is blank.
Impact: **2,489** genes have a previous symbol and **8,741** have a previous name;
all currently misrouted.

## Why the test suite missed it

`TestBuildAliasesQuery` only asserts that the literal strings `"prev_symbol"`,
`"alias_symbol"`, `"GROUP_CONCAT"`, `"IN"` appear in the SQL text. These are
format checks, not behavioral tests (AGENTS.md rejects these). The query also uses
MySQL-only `GROUP_CONCAT ... SEPARATOR`, so it cannot execute on the in-memory
SQLite harness used elsewhere in the file — which is why the team fell back to
substring asserts.

## Fix

Route each output column by its **exact** nomenclature_type value (clean 1:1
mapping):

- alias_symbol  ← `nt.type = 'alias_symbol'`
- alias_name    ← `nt.type = 'alias_name'`
- prev_symbol   ← `nt.type = 'previous_symbol'`
- prev_name     ← `nt.type = 'previous_name'`

This is also more robust than the old `= 'Previous'` / `!= 'Previous'` binary
split: any future new nomenclature_type no longer silently leaks into alias
fields.

## Tasks

### Task 1 — RED: behavioral integration test for alias routing
Add an integration test (`@pytest.mark.integration`) that runs the **real**
`build_aliases_query` against an ephemeral MySQL schema seeded with all four
`nomenclature_type` values and a gene carrying one value of each type, then
asserts each lands in the correct output column. Skipped by default; runs with
`--integration` against a local/dev MySQL (`MYSQL_TEST_DSN`).

- **Verify:** `pytest tests/test_split_queries.py -k alias_routing --integration`
  fails on current code (prev fields empty, prev values in alias fields).

### Task 2 — GREEN: route by exact nomenclature_type
Update the four UNION branches in `build_aliases_query` to filter by the exact
type value instead of `'Previous'` / `!= 'Previous'`.

- **Verify:** the Task 1 integration test passes; full suite green.

### Task 3 — prod spot-check
Re-run the VGNC:10098 alias query against `vgnc_public` via cloud-sql-proxy and
confirm `C17orf75` is in `prev_symbol`, `alias_symbol` excludes it.

- **Verify:** manual query returns prev_symbol = `C17orf75`, alias_symbol does not
  contain it.

### Task 4 — real-data fixture test (from vgnc_public_2026_07_05 dump)
Trim the dump's five alias tables (nomenclature_type, alt_symbol, alt_name,
gene_alt_symbol, gene_alt_name) into a committed fixture
(`tests/fixtures/vgnc_aliases_snapshot.sql`) and add an integration test that
cross-checks the SQL output against an independent Python re-derivation for
every gene, plus headline spot-checks: alias-only gene 697, previous-only gene
13195, and gene 91593 (VGNC:81821) whose same name string is stored under both
`alias_name` and `previous_name` (per-type routing). Confirmed to fail on the
old `= 'Previous'` query.

- **Verify:** `pytest tests/test_split_queries.py::TestBuildAliasesQueryRealSnapshot --integration` passes.

## Sweep: other hardcoded DB-content literals (same bug family)

Audited every hardcoded value the SQL/generators match against DB *data* (not
structure) against the vgnc_public_2026_07_05 dump. **All are currently
correct** -- nomenclature_type was the only actual bug:

| Literal | Where | Real value | Status |
|---|---|---|---|
| `db_name` x7 (ncbi_gene, ensembl_gene, uniprot_protein, pubmed, hgnc_ortholog, bgd_gene, horde) | build_xrefs_query | all present in database_resource | OK |
| `status_id [6,11,12]` | vgnc_public, vgnc_ensembl | Approved / Auto Approved / Cont Approved (display=Approved) | OK |
| `status_id [2,3]` | vgnc_withdrawn | Symbol Withdrawn / Entry Withdrawn | OK |
| `field_changed` assigned_symbol/assigned_name | build_dates_query | both present in change_type | OK |
| `nomenclature_type` x4 | build_aliases_query | previous_symbol/previous_name/alias_symbol/alias_name | FIXED (was 'Previous') |

Note: pubmed (db_name id 23) has **0 genes** in this snapshot, so it has no
real-data xref coverage; it is synthesised in the xrefs test to exercise the
pubmed_id code path, and its literal is pinned by the dictionary contract test.

### Guards added (tests/test_query_data_contracts.py)
- **Dictionary contract test**: loads the real lookup tables and asserts every
  hardcoded literal exists (catches DB drift / renumbering). status_id lists are
  imported from the generators as named constants (single source of truth) so
  code and test cannot drift apart.
- **xref routing cross-check**: runs the real build_xrefs_query vs an
  independent Python re-derivation for every gene in the sample -- a wrong
  db_name routes to the wrong column and the oracle disagrees. Verified to fail
  on a broken db_name literal.
- **dates routing cross-check**: same approach for field_changed -> date cols.
  Verified to fail on a broken field_changed literal.
- **status_id IN-filter test**: behavioural (SQLite) check that the lists
  actually select the right gene rows.

Source change: `PUBLIC_STATUS_IDS` / `WITHDRAWN_STATUS_IDS` extracted to
generator.py (previously inline `[6,11,12]` / `[2,3]` in three files).
