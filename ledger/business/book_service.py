from logging import getLogger

from ledger.business.base_service import BaseService

logger = getLogger(__name__)


class BookService(BaseService):
    def create_new_book(self, book_name):
        logger.debug(f"Looking up book '{book_name}'")
        book = self.data_access.get_book_by_name(book_name)
        if book:
            logger.info(f"Book '{book_name}' already exists (id={book.id})")
        else:
            book = self.data_access.create_book(book_name)
            logger.info(f"Created book '{book_name}' (id={book.id})")

        return book

    def get_book_by_name(self, book_name):
        logger.debug(f"Getting book by name: '{book_name}'")
        book = self.data_access.get_book_by_name(name=book_name)
        return book
