from financial_accounts.business.base_service import BaseService


class BookService(BaseService):
    def create_new_book(self, book_name):
        book = self.data_access.get_book_by_name(book_name)
        if book:
            print(f"Book '{book_name}' already exists with id={book.id}")
        else:
            book = self.data_access.create_book(book_name)

        return book

    def get_book_by_name(self, book_name):
        book = self.data_access.get_book_by_name(name=book_name)
        return book
