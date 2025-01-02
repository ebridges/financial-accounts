from sqlalchemy import create_engine

from financial_accounts.db.models import Base


class ManagementService:
    def init_with_url(self, db_url):
        self.engine = create_engine(db_url, echo=False)
        return self

    # for testing purposes
    def init_with_engine(self, engine):
        self.engine = engine
        return self

    def reset_database(self):
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
