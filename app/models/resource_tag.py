from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    UniqueConstraint
)

from app.db.database import Base


class ResourceTag(Base):
    __tablename__ = "resource_tags"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    resource_id = Column(
        Integer,
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    tag_id = Column(
        Integer,
        ForeignKey("tags.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    __table_args__ = (
        UniqueConstraint(
            "resource_id",
            "tag_id",
            name="uq_resource_tag"
        ),
    )