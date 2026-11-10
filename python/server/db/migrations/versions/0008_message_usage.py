"""add messages.model / messages.duration_ms（用量面板按模型/耗时统计）

Revision ID: 0008_message_usage
Revises: 0007_conversation_pin
Create Date: 2026-03-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_message_usage"
down_revision: Union[str, None] = "0007_conversation_pin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(sa.Column("model", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("duration_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_column("duration_ms")
        batch_op.drop_column("model")
