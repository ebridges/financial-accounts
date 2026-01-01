# test_archive_service.py
"""Tests for Archive Service."""
import pytest
import tempfile
import os
from datetime import date

from ledger.business.archive_service import ArchiveService


class TestArchiveServicePathGeneration:
    """Tests for archive path generation."""

    @pytest.fixture
    def archive_service(self):
        return ArchiveService(base_path='test_archive')

    def test_generate_archive_path_csv(self, archive_service):
        path = archive_service.generate_archive_path(
            account_slug='checking-chase-personal-1381',
            coverage_start=date(2024, 1, 10),
            coverage_end=date(2024, 2, 8),
            extension='csv'
        )

        expected = os.path.join(
            'test_archive', '2024', 'checking-chase-personal-1381',
            '2024-01-10--2024-02-08-checking-chase-personal-1381.csv'
        )
        assert path == expected

    def test_generate_archive_path_qif(self, archive_service):
        path = archive_service.generate_archive_path(
            account_slug='checking-chase-personal-1381',
            coverage_start=date(2024, 1, 10),
            coverage_end=date(2024, 2, 8),
            extension='qif'
        )

        assert path.endswith('.qif')
        assert '2024-01-10--2024-02-08' in path

    def test_generate_pdf_path_credit_card(self, archive_service):
        path = archive_service.generate_pdf_archive_path(
            account_slug='creditcard-chase-personal-6063',
            coverage_start=date(2024, 2, 28),
            coverage_end=date(2024, 3, 28),
            is_combined_checking=False
        )

        expected = os.path.join(
            'test_archive', '2024', 'creditcard-chase-personal-6063',
            '2024-02-28--2024-03-28-creditcard-chase-personal-6063.pdf'
        )
        assert path == expected

    def test_generate_pdf_path_combined_checking(self, archive_service):
        path = archive_service.generate_pdf_archive_path(
            account_slug='checking-chase-personal-1381',
            coverage_start=date(2024, 1, 10),
            coverage_end=date(2024, 2, 8),
            is_combined_checking=True
        )

        # Should use 'checking-chase-personal' folder (no account number)
        expected = os.path.join(
            'test_archive', '2024', 'checking-chase-personal',
            '2024-01-10--2024-02-08-checking-chase-personal.pdf'
        )
        assert path == expected


class TestArchiveServiceSlugExtraction:
    """Tests for account slug extraction."""

    @pytest.fixture
    def archive_service(self):
        return ArchiveService()

    def test_extract_slug_from_checking_account(self, archive_service):
        full_name = 'Assets:Checking Accounts:checking-chase-personal-1381'
        slug = archive_service.get_account_slug_from_full_name(full_name)
        assert slug == 'checking-chase-personal-1381'

    def test_extract_slug_from_credit_card(self, archive_service):
        full_name = 'Liabilities:Credit Cards:creditcard-chase-personal-6063'
        slug = archive_service.get_account_slug_from_full_name(full_name)
        assert slug == 'creditcard-chase-personal-6063'

    def test_is_checking_account(self, archive_service):
        assert archive_service.is_checking_account('checking-chase-personal-1381') is True
        assert archive_service.is_checking_account('creditcard-chase-personal-6063') is False

    def test_is_credit_card_account(self, archive_service):
        assert archive_service.is_credit_card_account('creditcard-chase-personal-6063') is True
        assert archive_service.is_credit_card_account('checking-chase-personal-1381') is False

    def test_get_combined_checking_slug(self, archive_service):
        slug = archive_service._get_combined_checking_slug('checking-chase-personal-1381')
        assert slug == 'checking-chase-personal'

        slug = archive_service._get_combined_checking_slug('checking-chase-personal-1605')
        assert slug == 'checking-chase-personal'


class TestArchiveServiceFileCopy:
    """Tests for file archiving operations."""

    @pytest.fixture
    def temp_archive_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def source_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("test,data\n1,2\n")
            f.flush()
            yield f.name
        os.unlink(f.name)

    def test_archive_file(self, temp_archive_dir, source_file):
        service = ArchiveService(base_path=temp_archive_dir)

        archive_path = service.archive_file(
            source_path=source_file,
            account_slug='checking-chase-personal-1381',
            coverage_start=date(2024, 1, 10),
            coverage_end=date(2024, 2, 8),
        )

        assert os.path.exists(archive_path)
        assert archive_path.endswith('.csv')

        # Verify content was copied
        with open(archive_path) as f:
            content = f.read()
        assert 'test,data' in content

    def test_archive_content(self, temp_archive_dir):
        service = ArchiveService(base_path=temp_archive_dir)

        qif_content = "!Account\nNTest\n^\n"
        archive_path = service.archive_content(
            content=qif_content,
            account_slug='checking-chase-personal-1381',
            coverage_start=date(2024, 1, 10),
            coverage_end=date(2024, 2, 8),
            extension='qif'
        )

        assert os.path.exists(archive_path)
        assert archive_path.endswith('.qif')

        with open(archive_path) as f:
            content = f.read()
        assert '!Account' in content

    def test_archive_csv_with_qif(self, temp_archive_dir, source_file):
        service = ArchiveService(base_path=temp_archive_dir)

        csv_path, qif_path = service.archive_csv_with_qif(
            csv_path=source_file,
            qif_content="!Account\nNTest\n^\n",
            account_slug='checking-chase-personal-1381',
            coverage_start=date(2024, 1, 10),
            coverage_end=date(2024, 2, 8),
        )

        assert os.path.exists(csv_path)
        assert os.path.exists(qif_path)
        assert csv_path.endswith('.csv')
        assert qif_path.endswith('.qif')

