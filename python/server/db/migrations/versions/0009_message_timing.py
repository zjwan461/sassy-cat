"""add messages.ttft_ms / messages.decode_ms（首 token 延迟与解码耗时）

Revision ID: 0009_message_timing
Revises: 0008_message_usage
Create Date: 2026-03-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_message_timing"
down_revision: Union[str, None] = "0008_message_usage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(sa.Column("ttft_ms", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("decode_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_column("decode_ms")
        batch_op.drop_column("ttft_ms")
