"""add kb_documents.file_path

Revision ID: 0003_kb_doc_file_path
Revises: 0002_system_meta
Create Date: 2026-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_kb_doc_file_path"
down_revision: Union[str, None] = "0002_system_meta"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("kb_documents") as batch_op:
        batch_op.add_column(sa.Column("file_path", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("kb_documents") as batch_op:
        batch_op.drop_column("file_path")
