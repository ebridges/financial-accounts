from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from financial_accounts.db.data_access import DAL


class BaseService:
    def __init__(self):
        self.session = None
        self.data_access = None

    def init_with_url(self, db_url):
        self.db_url = db_url
        self.engine = create_engine(db_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
        return self

    def __enter__(self):
        # Create a fresh session for this context
        self.session = self.SessionLocal()
        self.data_access = DAL(session=self.session)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if exc_type:
                # Rollback on any exception
                if self.session:
                    self.session.rollback()
                print(f"Exception occurred: {exc_type}, {exc_value}")
            else:
                # Commit successful operations
                if self.session:
                    self.session.commit()
            
            # Always close the session
            if self.data_access:
                self.data_access.close()
        except Exception as cleanup_error:
            print(f"Error during session cleanup: {cleanup_error}")
        finally:
            # Ensure session is cleared
            self.session = None
            self.data_access = None
            
        return False  # Allow exception propagation
