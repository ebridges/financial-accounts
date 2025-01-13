def test_get_transactions_in_range(transaction_service):
    transaction_service.data_access.get_transactions_in_range.return_value = [
        MagicMock(id=1),
        MagicMock(id=2),
    ]

    transactions = transaction_service.get_transactions_in_range(
        book_id=1,
        start_date="2023-01-01",
        end_date="2023-12-31"
    )
    assert len(transactions) == 2
    assert transactions[0].id == 1
    assert transactions[1].id == 2
