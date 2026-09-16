"""Add external web-suggestion columns to suggestion table

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-09-16 00:00:00.000000

Adds ``is_external`` (bool) + ``source_urls`` (JSON list as TEXT) so
web suggestions (verbatim URLs from /api/web_search) persist alongside
internal document-grounded rows. Existing rows read as internal.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'j0k1l2m3n4o5'
down_revision = 'i9j0k1l2m3n4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('suggestion', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_external', sa.Boolean(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('source_urls', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('suggestion', schema=None) as batch_op:
        batch_op.drop_column('source_urls')
        batch_op.drop_column('is_external')
