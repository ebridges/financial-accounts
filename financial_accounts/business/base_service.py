from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from financial_accounts.db.data_access import DAL


class BaseService:
    def __init__(self, db_url):
        self.engine = create_engine(db_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def __enter__(self):
        self.session = self.SessionLocal()
        self.data_access = DAL(session=self.session)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.data_access.close()
        if exc_type:
            print(f"Exception occurred: {exc_type}, {exc_value}")
        return False  # Allows exception propagation, if one was raised
