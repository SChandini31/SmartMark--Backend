from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Text,
    ForeignKey
)
from sqlalchemy.sql import func

from app.db.database import Base


class Resource(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    collection_id = Column(
    Integer,
    ForeignKey("collections.id", ondelete="SET NULL"),
    nullable=True,
    index=True
   )
   
    url = Column(Text, nullable=False)

    title = Column(String(500), nullable=True)

    description = Column(Text, nullable=True)

    resource_type = Column(String(50), nullable=True)

    source_domain = Column(String(255), nullable=True)

    preview_image = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )