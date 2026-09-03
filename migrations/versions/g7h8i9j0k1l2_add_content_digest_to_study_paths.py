"""Add content_digest to StudyPath

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-03 00:00:00.000000

Adds a ``content_digest`` Text column to ``study_paths``.  It stores the
full-coverage map-reduce digest produced at processing time (every extracted
chunk summarized in reading order) so lesson generation can ground the LLM
in the entire document without re-running the expensive map step.  The
column is cleared after lesson generation, mirroring the lifecycle of
``extracted_texts``.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'g7h8i9j0k1l2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('study_paths', schema=None) as batch_op:
        batch_op.add_column(sa.Column('content_digest', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('study_paths', schema=None) as batch_op:
        batch_op.drop_column('content_digest')
