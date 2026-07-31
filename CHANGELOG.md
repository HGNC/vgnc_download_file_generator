# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Runtime ID-format validation guardrails (`strict` / `warn` modes) to catch malformed
  or swapped cross-reference IDs before upload.
- Fail-fast query verification notes and supporting checks for ortholog fallback behavior.
- Explicit rollback plan documentation (`docs/ROLLBACK_PLAN.md`).

### Changed
- Aligned `hgnc_orthologs` export logic with website homolog behavior by accepting both
  `hgnc_gene` and `hgnc_ortholog` xrefs, preserving multiple HGNC IDs in pipe-delimited
  output, and adding exact HGNC-symbol fallback (website step 3) via `pub_hgnc` when available.
- Replaced long-lived streaming cursor export with keyset-paginated short-lived DB pages
  to avoid Cloud SQL connection drops during long GCS uploads.
- Re-keyed HGNC ortholog fallback join to indexed `genefam_id_b` path for performance and
  stability, while preserving prior result semantics.
- Hardened typing across config, generator filter flow, DB connection retry wrappers,
  and GCS writer internals; `mypy` now passes cleanly.
- Refined output-generation behavior to continue producing species-level all-genes,
  locus-type, and locus-group files under current publication policy.
- Refreshed dependency lockfile to patched releases (including `requests`, `urllib3`,
  `protobuf`, `pyasn1`, `idna`, and `pygments`) to clear vulnerability findings.
- Updated CLI option error assertion to remain compatible with current Click wording.

### Fixed
- Removed type-check regressions that previously blocked pre-launch quality gates.
- Preserved expected validation error behavior when invalid DB port values are provided.

## [0.1.0] - Initial release
- Core VGNC download file generator with TSV/JSON output, GCS uploads, and Cloud Run job packaging.
