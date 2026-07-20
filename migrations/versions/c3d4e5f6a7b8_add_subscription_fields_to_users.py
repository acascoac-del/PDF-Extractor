"""add subscription fields to users

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-07-20 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('plan', sa.String(16), nullable=False, server_default='free'))
        batch_op.add_column(sa.Column('stripe_customer_id', sa.String(64), nullable=True))
        batch_op.add_column(sa.Column('stripe_subscription_id', sa.String(64), nullable=True))
        batch_op.add_column(sa.Column('subscription_status', sa.String(16), nullable=False, server_default='none'))
        batch_op.add_column(sa.Column('subscription_end_date', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('pdf_count_month', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('pdf_count_reset_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_unique_constraint('uq_users_stripe_customer_id', ['stripe_customer_id'])


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('uq_users_stripe_customer_id', type_='unique')
        batch_op.drop_column('pdf_count_reset_at')
        batch_op.drop_column('pdf_count_month')
        batch_op.drop_column('subscription_end_date')
        batch_op.drop_column('subscription_status')
        batch_op.drop_column('stripe_subscription_id')
        batch_op.drop_column('stripe_customer_id')
        batch_op.drop_column('plan')
