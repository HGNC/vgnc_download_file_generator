# Spec: Fix vgnc-download-files "Server has gone away" (long-lived streaming cursor)

> Status: DONE — implemented; full suite (375) + integration parity green; mypy/ruff clean
> Branch: `task-fix-streaming-connection-drop` (off `gcp`)

## Problem (observed)

The `vgnc-download-files` Cloud Run Job aborted on 2026-07-30:

```
MySQLdb.OperationalError: (2013, 'Lost connection to server during query')   # in gene_cursor fetchone()
MySQLdb.OperationalError: (2006, 'Server has gone away')                       # pool finalizer ROLLBACK
```

The fatal frame is `VgncPublic.stream_rows` reading the gene-data
**server-side cursor**:

```
__main__.py:335  for line in row_iterator
vgnc_public.py:291  generate_tsv_rows -> stream_rows
vgnc_public.py:231  stream_rows: gene_cursor.close()            # cleanup, secondary
vgnc_public.py:205  stream_rows: for row in gene_cursor          # PRIMARY: fetchone() -> 2013
```

## Root cause

`stream_rows()` reads the **entire** gene dataset through one
`MySQLdb.cursors.SSCursor` on a single pooled connection (`gene_cursor =
self.db.get_streaming_cursor()`). A server-side cursor pins that connection +
its server-side result set open until the last row is fetched — for a full
species / "All" run that is many minutes.

Between batches the generator does non-DB work on a *second* connection:
per-batch xrefs/aliases/dates sub-queries (`sub_cursor`) and the GCS upload
(`__main__.py` `f.write(...)`). During all of that the streaming connection is
**never read and never pinged**. In a Cloud Run → Cloud SQL topology an idle
socket is dropped (Cloud SQL proxy / intermediate LB / MySQL `wait_timeout`);
the next `fetchone()` discovers a dead socket → `(2013)`.

The cascade after that is cleanup noise, not separate bugs:
- `finally: gene_cursor.close()` → `_discard()` on the dead conn → another `(2013)`.
- SQLAlchemy pool finalizer `ROLLBACK` on the dead conn → `(2006)`.

Nothing recovers it: `_retry_on_mysql_error` wraps only *checkout*
(`get_connection`/`_create_connection`), never the streaming fetch; and an
SSCursor is bound to one connection, so it cannot be resumed.

Supporting evidence (confirmed by reading the code):
- `read_timeout=600`/`write_timeout=600` (`connection.py`) only bound a *blocked*
  socket read — they send no keepalives, so they never prevent an idle drop.
- `QueuePool(recycle=60)` only refreshes connections **at checkout**, never
  mid-hold, so it cannot help a long-checked-out streaming cursor.
- The earlier "two cursors sharing one connection" footgun is already fixed via
  the `_proxy_connection` pin (`connection.py`), so `gene_cursor` (C1) and
  `sub_cursor` (C2) are genuinely distinct connections — this failure is purely
  the idle-drop on C1.

This is the class of failure the unit suite cannot catch: tests mock the DB or
run tiny fixtures, never a multi-minute real stream.

## Fix — address the root cause

**Stop holding one cursor open for the whole export. Fetch gene data in
discrete, keyset-paginated batches, each on a short-lived connection.**

Per batch (all DB reads on one connection, then release it *before* the
chunk is yielded upstream for GCS upload):

1. **ID page** (split-safe, index-scanned, stops at LIMIT):
   ```sql
   SELECT DISTINCT gf.genefam_id
   FROM genefam gf <…same joins/filters…>
   WHERE <filters> AND gf.genefam_id > :after_genefam_id
   ORDER BY gf.genefam_id
   LIMIT :batch_size
   ```
2. **Gene rows for that page** (no LIMIT; fetches every row incl. family
   fan-out, exactly as today):
   ```sql
   SELECT DISTINCT <14 cols>
   FROM genefam gf <…same joins/filters…>
   WHERE <filters> AND gf.genefam_id IN :page_ids
   ```
3. **Sub-queries** (xrefs/aliases/dates) for `page_ids` — unchanged.
4. Merge → map → validate → **materialise** the mapped rows.
5. Release the connection (`conn.close()` → returns to pool).
6. Yield the materialised rows as chunks. `last_id = page_ids[-1]`; stop when a
   page is short (`len(page_ids) < batch_size`).

