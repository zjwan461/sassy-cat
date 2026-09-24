"""add messages.subagent_name / messages.segments（子 agent 来源与分段）

Revision ID: 0006_message_subagent
Revises: 0005_message_error
Create Date: 2026-02-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0006_message_subagent"
down_revision: Union[str, None] = "0005_message_error"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(sa.Column("subagent_name", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("segments", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_column("segments")
        batch_op.drop_column("subagent_name")