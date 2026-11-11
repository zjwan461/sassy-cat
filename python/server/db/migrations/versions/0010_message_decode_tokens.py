"""add messages.decode_tokens（一轮内各解码步骤的输出 token 合计）

Revision ID: 0010_message_decode_tokens
Revises: 0009_message_timing
Create Date: 2026-03-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_message_decode_tokens"
down_revision: Union[str, None] = "0009_message_timing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(sa.Column("decode_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_column("decode_tokens")
