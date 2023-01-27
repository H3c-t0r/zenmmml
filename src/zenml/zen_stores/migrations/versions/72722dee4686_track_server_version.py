"""Track server version [72722dee4686].

Revision ID: 72722dee4686
Revises: 3944116bbd56
Create Date: 2023-01-26 11:52:42.765022

"""
import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision = "72722dee4686"
down_revision = "3944116bbd56"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade database schema and/or data, creating a new revision."""
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("pipeline_run", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "server_version",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=True,
            )
        )
        batch_op.alter_column(
            column_name="zenml_version",
            new_column_name="client_version",
            existing_type=sa.VARCHAR(),
        )

    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade database schema and/or data back to the previous revision."""
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("pipeline_run", schema=None) as batch_op:
        batch_op.drop_column("server_version")
        batch_op.alter_column(
            column_name="client_version",
            new_column_name="zenml_version",
            existing_type=sa.VARCHAR(),
        )

    # ### end Alembic commands ###
