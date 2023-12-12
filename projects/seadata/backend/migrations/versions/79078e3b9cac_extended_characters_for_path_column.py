"""extended characters for path column

Revision ID: 79078e3b9cac
Revises: bebf004b2b35
Create Date: 2023-12-12 09:29:32.708305

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "79078e3b9cac"
down_revision = "bebf004b2b35"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("data_object", schema=None) as batch_op:
        batch_op.alter_column(
            "path",
            existing_type=sa.VARCHAR(length=100),
            type_=sa.String(length=400),
            existing_nullable=False,
        )

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("data_object", schema=None) as batch_op:
        batch_op.alter_column(
            "path",
            existing_type=sa.String(length=400),
            type_=sa.VARCHAR(length=100),
            existing_nullable=False,
        )

    # ### end Alembic commands ###
