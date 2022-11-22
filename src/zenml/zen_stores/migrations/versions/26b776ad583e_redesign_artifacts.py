"""Redesign Artifacts [26b776ad583e].

Revision ID: 26b776ad583e
Revises: 0.22.0
Create Date: 2022-11-17 08:00:24.936750

"""
from typing import TYPE_CHECKING, Dict

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy import select
from sqlalchemy.sql.expression import false, true

if TYPE_CHECKING:
    from sqlalchemy.engine.row import Row

# revision identifiers, used by Alembic.
revision = "26b776ad583e"
down_revision = "0.22.0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade database schema and/or data, creating a new revision."""
    # ----------------
    # Create new table
    # ----------------
    op.create_table(
        "step_run_output_artifact",
        sa.Column("step_run_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("artifact_id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["artifacts.id"],
            name="fk_step_run_output_artifact_artifact_id_artifacts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["step_run_id"],
            ["step_run.id"],
            name="fk_step_run_output_artifact_step_run_id_step_run",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("step_run_id", "artifact_id"),
    )

    # Add `is_cached` column to `step_run`
    with op.batch_alter_table("step_run", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_cached", sa.Boolean(), nullable=True))

    # ------------
    # Migrate data
    # ------------
    conn = op.get_bind()
    meta = sa.MetaData(bind=op.get_bind())
    meta.reflect(
        only=(
            "artifacts",
            "step_run_output_artifact",
            "step_run_input_artifact",
            "step_run",
        )
    )
    artifacts = sa.Table("artifacts", meta)
    step_run_output_artifact = sa.Table("step_run_output_artifact", meta)
    step_run_input_artifact = sa.Table("step_run_input_artifact", meta)
    step_run = sa.Table("step_run", meta, autoload_with=conn)

    # Set `is_cached` to `False` for all existing step runs
    conn.execute(step_run.update().values(is_cached=false()))
    # conn.execute(step_run.insert({"is_cached": false()}))

    # Get all artifacts that were actually produced and not cached.
    produced_artifacts = conn.execute(
        select(
            artifacts.c.id,
            artifacts.c.name,
            artifacts.c.parent_step_id,
            artifacts.c.producer_step_id,
        ).where(artifacts.c.is_cached == false())
    ).fetchall()

    # Get all cached artifacts, these are all copies of some produced artifacts.
    cached_artifacts = conn.execute(
        select(
            artifacts.c.id,
            artifacts.c.name,
            artifacts.c.parent_step_id,
            artifacts.c.producer_step_id,
        ).where(artifacts.c.is_cached == true())
    ).fetchall()

    def _find_produced_artifact(cached_artifact: "Row") -> "Row":
        """For a given cached artifact, find the original produced artifact.

        Args:
            cached_artifact: The cached artifact to find the original for.

        Returns:
            The original produced artifact.

        Raises:
            ValueError: If the original produced artifact could not be found.
        """
        for produced_artifact in produced_artifacts:
            if (
                cached_artifact.name == produced_artifact.name
                and cached_artifact.producer_step_id
                == produced_artifact.producer_step_id
            ):
                return produced_artifact
        raise ValueError("Could not find produced artifact for cached artifact")

    # For each cached artifact, find the ID of the original produced artifact
    # and link all input artifact entries to the produced artifact.
    cached_to_produced_mapping: Dict[str, str] = {}
    for cached_artifact in cached_artifacts:
        produced_artifact = _find_produced_artifact(cached_artifact)
        cached_to_produced_mapping[cached_artifact.id] = produced_artifact.id
        conn.execute(
            step_run_input_artifact.update(
                step_run_input_artifact.c.artifact_id == cached_artifact.id
            ).values({"artifact_id": produced_artifact.id})
        )

    # Delete all cached artifacts from the artifacts table
    conn.execute(artifacts.delete().where(artifacts.c.is_cached == true()))

    # Insert all produced and cached artifacts into the output artifact table
    produced_output_artifacts = [
        {
            "step_run_id": produced_artifact.parent_step_id,
            "artifact_id": produced_artifact.id,
            "name": produced_artifact.name,
            "is_cached": False,
        }
        for produced_artifact in produced_artifacts
    ]
    cached_output_artifacts = [
        {
            "step_run_id": cached_artifact.parent_step_id,
            "artifact_id": cached_to_produced_mapping[cached_artifact.id],
            "name": cached_artifact.name,
            "is_cached": True,
        }
        for cached_artifact in cached_artifacts
    ]
    output_artifacts = produced_output_artifacts + cached_output_artifacts

    if output_artifacts:
        conn.execute(step_run_output_artifact.insert().values(output_artifacts))

    # --------------
    # Adjust columns
    # --------------
    with op.batch_alter_table("artifacts", schema=None) as batch_op:

        # Add artifact store link column
        batch_op.add_column(
            sa.Column(
                "artifact_store_id", sqlmodel.sql.sqltypes.GUID(), nullable=True
            )
        )
        batch_op.create_foreign_key(
            "fk_artifacts_artifact_store_id_stack_component",
            "stack_component",
            ["artifact_store_id"],
            ["id"],
            ondelete="SET NULL",
        )

        # Drop old parent and producer step columns
        batch_op.drop_constraint(
            "fk_artifacts_producer_step_id_step_run", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_artifacts_parent_step_id_step_run", type_="foreignkey"
        )
        batch_op.drop_column("parent_step_id")
        batch_op.drop_column("producer_step_id")
        batch_op.drop_column("is_cached")
        batch_op.drop_column("mlmd_parent_step_id")
        batch_op.drop_column("mlmd_producer_step_id")

    # Rename `step_id` to `step_run_id` in `step_run_input_artifact`
    with op.batch_alter_table(
        "step_run_input_artifact", schema=None
    ) as batch_op:
        batch_op.drop_constraint(
            "fk_step_run_input_artifact_step_id_step_run", type_="foreignkey"
        )
    op.alter_column(
        "step_run_input_artifact",
        "step_id",
        new_column_name="step_run_id",
        existing_type=sqlmodel.sql.sqltypes.GUID(),
        existing_nullable=False,
    )
    with op.batch_alter_table(
        "step_run_input_artifact", schema=None
    ) as batch_op:
        batch_op.create_foreign_key(
            "fk_step_run_input_artifact_step_run_id_step_run",
            "step_run",
            ["step_run_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # Set `is_cached` column of `step_run` to not nullable
    with op.batch_alter_table("step_run", schema=None) as batch_op:
        batch_op.alter_column(
            "is_cached",
            nullable=False,
            existing_type=sa.Boolean(),
        )


def downgrade() -> None:
    """Downgrade database schema and/or data back to the previous revision."""
    with op.batch_alter_table("artifacts", schema=None) as batch_op:

        # Create old parent and producer step columns
        batch_op.add_column(
            sa.Column(
                "producer_step_id", sqlmodel.sql.sqltypes.GUID(), nullable=True
            )
        )
        batch_op.add_column(
            sa.Column(
                "parent_step_id", sqlmodel.sql.sqltypes.GUID(), nullable=True
            )
        )
        batch_op.add_column(
            sa.Column("is_cached", sa.Boolean(), nullable=False)
        )
        batch_op.add_column(
            sa.Column("mlmd_producer_step_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("mlmd_parent_step_id", sa.Integer(), nullable=True)
        )

        # Drop new artifact store link column
        batch_op.drop_constraint(
            "fk_artifacts_artifact_store_id_stack_component", type_="foreignkey"
        )
        batch_op.drop_column("artifact_store_id")

    # Migrate data
    # TODO

    with op.batch_alter_table("artifacts", schema=None) as batch_op:

        # Change producer step and parent step to not nullable
        batch_op.alter_column(
            "producer_step_id",
            existing_type=sa.CHAR(length=32),
            nullable=False,
        )
        batch_op.alter_column(
            "parent_step_id",
            existing_type=sa.CHAR(length=32),
            nullable=False,
        )

        # Add foreign key constraints back
        batch_op.create_foreign_key(
            "fk_artifacts_parent_step_id_step_run",
            "step_run",
            ["parent_step_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_artifacts_producer_step_id_step_run",
            "step_run",
            ["producer_step_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # Rename `step_run_id` back to `step_id` in `step_run_input_artifact`
    with op.batch_alter_table(
        "step_run_input_artifact", schema=None
    ) as batch_op:
        batch_op.drop_constraint(
            "fk_step_run_input_artifact_step_run_id_step_run",
            type_="foreignkey",
        )
    op.alter_column(
        "step_run_input_artifact",
        "step_run_id",
        new_column_name="step_id",
        existing_type=sqlmodel.sql.sqltypes.GUID(),
        existing_nullable=False,
    )
    with op.batch_alter_table(
        "step_run_input_artifact", schema=None
    ) as batch_op:
        batch_op.create_foreign_key(
            "fk_step_run_input_artifact_step_id_step_run",
            "step_run",
            ["step_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # Drop `is_cached` column from `step_run`
    with op.batch_alter_table("step_run", schema=None) as batch_op:
        batch_op.drop_column("is_cached")

    # Drop new table
    op.drop_table("step_run_output_artifact")
