"""Drop unused ocr_text column from content_registry

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-19 00:01:00.000000

The ``ocr_text`` column was a write-only field: ``vision_parser.py``
stored OCR output there via ``register_content()``, but no code path
ever read it back from a queried ``ContentRegistry`` row. All consumers
(``rag_retriever.py``, ``processing.py``, ``vision_parser.py``) read
``extracted_text`` only, which already contains the combined usable
text. This migration drops the orphaned column and removes the
``ocr_text`` parameter from ``register_content()``.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('content_registry', schema=None) as batch_op:
        batch_op.drop_column('ocr_text')


def downgrade():
    with op.batch_alter_table('content_registry', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ocr_text', sa.Text(), nullable=True))