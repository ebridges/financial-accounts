import pytest
from unittest.mock import MagicMock
from accounts.business.management_service import ManagementService


@pytest.fixture
def management_service():
    return ManagementService(db_url="sqlite:///:memory:")


def test_reset_database(management_service):
    management_service.engine = MagicMock()
    management_service.reset_database()
    management_service.engine.execute.assert_called()
