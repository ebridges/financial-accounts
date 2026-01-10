"""Tests for AccountUri utility."""

import pytest
from datetime import date
from pathlib import Path
from ledger.util.statement_uri import AccountUri


class TestAccountUri:
    def test_from_string_valid(self):
        uri = AccountUri.from_string(
            "2023/creditcard-chase-personal-6063/2022-12-29--2023-01-28-creditcard-chase-personal-6063.pdf"
        )
        assert uri.year == 2023
        assert uri.account_slug == "creditcard-chase-personal-6063"
        assert uri.from_date == date(2022, 12, 29)
        assert uri.to_date == date(2023, 1, 28)

    def test_from_string_strips_extension(self):
        uri_pdf = AccountUri.from_string("2023/account/2023-01-01--2023-01-31-account.pdf")
        uri_json = AccountUri.from_string("2023/account/2023-01-01--2023-01-31-account.json")
        assert uri_pdf.path == uri_json.path

    def test_from_path_valid(self):
        path = Path(
            "2018/checking-chase-business-9210/2018-02-01--2018-02-28-checking-chase-business-9210"
        )
        uri = AccountUri.from_path(path)
        assert uri.year == 2018
        assert uri.account_slug == "checking-chase-business-9210"

    def test_from_components(self):
        uri = AccountUri.from_components(
            year=2024,
            account_slug="checking-chase-personal",
            from_date=date(2024, 1, 1),
            to_date=date(2024, 1, 31),
        )
        assert uri.year == 2024
        assert uri.account_slug == "checking-chase-personal"

    def test_pdf_and_json_paths(self):
        uri = AccountUri.from_string("2023/account/2023-01-01--2023-01-31-account")
        assert uri.pdf() == Path("2023/account/2023-01-01--2023-01-31-account.pdf")
        assert uri.json() == Path("2023/account/2023-01-01--2023-01-31-account.json")

    def test_invalid_path_raises(self):
        with pytest.raises(ValueError):
            AccountUri.from_string("invalid/path")

    def test_invalid_date_format_raises(self):
        with pytest.raises(ValueError):
            AccountUri.from_string("2023/account/01-01-2023--01-31-2023-account")

    def test_account_slug_mismatch_raises(self):
        with pytest.raises(ValueError):
            AccountUri.from_string("2023/account-a/2023-01-01--2023-01-31-account-b")

    def test_str_representation(self):
        uri = AccountUri.from_string("2023/account/2023-01-01--2023-01-31-account")
        assert "AccountUri" in str(uri)
