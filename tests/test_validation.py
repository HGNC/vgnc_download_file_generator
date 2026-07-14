"""Tests for runtime ID-format validation (pydantic-based).

These encode the authoritative ID formats so a swapped/malformed column fails
loudly at generation time instead of shipping to GCS. No database required.
"""

import pytest
from pydantic import ValidationError


class TestVgncIdRecordFormats:
    """Per-record format validation against authoritative ID patterns."""

    def _record(self, **overrides):
        from vgnc_download_file_generator.validation import VgncIdRecord

        base = {
            "assigned_id": "VGNC:14936",
            "ncbi_gene_id": "100037417",
            "ensembl_gene_id": "ENSBTAG00000001234",
            "uniprot_ids": "Q9H0A9",
            "pubmed_id": "12345678",
        }
        base.update(overrides)
        return VgncIdRecord.model_validate(base)

    def test_valid_record_passes(self) -> None:
        """A fully well-formed record validates without error."""
        self._record()  # no exception

    def test_none_and_empty_pass(self) -> None:
        """Genes legitimately lacking an ID must pass (None / '')."""
        self._record(ncbi_gene_id=None, ensembl_gene_id="", uniprot_ids=None)
        self._record(ncbi_gene_id="", ensembl_gene_id=None)

    def test_vgnc_id_format(self) -> None:
        self._record(assigned_id="VGNC:14936")
        with pytest.raises(ValidationError):
            self._record(assigned_id="14936")
        with pytest.raises(ValidationError):
            self._record(assigned_id="HGNC:1234")

    def test_ncbi_id_must_be_numeric(self) -> None:
        """The original bug: ncbi_id shipped Ensembl IDs. A non-numeric ncbi_id
        (the swap signature) must be rejected."""
        self._record(ncbi_gene_id="100037417")
        with pytest.raises(ValidationError):
            self._record(ncbi_gene_id="ENSBTAG00000001234")  # Ensembl value -> swap
        with pytest.raises(ValidationError):
            self._record(ncbi_gene_id="Q9H0A9")  # UniProt value

    def test_ensembl_id_format(self) -> None:
        """Ensembl gene IDs: ENS + <=4-letter species prefix + G + 11 digits."""
        for good in [
            "ENSG00000157764",        # human (no species prefix)
            "ENSBTAG00000001234",     # cattle (BTA)
            "ENSDARG00000101234",     # zebrafish (DAR)
            "ENSRNORG00000000001",    # rat (RNOR, 4-letter prefix)
            "ENSMUSG00000000001",
        ]:
            self._record(ensembl_gene_id=good)
        with pytest.raises(ValidationError):
            self._record(ensembl_gene_id="100037417")  # numeric -> swap signature
        with pytest.raises(ValidationError):
            self._record(ensembl_gene_id="ENST00000123456")  # transcript (T), not gene (G)
        with pytest.raises(ValidationError):
            self._record(ensembl_gene_id="ENSBTAG00000012")  # too few digits

    def test_uniprot_single_and_multi(self) -> None:
        """UniProt accessions (6 or 10 chars), single or pipe-separated."""
        self._record(uniprot_ids="P12345")
        self._record(uniprot_ids="Q9H0A9")
        self._record(uniprot_ids="A0A1B2C3D4")  # 10-char
        self._record(uniprot_ids="Q9H0A9|P12345")  # multiple
        with pytest.raises(ValidationError):
            self._record(uniprot_ids="ENSBTAG00000001234")  # Ensembl, not UniProt
        with pytest.raises(ValidationError):
            self._record(uniprot_ids="Q9H0A9|BADID")
        with pytest.raises(ValidationError):
            self._record(uniprot_ids="12345")

    def test_pubmed_id_numeric(self) -> None:
        self._record(pubmed_id="12345678")
        with pytest.raises(ValidationError):
            self._record(pubmed_id="PMID:12345")

    def test_extra_fields_ignored(self) -> None:
        """The merged dict carries many non-ID fields; they must be ignored."""
        from vgnc_download_file_generator.validation import VgncIdRecord

        VgncIdRecord.model_validate(
            {"genefam_id": 1, "assigned_id": "VGNC:1", "alias_symbol": "FOO|BAR",
             "date_modified": "2024-01-01", "gene_status": "Approved"}
        )


class TestRecordValidatorGrace:
    """Run-level grace-threshold enforcement."""

    def _validator(self, **kw):
        from vgnc_download_file_generator.validation import RecordValidator

        return RecordValidator(**kw)

    def _swap_record(self, i: int) -> dict:
        # ncbi_gene_id holds an Ensembl value -> systematic swap (the bug)
        return {
            "assigned_id": f"VGNC:{i}",
            "ncbi_gene_id": f"ENSG00000{i:06d}",
            "ensembl_gene_id": str(1000000 + i),
        }

    def test_strict_raises_after_grace_exceeded(self) -> None:
        """A systematic violation (every row) raises once it passes the grace
        threshold."""
        v = self._validator(mode="strict", grace=5)
        for i in range(5):
            v.check(self._swap_record(i))  # tolerated (<= grace)
        with pytest.raises(ValidationError):
            v.check(self._swap_record(6))  # 6th violation -> raise

    def test_strict_tolerates_under_grace(self) -> None:
        """A handful of legacy outliers (<= grace) must NOT raise."""
        v = self._validator(mode="strict", grace=5)
        for i in range(5):
            v.check(self._swap_record(i))
        summary = v.summary()
        assert summary["ncbi_gene_id"] == 5

    def test_warn_never_raises(self) -> None:
        """Warn mode records but never aborts, even with many violations."""
        v = self._validator(mode="warn", grace=1)
        for i in range(100):
            v.check(self._swap_record(i))  # must not raise
        assert v.summary()["ncbi_gene_id"] == 100

    def test_valid_records_no_violations(self) -> None:
        v = self._validator(mode="strict", grace=0)
        for i in range(50):
            v.check({"assigned_id": f"VGNC:{i}", "ncbi_gene_id": str(i),
                     "ensembl_gene_id": f"ENSG00000{i:06d}"})
        assert v.summary() == {}

    def test_default_factory_reads_env(self, monkeypatch) -> None:
        from vgnc_download_file_generator.validation import make_validator

        monkeypatch.setenv("VGNC_VALIDATION_MODE", "warn")
        monkeypatch.setenv("VGNC_VALIDATION_GRACE", "7")
        v = make_validator()
        assert v.mode == "warn"
        assert v.grace == 7

    def test_default_factory_strict(self, monkeypatch) -> None:
        from vgnc_download_file_generator.validation import make_validator

        monkeypatch.delenv("VGNC_VALIDATION_MODE", raising=False)
        v = make_validator()
        assert v.mode == "strict"
        assert v.grace > 0
