"""Remove shared columns [7500f434b71c].

Revision ID: 7500f434b71c
Revises: 0.45.1
Create Date: 2023-10-16 15:15:34.865337

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "7500f434b71c"
down_revision = "0.45.1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade database schema and/or data, creating a new revision."""
    # ### commands auto generated by Alembic - please adjust! ###

    with op.batch_alter_table("service_connector", schema=None) as batch_op:
        batch_op.drop_column("is_shared")

    with op.batch_alter_table("stack", schema=None) as batch_op:
        batch_op.drop_column("is_shared")

    with op.batch_alter_table("stack_component", schema=None) as batch_op:
        batch_op.drop_column("is_shared")

    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade database schema and/or data back to the previous revision."""
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("stack_component", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_shared", sa.BOOLEAN(), nullable=False)
        )

    with op.batch_alter_table("stack", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_shared", sa.BOOLEAN(), nullable=False)
        )

    with op.batch_alter_table("service_connector", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_shared", sa.BOOLEAN(), nullable=False)
        )
    # ### end Alembic commands ###
