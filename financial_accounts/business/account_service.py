from financial_accounts.business.base_service import BaseService


class AccountService(BaseService):
    def list_accounts_in_book(self, book_name):
        book = self.data_access.get_book_by_name(book_name)
        if not book:
            print(f"No book found named '{book_name}'.")
            return 1
        accounts = self.data_access.list_accounts_for_book(book.id)
        return accounts

    def add_account(
        self,
        book_name,
        parent_name,
        acct_name,
        acct_code,
        acct_type,
        description,
        hidden,
        placeholder,
    ):
        book = self.data_access.get_book_by_name(book_name)
        if not book:
            raise Exception(f"No book found named '{book_name}'.")

        parent_id = None
        if parent_name:
            parent_acct = self.data_access.get_account_by_name_for_book(book.id, parent_name)
            if not parent_acct:
                raise Exception(f"Parent account named '{parent_name}' not found.")
            parent_id = parent_acct.id

        new_acct = self.data_access.create_account(
            book_id=book.id,
            name=acct_name,
            code=acct_code,
            acct_type=acct_type,
            description=description,
            hidden=hidden,
            placeholder=placeholder,
            parent_account_id=parent_id,
        )
        return new_acct
