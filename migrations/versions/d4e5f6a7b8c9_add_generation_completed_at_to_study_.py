"""Add generation_completed_at to StudyPath

Revision ID: d4e5f6a7b8c9
Revises: 7477e6809a28
Create Date: 2026-06-16 22:00:00.000000

Adds a ``generation_completed_at`` DateTime column to ``study_paths``. It
is the canonical "navigate now" signal for the JS client: the request
handler sets it synchronously for TTS-disabled generations, and the
background TTS worker sets it in its finally block for TTS-enabled
generations. The JS polls ``/lessons/generation-status`` (which reads
this column via the StudyPath model) and redirects when the column is
non-NULL.

Replaces the previous cache-based ``data.done`` signal (via
``progress_tracker.mark_done()``), which suffered from a race condition
when the TTS worker and the request handler shared the same
progress_tracker key.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = '7477e6809a28'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('study_paths', schema=None) as batch_op:
        batch_op.add_column(sa.Column('generation_completed_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('study_paths', schema=None) as batch_op:
        batch_op.drop_column('generation_completed_at')
