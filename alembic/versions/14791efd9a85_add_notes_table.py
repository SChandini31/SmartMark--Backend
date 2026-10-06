"""add notes table

Revision ID: 14791efd9a85
Revises: 8d47d51980e7
Create Date: 2026-10-06 10:45:17.473362

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '14791efd9a85'
down_revision: Union[str, Sequence[str], None] = '8d47d51980e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.id"],
            ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id")
    )

    op.create_index(
        "ix_notes_id",
        "notes",
        ["id"],
        unique=False
    )

    op.create_index(
        "ix_notes_user_id",
        "notes",
        ["user_id"],
        unique=False
    )

    op.create_index(
        "ix_notes_resource_id",
        "notes",
        ["resource_id"],
        unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_notes_resource_id", table_name="notes")
    op.drop_index("ix_notes_user_id", table_name="notes")
    op.drop_index("ix_notes_id", table_name="notes")
    op.drop_table("notes")
