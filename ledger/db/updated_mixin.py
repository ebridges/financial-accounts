# updated_mixin.py
from datetime import datetime, timezone
from sqlalchemy import event
from sqlalchemy.orm import Session
from sqlalchemy import Column, DateTime, text


@event.listens_for(Session, "before_flush")
def update_timestamp_before_flush(session, flush_context, instances):
    """
    This event fires before SQLAlchemy flushes changes to the DB.
    We'll loop over all objects in session.new and session.dirty:
      - If they have an updated_at column, set it to now.
    """

    for obj in session.new.union(session.dirty):
        # Check if this object has our mixin or an updated_at attribute
        # Option A: Check via isinstance(obj, TimestampMixin)
        # Option B: Directly detect the updated_at attribute
        if hasattr(obj, 'updated_at'):
            # Only update it if the object is actually dirty or new
            #   (it's in session.new or session.dirty, so that's implied)
            obj.updated_at = datetime.now(timezone.utc)


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
