"""Runtime ID-format validation for VGNC records.

Catches swapped or malformed cross-reference IDs at generation time so that bad
data never reaches GCS. The contract is encoded as a pydantic model
(:class:`VgncIdRecord`) applied to every streamed record; a :class:`RecordValidator`
enforces a per-field grace threshold so systematic bugs (e.g. an entire swapped
column) fail the run while a handful of legacy outliers are tolerated.

Authoritative formats (see ``.ai/specs/fix-vgnc-data-correctness.md`` Task 4):
- VGNC ID (assigned_id): ``VGNC:<digits>``
- NCBI/Entrez Gene ID: digits only
- Ensembl Gene ID: ``ENS`` + <=4-letter species prefix + ``G`` + 11 digits
- UniProt accession: 6 or 10 chars (official UniProt regex)
- PubMed ID: digits only
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

logger = logging.getLogger(__name__)

# Authoritative ID patterns (compiled once).
VGNC_ID_RE = re.compile(r"^VGNC:\d+$")
NCBI_ID_RE = re.compile(r"^\d+$")
ENSEMBL_GENE_ID_RE = re.compile(r"^ENS[A-Z]{0,4}G\d{11}$")
UNIPROT_RE = re.compile(
    r"^([OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2})$"
)
PUBMED_ID_RE = re.compile(r"^\d+$")


def _require(pattern: re.Pattern[str], value: Any, label: str) -> Any:
    """Allow None / empty string; otherwise require ``value`` to match ``pattern``."""
    if value is None:
        return None
    text = str(value)
    if text == "":
        return ""
    if not pattern.match(text):
        raise ValueError(f"invalid {label}: {value!r}")
    return text


def _require_each(pattern: re.Pattern[str], value: Any, label: str) -> Any:
    """Like :func:`_require` but for pipe-separated array fields (e.g.
    ``uniprot_ids``, ``pubmed_id``): each non-empty segment must match
    ``pattern``. None / empty pass through unchanged."""
    if value is None:
        return None
    text = str(value)
    if text == "":
        return ""
    bad = [part for part in text.split("|") if part and not pattern.match(part)]
    if bad:
        raise ValueError(f"invalid {label}: {bad}")
    return text


class VgncIdRecord(BaseModel):
    """Per-record ID format contract.

    Only the ID fields are declared; every other key in the validated dict is
    ignored (``extra="ignore"``) so the full merged gene row can be passed in
    directly. ``None`` and ``""`` are allowed because a gene may legitimately
    lack any given identifier.
    """

    model_config = ConfigDict(extra="ignore")

    assigned_id: str | None = None
    ncbi_gene_id: str | None = None
    ensembl_gene_id: str | None = None
    uniprot_ids: str | None = None  # pipe-separated UniProt accessions
    pubmed_id: str | None = None  # pipe-separated PubMed IDs

    @field_validator("assigned_id")
    @classmethod
    def _check_assigned_id(cls, v: Any) -> Any:
        return _require(VGNC_ID_RE, v, "VGNC ID (expected VGNC:<digits>)")

    @field_validator("ncbi_gene_id")
    @classmethod
    def _check_ncbi(cls, v: Any) -> Any:
        return _require(NCBI_ID_RE, v, "NCBI Gene ID (expected digits)")

    @field_validator("ensembl_gene_id")
    @classmethod
    def _check_ensembl(cls, v: Any) -> Any:
        return _require(
            ENSEMBL_GENE_ID_RE,
            v,
            "Ensembl Gene ID (expected ENS[A-Z]{0,4}G + 11 digits)",
        )

    @field_validator("pubmed_id")
    @classmethod
    def _check_pubmed(cls, v: Any) -> Any:
        return _require_each(PUBMED_ID_RE, v, "PubMed ID(s)")

    @field_validator("uniprot_ids")
    @classmethod
    def _check_uniprot(cls, v: Any) -> Any:
        return _require_each(UNIPROT_RE, v, "UniProt accession(s)")


class RecordValidator:
    """Run-level validator with a per-field grace threshold.

    Each :meth:`check` validates one record. Violations are counted per field.

    - ``strict`` (default): once a field exceeds ``grace`` violations the
      validator raises -- this catches systematic bugs (an entire swapped
      column violates on every row) while tolerating up to ``grace`` legacy
      outliers.
    - ``warn``: violations are logged and never raised.

    Guarantee that bad data does not ship: keep ``grace`` smaller than the
    streaming ``chunk_size`` (default 5000). A systematic violation then raises
    within the first chunk, before any data chunk is yielded to the GCS writer
    (only the header line would have been written).
    """

    def __init__(self, mode: str = "strict", grace: int = 50) -> None:
        if mode not in ("strict", "warn"):
            raise ValueError(f"mode must be 'strict' or 'warn', got {mode!r}")
        if grace < 0:
            raise ValueError(f"grace must be >= 0, got {grace}")
        self.mode = mode
        self.grace = grace
        self._counts: dict[str, int] = {}

    def check(self, record: dict[str, Any]) -> None:
        """Validate one merged record; raise (strict) or log (warn) on failure."""
        try:
            VgncIdRecord.model_validate(record)
        except ValidationError as exc:
            fields = {str(err["loc"][0]) for err in exc.errors()}
            for field in fields:
                self._counts[field] = self._counts.get(field, 0) + 1
                if self.mode == "strict" and self._counts[field] > self.grace:
                    raise
                if self.mode == "warn":
                    logger.warning(
                        "ID validation violation on field %s (count=%d): %s",
                        field,
                        self._counts[field],
                        exc,
                    )

    def summary(self) -> dict[str, int]:
        """Return per-field violation counts observed so far."""
        return dict(self._counts)


def make_validator() -> RecordValidator:
    """Build a :class:`RecordValidator` from environment variables.

    Reads ``VGNC_VALIDATION_MODE`` (``strict`` | ``warn``, default ``strict``)
    and ``VGNC_VALIDATION_GRACE`` (int, default 50).
    """
    mode = os.environ.get("VGNC_VALIDATION_MODE", "strict").strip().lower()
    try:
        grace = int(os.environ.get("VGNC_VALIDATION_GRACE", "50"))
    except ValueError:
        grace = 50
    return RecordValidator(mode=mode, grace=grace)
