"""Drop unused active_lessons column from users

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-19 00:00:00.000000

The ``active_lessons`` column was a denormalized counter intended to track
the number of active StudyPath records per user. It was never read or
written in application code — the cap-check feature is implemented by the
``User.active_lesson_count`` property, which dynamically counts
``StudyPath`` rows with ``status='active'``. This migration drops the
orphaned column.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('active_lessons')


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('active_lessons', sa.Integer(), nullable=False, server_default='0'))