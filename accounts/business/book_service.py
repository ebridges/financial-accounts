from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from accounts.db.data_access import DAL


class BookService:
    def __init__(self, db_url):
        self.engine = create_engine(db_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def __enter__(self):
        self.session = self.SessionLocal()
        self.data_access = DAL(session=self.session)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.data_access.close()

    def create_new_book(self, book_name):
        book = self.data_access.get_book_by_name(book_name)
        if book:
            print(f"Book '{book_name}' already exists with id={book.id}")
        else:
            book = self.data_access.create_book(book_name)

        return book
