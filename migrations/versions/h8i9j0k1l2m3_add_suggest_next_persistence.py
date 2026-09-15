"""Add suggest-next persistence: StudyPath snapshot columns + suggestion table

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-09-15 00:00:00.000000

Adds three durable snapshot columns to ``study_paths`` (``modules_json``,
``summary_text``, ``relevance_json``) so post-generation features can reason
about the study plan after session data expires and ``extracted_texts`` /
``content_digest`` are cleared. Unlike those columns, the snapshot is NEVER
cleared.

Also creates the ``suggestion`` table backing the suggest-next card on the
lessons page (pending/accepted/dismissed/completed per user + path).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'h8i9j0k1l2m3'
down_revision = 'g7h8i9j0k1l2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('study_paths', schema=None) as batch_op:
        batch_op.add_column(sa.Column('modules_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('summary_text', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('relevance_json', sa.Text(), nullable=True))
    op.create_table(
        'suggestion',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('study_path_id', sa.String(length=36), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('source_refs', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['study_path_id'], ['study_paths.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('suggestion', schema=None) as batch_op:
        batch_op.create_index('ix_suggestion_user_id', ['user_id'], unique=False)
        batch_op.create_index('ix_suggestion_study_path_id', ['study_path_id'], unique=False)


def downgrade():
    with op.batch_alter_table('suggestion', schema=None) as batch_op:
        batch_op.drop_index('ix_suggestion_study_path_id')
        batch_op.drop_index('ix_suggestion_user_id')
    op.drop_table('suggestion')
    with op.batch_alter_table('study_paths', schema=None) as batch_op:
        batch_op.drop_column('relevance_json')
        batch_op.drop_column('summary_text')
        batch_op.drop_column('modules_json')
