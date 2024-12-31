from sqlalchemy import create_engine

from accounts.db.models import Base


class ManagementService:
    def __init__(self, db_url):
        self.engine = create_engine(db_url, echo=False)

    def reset_database(self):
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
