"""Add workflow step and action models for request pipeline tracking

Revision ID: 002_add_workflow_models
Revises: 001_add_new_models
Create Date: 2026-02-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002_add_workflow_models'
down_revision: Union[str, None] = '001_add_new_models'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # RequestWorkflowStep table
    op.create_table('request_workflow_steps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.Integer(), nullable=False),
        sa.Column('step_key', sa.String(30), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('last_error_code', sa.String(50), nullable=True),
        sa.Column('last_error_message', sa.Text(), nullable=True),
        sa.Column('artifacts_json', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['request_id'], ['media_requests.id'], ondelete='CASCADE')
    )
    op.create_index('ix_request_workflow_steps_request_id', 'request_workflow_steps', ['request_id'])
    op.create_index('ix_workflow_steps_request_status', 'request_workflow_steps', ['request_id', 'status'])
    op.create_index('ix_workflow_steps_step_key', 'request_workflow_steps', ['step_key'])

    # RequestAction table
    op.create_table('request_actions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.Integer(), nullable=False),
        sa.Column('workflow_step_id', sa.Integer(), nullable=True),
        sa.Column('action_type', sa.String(30), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='open'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('payload_json', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('resolution_json', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_by_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['request_id'], ['media_requests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workflow_step_id'], ['request_workflow_steps.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['resolved_by_id'], ['users.id'], ondelete='SET NULL')
    )
    op.create_index('ix_request_actions_request_id', 'request_actions', ['request_id'])
    op.create_index('ix_request_actions_workflow_step_id', 'request_actions', ['workflow_step_id'])
    op.create_index('ix_request_actions_status', 'request_actions', ['status'])
    op.create_index('ix_request_actions_type_status', 'request_actions', ['action_type', 'status'])


def downgrade() -> None:
    op.drop_table('request_actions')
    op.drop_table('request_workflow_steps')
