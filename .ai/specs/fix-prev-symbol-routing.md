# Spec: Fix prev_symbol / prev_name routing into alias fields

> Status: RED test failing; awaiting GREEN
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
