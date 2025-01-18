from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from financial_accounts.db.data_access import DAL


class BaseService:
    shared_session = None

    def __init__(self):
        pass

    def init_with_url(self, db_url):
        self.db_url = db_url
        self.engine = create_engine(db_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
        return self

    def __enter__(self):
        if not BaseService.shared_session:
            BaseService.shared_session = self.SessionLocal()
        self.data_access = DAL(session=BaseService.shared_session)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.data_access.close()
        if exc_type:
            print(f"Exception occurred: {exc_type}, {exc_value}")
        return False  # Allows exception propagation, if one was raised
