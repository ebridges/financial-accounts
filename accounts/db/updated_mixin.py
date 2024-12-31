# updated_mixin.py
from sqlalchemy import Column, DateTime, text


class UpdatedAtMixin:
    """
    Mixin to give SQLAlchemy models an updated_at column,
    which we'll update via an ORM event before flush.
    """

    updated_at = Column(
        DateTime,
        server_default=text("CURRENT_TIMESTAMP"),  # Sets a default on insert
        nullable=False,
    )
