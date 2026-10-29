
"""add document support to resources

Revision ID: 59daae132033
Revises: 4d75d74bf837
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "59daae132033"
down_revision: Union[str, Sequence[str], None] = "4d75d74bf837"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "resources",
        "url",
        existing_type=sa.Text(),
        nullable=True,
    )

    op.add_column(
        "resources",
        sa.Column("original_filename", sa.String(255), nullable=True),
    )

    op.add_column(
        "resources",
        sa.Column("file_path", sa.Text(), nullable=True),
    )

    op.add_column(
        "resources",
        sa.Column("mime_type", sa.String(100), nullable=True),
    )

    op.add_column(
        "resources",
        sa.Column("extracted_text", sa.Text(), nullable=True),
    )

    op.add_column(
        "resources",
        sa.Column(
            "extraction_status",
            sa.String(30),
            server_default="pending",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("resources", "extraction_status")
    op.drop_column("resources", "extracted_text")
    op.drop_column("resources", "mime_type")
    op.drop_column("resources", "file_path")
    op.drop_column("resources", "original_filename")

    op.alter_column(
        "resources",
        "url",
        existing_type=sa.Text(),
        nullable=False,
    )