Why this is correct and safe:
- `genefam_id` is the `genefam` PK, so keyset pagination is stable and
  lossless: a gene's rows always share one `genefam_id`, so advancing
  `last_id` past `page_ids[-1]` never splits or skips a gene (the two-phase
  page→rows design makes the family-join fan-out split-free).
- Output becomes **deterministic** (ascending `genefam_id`). The previous query
  had no `ORDER BY`, so order was the server's natural order; ordering by the PK
  is a strict improvement and no test asserts full-file byte order.
- `_process_batch` (merge + map + validation + `location_sortable`) is
  **unchanged** — it still receives `gene_batch` + a live cursor for sub-queries.
  Its validation/abort and `location_sortable` behavior are preserved verbatim.

Connection lifecycle is the crux: a connection is held only for the few seconds
of DB reads, then returned before the (slow) GCS upload — so no single
connection is idle long enough to be dropped. `get_connection()` is already
retry-wrapped, so a transient drop on checkout retries the batch cleanly.

> Out of scope (noted, not done here): the stale `recycle` docstring
> (`connection.py` says `recycle=300`, code is `60`) — unrelated to the crash;
> `get_streaming_cursor` is left in place (still unit-tested, env-gated) but no
> longer used by the generator.

## Constraints (explicit decisions)

- **Root-cause fix, not a keepalive band-aid.** We remove the long-lived
  cursor rather than papering over it with `wait_timeout`/pre-ping (which do
  not protect against proxy/network idle drops).
- **No streaming cursor for gene data.** Buffered per-batch queries only.
- **Deterministic ascending `genefam_id` output** is acceptable/intended.
- **No schema migration.** This module is a read-only consumer of `vgnc_public`.
- **`_process_batch` signature is unchanged** to keep validation/`location_sortable`
  tests intact; only `stream_rows` + the query builders change.

## Why the suite missed it

`TestVgncPublicStreamRows` mocks `get_streaming_cursor`/`get_cursor` and asserts
the streaming pattern *itself* — i.e. the tests encode the buggy design, so they
pass while production drops the connection. There is no test asserting that the
generator (a) never uses a server-side cursor, (b) paginates, or (c) does not
hold one connection across the whole stream.

## Tasks

### Task 1 — RED: keyset query builders + pagination/lifecycle guards

1. **Query builders (`tests/test_split_queries.py`):**
   - New `build_gene_id_page_query(filters, after_genefam_id, limit)` returns a
     `TextClause` whose `.text` contains `SELECT DISTINCT gf.genefam_id`, the
     same core JOINs/WHERE, `gf.genefam_id > :after_genefam_id`, `ORDER BY
     gf.genefam_id`, `LIMIT :limit`, with bound params. Filter routing
     (taxon_id/locus/status_id) is inherited.
   - `build_gene_data_query(filters, genefam_ids=[...])` adds `AND
     gf.genefam_id IN :genefam_ids` (expanding bind) and leaves the existing
     no-`genefam_ids` path unchanged (backward compatible).
   - *Fails on current code*: neither symbol/param exists yet.

2. **Generator contract (`tests/test_vgnc_public_stream.py`):** replace the
   obsolete `TestVgncPublicStreamRows` cases (which assert
   `get_streaming_cursor` is used) with:
   - `test_stream_rows_does_not_use_streaming_cursor` — after a full drain,
     `db.get_streaming_cursor.assert_not_called()`.
   - `test_stream_rows_checks_out_connection_per_batch` — with a fake cursor
     serving 2 non-empty ID pages then an empty one, assert
     `db.get_connection.call_count == 3` (one checkout per page attempt,
     including the terminating empty page) **and** that each checked-out
     connection had `.close()` called — i.e. no connection is held across the
     whole stream.
   - `test_stream_rows_paginates_all_rows_in_order` — the same fake returns
     IDs [1,2] then [3] then []; assert the yielded rows cover genefam_ids
     {1,2,3} exactly once, in ascending order, with no duplicates/gaps.

   These drive a fake cursor that dispatches on SQL content (ID-page query vs
   gene/sub queries) and advance `after_genefam_id`. `TestVgncPublicRuntimeValidation`
   and `TestVgncPublicLocationSortable` (which test `_process_batch` directly)
   are **unchanged** and must stay green — they are the non-regression guard for
   validation/`location_sortable`.

