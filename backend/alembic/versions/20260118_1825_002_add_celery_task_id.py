"""Add celery_task_id to media_requests

Revision ID: 002
Revises: 001
Create Date: 2026-01-18 18:25:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add celery_task_id column for Celery task tracking."""
    op.add_column(
        'media_requests',
        sa.Column('celery_task_id', sa.String(length=100), nullable=True)
    )
    op.create_index(
        'ix_media_requests_celery_task_id',
        'media_requests',
        ['celery_task_id']
    )


def downgrade() -> None:
    """Remove celery_task_id column."""
    op.drop_index('ix_media_requests_celery_task_id', table_name='media_requests')
    op.drop_column('media_requests', 'celery_task_id')
