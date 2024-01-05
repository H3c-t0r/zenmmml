"""Add name column to input artifact PK [728c6369cfaa].

Revision ID: 728c6369cfaa
Revises: 0.36.0
Create Date: 2023-03-20 13:37:51.215760

"""
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "728c6369cfaa"
down_revision = "0.36.0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade database schema and/or data, creating a new revision.

    Raises:
        NotImplementedError: If the database engine is not SQLite or MySQL.
    """
    # ### commands auto generated by Alembic - please adjust! ###
    _disable_primary_key_requirement_if_necessary()

    engine_name = op.get_bind().engine.name
    if engine_name == "sqlite":
        constraint_name = "pk_step_run_input_artifact"
    elif engine_name == "mysql":
        constraint_name = "PRIMARY"
    else:
        raise NotImplementedError(f"Unsupported engine: {engine_name}")

    with op.batch_alter_table(
        "step_run_input_artifact",
        schema=None,
        naming_convention={"pk": "pk_%(table_name)s"},
    ) as batch_op:
        # Need to first drop the foreign keys as otherwise the table renaming
        # used during the PK constraint drop/create doesn't work
        batch_op.drop_constraint(
            constraint_name="fk_step_run_input_artifact_step_id_step_run",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            constraint_name="fk_step_run_input_artifact_artifact_id_artifact",
            type_="foreignkey",
        )

        # Update the PK
        batch_op.drop_constraint(
            constraint_name=constraint_name, type_="primary"
        )
        batch_op.create_primary_key(
            constraint_name="pk_step_run_input_artifact",
            columns=["step_id", "artifact_id", "name"],
        )

        # Re-add the foreign keys
        batch_op.create_foreign_key(
            constraint_name="fk_step_run_input_artifact_step_id_step_run",
            referent_table="step_run",
            local_cols=["step_id"],
            remote_cols=["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            constraint_name="fk_step_run_input_artifact_artifact_id_artifact",
            referent_table="artifact",
            local_cols=["artifact_id"],
            remote_cols=["id"],
            ondelete="CASCADE",
        )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade database schema and/or data back to the previous revision."""
    # ### commands auto generated by Alembic - please adjust! ###

    _disable_primary_key_requirement_if_necessary()

    with op.batch_alter_table(
        "step_run_input_artifact",
        schema=None,
    ) as batch_op:
        # Need to first drop the foreign keys as otherwise the table renaming
        # used during the PK constraint drop/create doesn't work
        batch_op.drop_constraint(
            constraint_name="fk_step_run_input_artifact_step_id_step_run",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            constraint_name="fk_step_run_input_artifact_artifact_id_artifact",
            type_="foreignkey",
        )

        # Update the PK
        batch_op.drop_constraint(
            constraint_name="pk_step_run_input_artifact", type_="primary"
        )
        batch_op.create_primary_key(
            constraint_name="pk_step_run_input_artifact",
            columns=["step_id", "artifact_id"],
        )

        # Re-add the foreign keys
        batch_op.create_foreign_key(
            constraint_name="fk_step_run_input_artifact_step_id_step_run",
            referent_table="step_run",
            local_cols=["step_id"],
            remote_cols=["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            constraint_name="fk_step_run_input_artifact_artifact_id_artifact",
            referent_table="artifact",
            local_cols=["artifact_id"],
            remote_cols=["id"],
            ondelete="CASCADE",
        )

    # ### end Alembic commands ###


def _disable_primary_key_requirement_if_necessary() -> None:
    """Adjusts settings based on database engine requirements."""
    engine = op.get_bind().engine
    engine_name = engine.name
    server_version_info = engine.dialect.server_version_info

    if engine_name == "mysql" and server_version_info >= (8, 0, 13):
        potential_session_var = engine.execute(
            text('SHOW SESSION VARIABLES LIKE "sql_require_primary_key";')
        ).fetchone()
        if potential_session_var and potential_session_var[1] == "ON":
            # Temporarily disable this MySQL setting for primary key modification
            op.execute("SET SESSION sql_require_primary_key = 0;")
    elif engine_name == "mariadb":
        # MariaDB does not require a similar setting, so skip this step
        pass
    else:
        raise NotImplementedError(f"Unsupported engine: {engine_name}")
