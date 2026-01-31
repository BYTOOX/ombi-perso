"""Add service_config, monitored_series, upgrade_candidate, episode_schedule, library_analysis models

Revision ID: 001_add_new_models
Revises:
Create Date: 2026-01-31 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_add_new_models'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Service Configurations
    op.create_table('service_configurations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('service_name', sa.String(50), nullable=False),
        sa.Column('display_name', sa.String(100), nullable=True),
        sa.Column('url', sa.String(500), nullable=True),
        sa.Column('username', sa.String(100), nullable=True),
        sa.Column('password_encrypted', sa.Text(), nullable=True),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('token_encrypted', sa.Text(), nullable=True),
        sa.Column('extra_config', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_health_check', sa.DateTime(), nullable=True),
        sa.Column('last_health_status', sa.String(20), nullable=True),
        sa.Column('last_health_message', sa.String(500), nullable=True),
        sa.Column('last_health_latency_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('service_name')
    )
    op.create_index('ix_service_configurations_service_name', 'service_configurations', ['service_name'])

    # Monitored Series
    op.create_table('monitored_series',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('tmdb_id', sa.Integer(), nullable=True),
        sa.Column('tvdb_id', sa.Integer(), nullable=True),
        sa.Column('anilist_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('title_fr', sa.String(500), nullable=True),
        sa.Column('year', sa.Integer(), nullable=True),
        sa.Column('poster_url', sa.String(1000), nullable=True),
        sa.Column('media_type', sa.String(50), nullable=False),
        sa.Column('monitor_type', sa.String(20), nullable=False, server_default='new_episodes'),
        sa.Column('audio_preference', sa.String(20), nullable=False, server_default='vostfr'),
        sa.Column('quality_preference', sa.String(20), nullable=False, server_default='1080p'),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('last_checked_at', sa.DateTime(), nullable=True),
        sa.Column('last_episode_season', sa.Integer(), nullable=True),
        sa.Column('last_episode_number', sa.Integer(), nullable=True),
        sa.Column('next_episode_air_date', sa.DateTime(), nullable=True),
        sa.Column('total_downloads', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('extra_config', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index('ix_monitored_series_tmdb_id', 'monitored_series', ['tmdb_id'])
    op.create_index('ix_monitored_series_user_id', 'monitored_series', ['user_id'])
    op.create_index('ix_monitored_series_status', 'monitored_series', ['status'])

    # Upgrade Candidates
    op.create_table('upgrade_candidates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plex_rating_key', sa.String(50), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('year', sa.Integer(), nullable=True),
        sa.Column('media_type', sa.String(50), nullable=False),
        sa.Column('tmdb_id', sa.Integer(), nullable=True),
        sa.Column('tvdb_id', sa.Integer(), nullable=True),
        sa.Column('current_resolution', sa.String(20), nullable=True),
        sa.Column('current_audio_language', sa.String(10), nullable=True),
        sa.Column('current_audio_codec', sa.String(50), nullable=True),
        sa.Column('target_resolution', sa.String(20), nullable=True),
        sa.Column('target_audio_language', sa.String(10), nullable=True),
        sa.Column('upgrade_reason', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('file_path', sa.String(2000), nullable=True),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('download_id', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.String(1000), nullable=True),
        sa.Column('extra_config', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['download_id'], ['downloads.id'], ondelete='SET NULL')
    )
    op.create_index('ix_upgrade_candidates_status', 'upgrade_candidates', ['status'])
    op.create_index('ix_upgrade_candidates_plex_rating_key', 'upgrade_candidates', ['plex_rating_key'])

    # Episode Release Schedule
    op.create_table('episode_release_schedules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('monitored_series_id', sa.Integer(), nullable=False),
        sa.Column('season_number', sa.Integer(), nullable=False),
        sa.Column('episode_number', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(500), nullable=True),
        sa.Column('air_date', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('download_id', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.String(1000), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_retry_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['monitored_series_id'], ['monitored_series.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['download_id'], ['downloads.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('monitored_series_id', 'season_number', 'episode_number', name='uq_episode_schedule')
    )
    op.create_index('ix_episode_release_schedules_status', 'episode_release_schedules', ['status'])
    op.create_index('ix_episode_release_schedules_air_date', 'episode_release_schedules', ['air_date'])

    # Analysis Runs
    op.create_table('analysis_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('analysis_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='running'),
        sa.Column('started_by', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('items_analyzed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('issues_found', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.String(1000), nullable=True),
        sa.Column('extra_config', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['started_by'], ['users.id'], ondelete='SET NULL')
    )
    op.create_index('ix_analysis_runs_status', 'analysis_runs', ['status'])
    op.create_index('ix_analysis_runs_analysis_type', 'analysis_runs', ['analysis_type'])

    # Library Analysis Results
    op.create_table('library_analysis_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('analysis_run_id', sa.Integer(), nullable=False),
        sa.Column('plex_rating_key', sa.String(50), nullable=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('media_type', sa.String(50), nullable=True),
        sa.Column('file_path', sa.String(2000), nullable=True),
        sa.Column('issue_type', sa.String(100), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False, server_default='info'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('suggestion', sa.Text(), nullable=True),
        sa.Column('auto_fixable', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('fixed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('fixed_at', sa.DateTime(), nullable=True),
        sa.Column('extra_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['analysis_run_id'], ['analysis_runs.id'], ondelete='CASCADE')
    )
    op.create_index('ix_library_analysis_results_analysis_run_id', 'library_analysis_results', ['analysis_run_id'])
    op.create_index('ix_library_analysis_results_severity', 'library_analysis_results', ['severity'])
    op.create_index('ix_library_analysis_results_issue_type', 'library_analysis_results', ['issue_type'])


def downgrade() -> None:
    op.drop_table('library_analysis_results')
    op.drop_table('analysis_runs')
    op.drop_table('episode_release_schedules')
    op.drop_table('upgrade_candidates')
    op.drop_table('monitored_series')
    op.drop_table('service_configurations')
