"""Remove teams and roles [86fa52918b54].

Revision ID: 86fa52918b54
Revises: 7500f434b71c
Create Date: 2023-11-17 15:33:56.501617

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "86fa52918b54"
down_revision = "7500f434b71c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade database schema and/or data, creating a new revision."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("role_permission")
    op.drop_table("team_role_assignment")
    op.drop_table("user_role_assignment")
    op.drop_table("team_assignment")
    op.drop_table("team")
    op.drop_table("role")
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade database schema and/or data back to the previous revision."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "role",
        sa.Column("id", sa.CHAR(length=32), nullable=False),
        sa.Column("name", sa.VARCHAR(), nullable=False),
        sa.Column("created", sa.DATETIME(), nullable=False),
        sa.Column("updated", sa.DATETIME(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "team",
        sa.Column("id", sa.CHAR(length=32), nullable=False),
        sa.Column("name", sa.VARCHAR(), nullable=False),
        sa.Column("created", sa.DATETIME(), nullable=False),
        sa.Column("updated", sa.DATETIME(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "team_assignment",
        sa.Column("user_id", sa.CHAR(length=32), nullable=False),
        sa.Column("team_id", sa.CHAR(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["team.id"],
            name="fk_team_assignment_team_id_team",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name="fk_team_assignment_user_id_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "team_id"),
    )
    op.create_table(
        "user_role_assignment",
        sa.Column("id", sa.CHAR(length=32), nullable=False),
        sa.Column("role_id", sa.CHAR(length=32), nullable=False),
        sa.Column("user_id", sa.CHAR(length=32), nullable=False),
        sa.Column("workspace_id", sa.CHAR(length=32), nullable=True),
        sa.Column("created", sa.DATETIME(), nullable=False),
        sa.Column("updated", sa.DATETIME(), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["role.id"],
            name="fk_user_role_assignment_role_id_role",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name="fk_user_role_assignment_user_id_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name="fk_user_role_assignment_workspace_id_workspace",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "team_role_assignment",
        sa.Column("id", sa.CHAR(length=32), nullable=False),
        sa.Column("role_id", sa.CHAR(length=32), nullable=False),
        sa.Column("team_id", sa.CHAR(length=32), nullable=False),
        sa.Column("workspace_id", sa.CHAR(length=32), nullable=True),
        sa.Column("created", sa.DATETIME(), nullable=False),
        sa.Column("updated", sa.DATETIME(), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["role.id"],
            name="fk_team_role_assignment_role_id_role",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["team.id"],
            name="fk_team_role_assignment_team_id_team",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name="fk_team_role_assignment_workspace_id_workspace",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "role_permission",
        sa.Column("name", sa.VARCHAR(), nullable=False),
        sa.Column("role_id", sa.CHAR(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["role.id"],
            name="fk_role_permission_role_id_role",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("name", "role_id"),
    )
    # ### end Alembic commands ###
