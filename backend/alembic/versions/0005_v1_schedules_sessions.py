"""scheduled imports and session details

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-23 00:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'import_schedules',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False, unique=True),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('protocol', sa.String(length=10), nullable=False),
        sa.Column('url', sa.String(length=1000), nullable=False, server_default=''),
        sa.Column('host', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('port', sa.Integer(), nullable=False, server_default='22'),
        sa.Column('username', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('password', sa.Text(), nullable=False, server_default=''),
        sa.Column('auth_method', sa.String(length=10), nullable=False, server_default='password'),
        sa.Column('host_key', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('remote_path', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('filename', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('ftps_implicit', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('verify_tls', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('passive', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('mapping', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('defaults', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('filter_locations', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('filter_departments', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('console_ids', sa.JSON(), nullable=True),
        sa.Column('mode', sa.String(length=10), nullable=False, server_default='upsert'),
        sa.Column('max_remove', sa.Integer(), nullable=False, server_default='25'),
        sa.Column('skip_unchanged', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('schedule', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_status', sa.String(length=20), nullable=False, server_default=''),
        sa.Column('last_message', sa.Text(), nullable=False, server_default=''),
        sa.Column('last_hash', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('last_job_id', sa.Integer(), nullable=True),
    )
    with op.batch_alter_table('user_sessions') as batch:
        batch.add_column(sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('ip_address', sa.String(length=64), nullable=False, server_default=''))
        batch.add_column(sa.Column('user_agent', sa.String(length=255), nullable=False, server_default=''))


def downgrade() -> None:
    with op.batch_alter_table('user_sessions') as batch:
        batch.drop_column('user_agent')
        batch.drop_column('ip_address')
        batch.drop_column('last_seen_at')
    op.drop_table('import_schedules')
