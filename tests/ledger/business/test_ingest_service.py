# test_ingest_service.py
"""Tests for Ingest Service."""
import pytest
import tempfile
import os
from unittest.mock import MagicMock, patch

from ledger.business.ingest_service import IngestService, IngestResult, IngestReport


class TestIngestServiceFileHash:
    """Tests for file hash computation."""

    def test_compute_file_hash_same_content(self):
        """Same content should produce same hash."""
        content = "test content for hashing"

        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f1:
            f1.write(content)
            f1.flush()
            path1 = f1.name

        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f2:
            f2.write(content)
            f2.flush()
            path2 = f2.name

        try:
            hash1 = IngestService._compute_file_hash(path1)
            hash2 = IngestService._compute_file_hash(path2)
            assert hash1 == hash2
            assert len(hash1) == 64  # SHA-256 hex length
        finally:
            os.unlink(path1)
            os.unlink(path2)

    def test_compute_file_hash_different_content(self):
        """Different content should produce different hash."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f1:
            f1.write("content one")
            f1.flush()
            path1 = f1.name

        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f2:
            f2.write("content two")
            f2.flush()
            path2 = f2.name

        try:
            hash1 = IngestService._compute_file_hash(path1)
            hash2 = IngestService._compute_file_hash(path2)
            assert hash1 != hash2
        finally:
            os.unlink(path1)
            os.unlink(path2)


class TestIngestReport:
    """Tests for IngestReport dataclass."""

    def test_imported_report(self):
        report = IngestReport(
            result=IngestResult.IMPORTED,
            import_file_id=1,
            transactions_imported=10,
            message='Success'
        )

        assert report.result == IngestResult.IMPORTED
        assert report.transactions_imported == 10
        assert report.import_file_id == 1

    def test_skipped_duplicate_report(self):
        report = IngestReport(
            result=IngestResult.SKIPPED_DUPLICATE,
            import_file_id=5,
            message='Already imported'
        )

        assert report.result == IngestResult.SKIPPED_DUPLICATE
        assert report.transactions_imported == 0

    def test_hash_mismatch_report(self):
        report = IngestReport(
            result=IngestResult.HASH_MISMATCH,
            import_file_id=3,
            message='Different hash'
        )

        assert report.result == IngestResult.HASH_MISMATCH


class TestIngestServiceIdempotency:
    """Tests for file-level idempotency behavior."""

    @pytest.fixture
    def qif_content(self):
        return """!Account
NTest:Account
TBank
^
!Type:Bank
D01/15/2024
PTEST TRANSACTION
T-100.00
LExpenses:Uncategorized
^
"""

    def test_skip_duplicate_same_hash(self, mock_ctx, qif_content):
        """Same file (by hash) should be skipped."""
        # Setup default account lookup
        mock_ctx.accounts.lookup_by_name.return_value = MagicMock(id=1, full_name='Test:Account')
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.qif', delete=False) as f:
            f.write(qif_content)
            f.flush()
            qif_path = f.name

        try:
            file_hash = IngestService._compute_file_hash(qif_path)

            # Mock existing import with same hash
            mock_existing = MagicMock()
            mock_existing.id = 5
            mock_existing.file_hash = file_hash  # Same hash
            mock_ctx.dal.get_import_file_by_scope.return_value = mock_existing

            service = IngestService(mock_ctx)
            report = service.ingest_qif(file_path=qif_path)

            assert report.result == IngestResult.SKIPPED_DUPLICATE
            assert report.import_file_id == 5
            # Verify no transactions were inserted
            mock_ctx.transactions.insert.assert_not_called()
        finally:
            os.unlink(qif_path)

    def test_hash_mismatch_different_hash(self, mock_ctx, qif_content):
        """Same filename but different hash should report mismatch."""
        # Setup default account lookup
        mock_ctx.accounts.lookup_by_name.return_value = MagicMock(id=1, full_name='Test:Account')
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.qif', delete=False) as f:
            f.write(qif_content)
            f.flush()
            qif_path = f.name

        try:
            # Mock existing import with different hash
            mock_existing = MagicMock()
            mock_existing.id = 5
            mock_existing.file_hash = 'different_hash_value'
            mock_ctx.dal.get_import_file_by_scope.return_value = mock_existing

            service = IngestService(mock_ctx)
            report = service.ingest_qif(file_path=qif_path)

            assert report.result == IngestResult.HASH_MISMATCH
            assert report.import_file_id == 5
        finally:
            os.unlink(qif_path)

    def test_new_file_imported(self, mock_ctx, qif_content):
        """New file should be imported successfully."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.qif', delete=False) as f:
            f.write(qif_content)
            f.flush()
            qif_path = f.name

        try:
            # No existing import
            mock_ctx.dal.get_import_file_by_scope.return_value = None

            # Mock import file creation
            mock_import_file = MagicMock()
            mock_import_file.id = 10
            mock_ctx.dal.create_import_file.return_value = mock_import_file

            # Mock account lookups
            def mock_lookup_by_name(name):
                if name == 'Test:Account':
                    return MagicMock(id=1, full_name='Test:Account')
                elif name == 'Expenses:Uncategorized':
                    return MagicMock(id=2, full_name='Expenses:Uncategorized')
                raise Exception(f"Account not found: {name}")
            
            mock_ctx.accounts.lookup_by_name.side_effect = mock_lookup_by_name

            service = IngestService(mock_ctx)
            report = service.ingest_qif(file_path=qif_path)

            assert report.result == IngestResult.IMPORTED
            assert report.import_file_id == 10
            mock_ctx.dal.create_import_file.assert_called_once()
            # Verify transaction was inserted via TransactionService
            mock_ctx.transactions.insert.assert_called_once()
        finally:
            os.unlink(qif_path)


class TestIngestServiceErrors:
    """Tests for error handling."""

    def test_account_not_found(self, mock_ctx):
        """Should raise error if account not found."""
        mock_ctx.accounts.lookup_by_name.side_effect = Exception("Account not found")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.qif', delete=False) as f:
            f.write("!Account\nNNonexistent:Account\n^\n")
            f.flush()
            qif_path = f.name

        try:
            service = IngestService(mock_ctx)

            with pytest.raises(ValueError, match="Account 'Nonexistent:Account' not found"):
                service.ingest_qif(qif_path)
        finally:
            os.unlink(qif_path)

    def test_qif_without_account_info(self, mock_ctx):
        """Should raise error if QIF has no account info."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.qif', delete=False) as f:
            f.write("!Type:Bank\nD01/15/2024\nPTest\nT-100\n^\n")
            f.flush()
            qif_path = f.name

        try:
            service = IngestService(mock_ctx)

            with pytest.raises(ValueError, match="does not contain account information"):
                service.ingest_qif(qif_path)
        finally:
            os.unlink(qif_path)
