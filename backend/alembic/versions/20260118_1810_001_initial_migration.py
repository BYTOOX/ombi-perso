"""Initial migration: all existing models

Revision ID: 001
Revises:
Create Date: 2026-01-18 18:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables and insert default admin user."""

    # =========================================================================
    # USERS TABLE
    # =========================================================================
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=50), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
        sa.UniqueConstraint('email')
    )
    op.create_index('ix_users_username', 'users', ['username'])
    op.create_index('ix_users_email', 'users', ['email'])

    # Insert default admin user (password: 'admin')
    # Hash generated with: passlib.hash.argon2.using(rounds=4).hash("admin")
    op.execute("""
        INSERT INTO users (username, email, hashed_password, role, status, is_active, created_at)
        VALUES (
            'admin',
            'admin@plex-kiosk.local',
            '$argon2id$v=19$m=65536,t=3,p=4$oRRCaM05R+i9tzYGQIhRqg$EruT3Im0bDj7QX3MR0wLy5zJsZf0VGqSYfGLLPsKMWQ',
            'admin',
            'active',
            true,
            NOW()
        )
        ON CONFLICT (username) DO NOTHING;
    """)

    # =========================================================================
    # MEDIA REQUESTS TABLE
    # =========================================================================
    op.create_table(
        'media_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('media_type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('year', sa.Integer(), nullable=True),
        sa.Column('tmdb_id', sa.Integer(), nullable=True),
        sa.Column('imdb_id', sa.String(length=20), nullable=True),
        sa.Column('season_number', sa.Integer(), nullable=True),
        sa.Column('episode_number', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('requested_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_media_requests_user_id', 'media_requests', ['user_id'])
    op.create_index('ix_media_requests_status', 'media_requests', ['status'])
    op.create_index('ix_media_requests_tmdb_id', 'media_requests', ['tmdb_id'])

    # =========================================================================
    # DOWNLOADS TABLE
    # =========================================================================
    op.create_table(
        'downloads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.Integer(), nullable=False),
        sa.Column('torrent_hash', sa.String(length=40), nullable=False),
        sa.Column('torrent_name', sa.String(length=500), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('progress', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('download_speed', sa.Float(), nullable=True),
        sa.Column('upload_speed', sa.Float(), nullable=True),
        sa.Column('eta', sa.Integer(), nullable=True),
        sa.Column('size_total', sa.BigInteger(), nullable=True),
        sa.Column('size_downloaded', sa.BigInteger(), nullable=True),
        sa.Column('save_path', sa.String(length=500), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['request_id'], ['media_requests.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('torrent_hash')
    )
    op.create_index('ix_downloads_request_id', 'downloads', ['request_id'])
    op.create_index('ix_downloads_status', 'downloads', ['status'])
    op.create_index('ix_downloads_torrent_hash', 'downloads', ['torrent_hash'])

    # =========================================================================
    # PLEX LIBRARY ITEMS TABLE
    # =========================================================================
    op.create_table(
        'plex_library_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plex_key', sa.String(length=100), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('media_type', sa.String(length=50), nullable=False),
        sa.Column('year', sa.Integer(), nullable=True),
        sa.Column('tmdb_id', sa.Integer(), nullable=True),
        sa.Column('imdb_id', sa.String(length=20), nullable=True),
        sa.Column('library_section', sa.String(length=100), nullable=True),
        sa.Column('file_path', sa.String(length=1000), nullable=True),
        sa.Column('added_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('last_synced', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('sync_status', sa.String(length=50), nullable=False, server_default="'synced'"),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('plex_key')
    )
    op.create_index('ix_plex_library_items_plex_key', 'plex_library_items', ['plex_key'])
    op.create_index('ix_plex_library_items_media_type', 'plex_library_items', ['media_type'])
    op.create_index('ix_plex_library_items_tmdb_id', 'plex_library_items', ['tmdb_id'])

    # =========================================================================
    # RENAME SETTINGS TABLE
    # =========================================================================
    op.create_table(
        'rename_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('media_type', sa.String(length=50), nullable=False),
        sa.Column('pattern', sa.String(length=500), nullable=False),
        sa.Column('example', sa.String(length=500), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_rename_settings_media_type', 'rename_settings', ['media_type'])

    # =========================================================================
    # TITLE MAPPINGS TABLE
    # =========================================================================
    op.create_table(
        'title_mappings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('original_title', sa.String(length=255), nullable=False),
        sa.Column('french_title', sa.String(length=255), nullable=False),
        sa.Column('media_type', sa.String(length=50), nullable=True),
        sa.Column('year', sa.Integer(), nullable=True),
        sa.Column('tmdb_id', sa.Integer(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_title_mappings_original_title', 'title_mappings', ['original_title'])
    op.create_index('ix_title_mappings_french_title', 'title_mappings', ['french_title'])
    op.create_index('ix_title_mappings_tmdb_id', 'title_mappings', ['tmdb_id'])

    # =========================================================================
    # SYSTEM SETTINGS TABLE
    # =========================================================================
    op.create_table(
        'system_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('value_type', sa.String(length=50), nullable=False, server_default="'string'"),
        sa.Column('is_sensitive', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key')
    )
    op.create_index('ix_system_settings_key', 'system_settings', ['key'])

    # =========================================================================
    # TRANSFER HISTORY TABLE
    # =========================================================================
    op.create_table(
        'transfer_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.Integer(), nullable=True),
        sa.Column('source_path', sa.String(length=1000), nullable=False),
        sa.Column('destination_path', sa.String(length=1000), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('transfer_speed', sa.Float(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['request_id'], ['media_requests.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_transfer_history_request_id', 'transfer_history', ['request_id'])
    op.create_index('ix_transfer_history_status', 'transfer_history', ['status'])


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table('transfer_history')
    op.drop_table('system_settings')
    op.drop_table('title_mappings')
    op.drop_table('rename_settings')
    op.drop_table('plex_library_items')
    op.drop_table('downloads')
    op.drop_table('media_requests')
    op.drop_table('users')
