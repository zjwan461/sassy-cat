"""add conversations.pinned / conversations.pinned_at（会话置顶）

Revision ID: 0007_conversation_pin
Revises: 0006_message_subagent
Create Date: 2026-02-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0007_conversation_pin"
down_revision: Union[str, None] = "0006_message_subagent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 存量会话一律视为未置顶：pinned 默认 0，pinned_at 保持 NULL
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.add_column(
            sa.Column("pinned", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("pinned_at", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_column("pinned_at")
        batch_op.drop_column("pinned")