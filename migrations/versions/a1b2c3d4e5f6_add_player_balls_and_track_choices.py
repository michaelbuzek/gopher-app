"""Add player_balls and player_track_choices tables

Additive migration — creates two new tables only.
No existing tables are modified or dropped.

Revision ID: a1b2c3d4e5f6
Revises: 0b7ef4750c8c
Create Date: 2026-05-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'a1b2c3d4e5f6'
down_revision = '0b7ef4750c8c'
branch_labels = None
depends_on = None


def _has_table(name):
    bind = op.get_bind()
    return inspect(bind).has_table(name)


def upgrade():
    if not _has_table('player_balls'):
        op.create_table(
            'player_balls',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('player_name', sa.String(length=100), nullable=False),
            sa.Column('label', sa.String(length=100), nullable=False),
            sa.Column('color_hex', sa.String(length=9), nullable=True),
            sa.Column('image_filename', sa.String(length=200), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('player_name', 'label', name='uq_player_ball_label'),
        )
        op.create_index('idx_player_ball_player', 'player_balls', ['player_name'])

    if not _has_table('player_track_choices'):
        op.create_table(
            'player_track_choices',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('place_id', sa.Integer(), nullable=False),
            sa.Column('track_number', sa.Integer(), nullable=False),
            sa.Column('player_name', sa.String(length=100), nullable=False),
            sa.Column('ball_id', sa.Integer(), nullable=True),
            sa.Column('note', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['place_id'], ['places.id']),
            sa.ForeignKeyConstraint(['ball_id'], ['player_balls.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(
            'idx_choice_lookup',
            'player_track_choices',
            ['place_id', 'track_number', 'player_name', 'created_at'],
        )


def downgrade():
    # Reversal drops the new tables. Existing app tables are NOT touched.
    if _has_table('player_track_choices'):
        op.drop_index('idx_choice_lookup', table_name='player_track_choices')
        op.drop_table('player_track_choices')
    if _has_table('player_balls'):
        op.drop_index('idx_player_ball_player', table_name='player_balls')
        op.drop_table('player_balls')
