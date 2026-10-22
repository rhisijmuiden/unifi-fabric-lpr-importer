"""api key ip allowlist and job idempotency key

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-22 23:10:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('api_keys') as batch:
        batch.add_column(sa.Column('allowed_ips', sa.JSON(), nullable=False, server_default='[]'))
    with op.batch_alter_table('jobs') as batch:
        batch.add_column(sa.Column('idempotency_key', sa.String(length=100), nullable=True))
        batch.create_index('ix_jobs_idempotency_key', ['idempotency_key'])


def downgrade() -> None:
    with op.batch_alter_table('jobs') as batch:
        batch.drop_index('ix_jobs_idempotency_key')
        batch.drop_column('idempotency_key')
    with op.batch_alter_table('api_keys') as batch:
        batch.drop_column('allowed_ips')