- **Verify:** `uv run pytest tests/test_split_queries.py::TestBuildGeneIdPageQuery
  tests/test_split_queries.py::TestBuildGeneDataQuery tests/test_vgnc_public_stream.py
  -m "not integration"` — the new builder + generator tests **fail on current
  `gcp` HEAD** (symbols/behavior absent); the two `_process_batch` classes stay green.

### Task 2 — GREEN: keyset pagination in `stream_rows`

- In `queries_split.py`: factor the shared `SELECT…FROM…JOINs…WHERE` core out of
  `build_gene_data_query` (existing `.text` substring assertions must still
  hold) and add `build_gene_id_page_query(filters, after_genefam_id, limit)`.
  Extend `build_gene_data_query` with an optional `genefam_ids` → expanding
  `IN :genefam_ids`. Backward compatible when `genefam_ids` is None.
- In `vgnc_public.py` `stream_rows`: replace the single SSCursor drain with the
  per-batch keyset loop described in *Fix*. Use `self.db.get_connection()` →
  `conn.cursor()` (MySQLdb default **buffered** cursor) → run ID page + gene
  rows + sub-queries + merge/map/validate **inside** the connection scope,
  materialise mapped rows, then `cursor.close()`/`conn.close()` in `finally`,
  **then** yield chunks. `_process_batch` is called unchanged.
- Remove the `get_streaming_cursor()` call from `stream_rows`.

- **Verify:** the Task 1 tests pass; full suite green:
  `uv run pytest --integration` (unit + integration).

### Task 3 — Integration parity guard (MySQL, `--integration`)

Add `@pytest.mark.integration` tests in `tests/test_vgnc_public_stream.py`
following the existing `mysql_*_schema` ephemeral-DB pattern (`MYSQL_TEST_DSN`,
default `root:root@127.0.0.1:3306`):

- Seed `genefam` (+ the minimal joined tables) with e.g. 7 genes for a taxon,
  one of which fans out to 2 `gene_has_family` rows, plus a second taxon's gene
  that must be excluded by the taxon filter.
- With `batch_size=3`, drive `stream_rows()` through a real `DatabaseConnection`
  and assert: every gene of the target taxon is yielded **exactly once**; rows
  arrive in ascending `genefam_id` order; the cross-taxon gene is absent; the
  fanned-out gene's family rows are both present (no split/loss across the page
  boundary).

- **Verify:** `uv run pytest tests/test_vgnc_public_stream.py -m integration`
  green against the local MySQL (it is reachable at `127.0.0.1:3306`).

## Out of scope

- `wait_timeout`/keepalive/pre-ping tuning — rejected (does not fix the root
  cause; the long-lived cursor is removed instead).
- Adding/removing DB indexes — none needed; keyset pagination rides the
  `genefam` PK.
- Removing `get_streaming_cursor` / fixing the stale `recycle=300` docstring —
  unrelated to the crash; deferred.
- Splitting the ortholog/xref sub-queries — already batched per page; out of scope.

## Affected files

- `src/vgnc_download_file_generator/database/queries_split.py`
  (factor core; add `build_gene_id_page_query`; extend `build_gene_data_query`)
- `src/vgnc_download_file_generator/generators/vgnc_public.py` (`stream_rows`)
- `tests/test_split_queries.py` (new builder tests)
- `tests/test_vgnc_public_stream.py` (replace streaming-pattern tests; add
  pagination/lifecycle unit tests + MySQL integration parity tests)


## Implementation notes (post-implementation)

- The fix was applied to **all three** generators (vgnc_public, vgnc_withdrawn,
  vgnc_ensembl): they shared the identical long-lived-cursor bug. The drop-safe
  keyset loop was factored into `BaseFileGenerator._paginate_gene_stream` once
  (rather than triplicated) so the correctness-critical loop cannot drift.
- `_process_batch` (merge + map + validation + `location_sortable`) is unchanged.
- A `paginating_db` pytest fixture (conftest) drives the shared loop without a
  real DB; a MySQL `--integration` parity test proves no gaps/dupes, ascending
  order, family-fan-out preservation, and taxon-filter exclusion.
- mypy: zero new errors (the only remaining ones are the pre-existing
  `filters["status_id"] = <STATUS_IDS>` assignment pattern present on `gcp` in
  all three generators).

