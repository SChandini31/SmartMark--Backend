from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Text,
    ForeignKey, 
    Boolean,
    UniqueConstraint
)
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from app.db.database import Base


class Resource(Base):
    __tablename__ = "resources"
    
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "file_hash",
            name="uq_resources_user_file_hash",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    embedding = Column(
        Vector(384),
        nullable=True
    )

    collection_id = Column(
        Integer,
        ForeignKey("collections.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    url = Column(
        Text,
        nullable=True
    )

    title = Column(
        String(500),
        nullable=True
    )

    description = Column(
        Text,
        nullable=True
    )

    resource_type = Column(
        String(50),
        nullable=True
    )

    source_domain = Column(
        String(255),
        nullable=True
    )

    preview_image = Column(
        Text,
        nullable=True
    )

    # Uploaded document metadata
    original_filename = Column(
        String(255),
        nullable=True
    )

    file_path = Column(
        Text,
        nullable=True
    )

    mime_type = Column(
        String(100),
        nullable=True
    )

    file_hash = Column(
        String(64),
        nullable=True,
        index=True,
    )

    # Extracted document content
    extracted_text = Column(
        Text,
        nullable=True
    )

    extraction_status = Column(
        String(30),
        nullable=False,
        default="pending",
        server_default="pending"
    )

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

    last_accessed_at = Column(
    DateTime(timezone=True),
    nullable=True
    )

    is_favorite = Column(
    Boolean,
    nullable=False,
    default=False,
    server_default="false"
    )