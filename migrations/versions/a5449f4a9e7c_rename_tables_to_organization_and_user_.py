"""Rename tables to organization and user_organization, add type column

Revision ID: a5449f4a9e7c
Revises: a1b2c3d4e5f6
Create Date: 2025-06-21 13:04:58.718358

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a5449f4a9e7c'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.rename_table('companies', 'organization')
    op.rename_table('usr_company', 'user_organization')
    op.add_column(
        'organization',
        sa.Column('type', sa.String(length=50), nullable=False, server_default='Company')
    )

    


def downgrade():
    op.drop_column('organization', 'type')

    # 2. Rename 'user_organization' back to 'usr_company'
    op.rename_table('user_organization', 'user_company')

    # 3. Rename 'organization' back to 'companies'
    op.rename_table('organization', 'companies')
