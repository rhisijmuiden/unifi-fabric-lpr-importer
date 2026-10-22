"""backup targets

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-22 22:40:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('backup_targets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('protocol', sa.String(length=10), nullable=False),
    sa.Column('host', sa.String(length=255), nullable=False),
    sa.Column('port', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=255), nullable=False),
    sa.Column('password', sa.Text(), nullable=False),
    sa.Column('auth_method', sa.String(length=10), nullable=False),
    sa.Column('host_key', sa.String(length=128), nullable=False),
    sa.Column('remote_path', sa.String(length=500), nullable=False),
    sa.Column('ftps_implicit', sa.Boolean(), nullable=False),
    sa.Column('verify_tls', sa.Boolean(), nullable=False),
    sa.Column('passive', sa.Boolean(), nullable=False),
    sa.Column('is_enabled', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_backup_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_backup_name', sa.String(length=100), nullable=False),
    sa.Column('last_status', sa.String(length=20), nullable=False),
    sa.Column('last_message', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )


def downgrade() -> None:
    op.drop_table('backup_targets')
