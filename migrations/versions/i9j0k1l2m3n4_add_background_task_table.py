"""Add background_task table for the navbar bell (durable cross-tab tasks)

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-09-15 00:00:00.000000

Creates the ``background_task`` table backing GET /tasks + the navbar
bell badge. Rows are keyed by the client-generated task UUID (shared with
progress_tracker) and flip running -> ready/failed with a result_url deep
link so any tab can resume after navigation.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'i9j0k1l2m3n4'
down_revision = 'h8i9j0k1l2m3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'background_task',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('task_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('pct', sa.Integer(), nullable=True),
        sa.Column('label', sa.String(length=200), nullable=True),
        sa.Column('path_id', sa.String(length=36), nullable=True),
        sa.Column('result_url', sa.String(length=500), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('read', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('background_task', schema=None) as batch_op:
        batch_op.create_index('ix_background_task_task_id', ['task_id'], unique=True)
        batch_op.create_index('ix_background_task_user_id', ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('background_task', schema=None) as batch_op:
        batch_op.drop_index('ix_background_task_user_id')
        batch_op.drop_index('ix_background_task_task_id')
    op.drop_table('background_task')
