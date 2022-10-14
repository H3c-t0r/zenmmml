#  Copyright (c) ZenML GmbH 2020. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       https://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.
"""CLI functionality to interact with pipelines."""


import json
from datetime import datetime
from typing import Dict, cast
from uuid import UUID

import click

from zenml.cli import utils as cli_utils
from zenml.cli.cli import TagGroup, cli
from zenml.client import Client
from zenml.enums import CliCategories, ExecutionStatus
from zenml.logger import get_logger
from zenml.models.pipeline_models import (
    ArtifactModel,
    PipelineRunModel,
    StepRunModel,
)
from zenml.utils.uuid_utils import is_valid_uuid

logger = get_logger(__name__)


@cli.group(cls=TagGroup, tag=CliCategories.MANAGEMENT_TOOLS)
def pipeline() -> None:
    """List, run, or delete pipelines."""


@pipeline.command("run", help="Run a pipeline with the given configuration.")
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
)
@click.argument("python_file")
def cli_pipeline_run(python_file: str, config_path: str) -> None:
    """Runs pipeline specified by the given config YAML object.

    Args:
        python_file: Path to the python file that defines the pipeline.
        config_path: Path to configuration YAML file.
    """
    from zenml.pipelines.run_pipeline import run_pipeline

    run_pipeline(python_file=python_file, config_path=config_path)


@pipeline.command("list", help="List all registered pipelines.")
def list_pipelines() -> None:
    """List all registered pipelines."""
    cli_utils.print_active_config()
    pipelines = Client().zen_store.list_pipelines(
        project_name_or_id=Client().active_project.id
    )
    if not pipelines:
        cli_utils.declare("No piplines registered.")
        return

    cli_utils.print_pydantic_models(
        pipelines,
        exclude_columns=["id", "created", "updated", "user", "project"],
    )


@pipeline.command("delete")
@click.argument("pipeline_name_or_id", type=str, required=True)
def delete_pipeline(pipeline_name_or_id: str) -> None:
    """Delete a pipeline.

    Args:
        pipeline_name_or_id: The name or ID of the pipeline to delete.
    """
    cli_utils.print_active_config()
    active_project_id = Client().active_project.id
    assert active_project_id is not None
    try:
        client = Client()
        if is_valid_uuid(pipeline_name_or_id):
            pipeline = client.zen_store.get_pipeline(UUID(pipeline_name_or_id))
        else:
            pipeline = client.zen_store.get_pipeline_in_project(
                pipeline_name=pipeline_name_or_id,
                project_name_or_id=active_project_id,
            )
    except KeyError as err:
        cli_utils.error(str(err))
    confirmation = cli_utils.confirmation(
        f"Are you sure you want to delete pipeline `{pipeline_name_or_id}`? "
        "This will change all existing runs of this pipeline to become "
        "unlisted."
    )
    if not confirmation:
        cli_utils.declare("Pipeline deletion canceled.")
        return
    assert pipeline.id is not None
    Client().zen_store.delete_pipeline(pipeline_id=pipeline.id)
    cli_utils.declare(f"Deleted pipeline '{pipeline_name_or_id}'.")


@pipeline.group()
def runs() -> None:
    """Commands for pipeline runs."""


@click.option("--pipeline", "-p", type=str, required=False)
@click.option("--stack", "-s", type=str, required=False)
@click.option("--user", "-u", type=str, required=False)
@click.option("--unlisted", is_flag=True)
@runs.command("list", help="List all registered pipeline runs.")
def list_pipeline_runs(
    pipeline: str, stack: str, user: str, unlisted: bool = False
) -> None:
    """List all registered pipeline runs.

    Args:
        pipeline: If provided, only return runs for this pipeline.
        stack: If provided, only return runs for this stack.
        user: If provided, only return runs for this user.
        unlisted: If True, only return unlisted runs that are not
            associated with any pipeline.
    """
    cli_utils.print_active_config()
    try:
        stack_id, pipeline_id, user_id = None, None, None
        client = Client()
        if stack:
            stack_id = cli_utils.get_stack_by_id_or_name_or_prefix(
                client=client, id_or_name_or_prefix=stack
            ).id
        if pipeline:
            pipeline_id = client.get_pipeline_by_name(pipeline).id
        if user:
            user_id = client.zen_store.get_user(user).id
        pipeline_runs = Client().zen_store.list_runs(
            project_name_or_id=Client().active_project.id,
            user_name_or_id=user_id,
            pipeline_id=pipeline_id,
            stack_id=stack_id,
            unlisted=unlisted,
        )
    except KeyError as err:
        cli_utils.error(str(err))
    if not pipeline_runs:
        cli_utils.declare("No pipeline runs registered.")
        return

    cli_utils.print_pipeline_runs_table(
        client=client, pipeline_runs=pipeline_runs
    )


@runs.command("export", help="Export all pipeline runs to a YAML file.")
@click.argument("filename", type=str, required=True)
def export_pipeline_runs(filename: str) -> None:
    """Export all pipeline runs to a YAML file.

    Args:
        filename: The filename to export the pipeline runs to.
    """
    from zenml.utils.yaml_utils import write_yaml

    cli_utils.print_active_config()
    client = Client()
    pipeline_runs = client.zen_store.list_runs(
        project_name_or_id=client.active_project.id
    )
    if not pipeline_runs:
        cli_utils.error("No pipeline runs registered.")
    yaml_data = []
    for pipeline_run in pipeline_runs:
        pipeline_run.status = client.zen_store.get_run_status(pipeline_run.id)
        run_dict = json.loads(pipeline_run.json())
        run_dict["steps"] = []
        steps = client.zen_store.list_run_steps(run_id=pipeline_run.id)
        for step in steps:
            step.status = client.zen_store.get_run_step_status(step.id)
            step_dict = json.loads(step.json())
            step_dict["output_artifacts"] = []
            artifacts = client.zen_store.get_run_step_outputs(step_id=step.id)
            for artifact in sorted(artifacts.values(), key=lambda x: x.created):
                artifact_dict = json.loads(artifact.json())
                step_dict["output_artifacts"].append(artifact_dict)
            run_dict["steps"].append(step_dict)
        yaml_data.append(run_dict)
    write_yaml(filename, yaml_data)
    cli_utils.declare(f"Exported {len(yaml_data)} pipeline runs to {filename}.")


@runs.command("import", help="Import pipeline runs from a YAML file.")
@click.argument("filename", type=str, required=True)
def import_pipeline_runs(filename: str) -> None:
    """Import pipeline runs from a YAML file.

    Args:
        filename: The filename from which to import the pipeline runs.
    """
    from zenml.utils.yaml_utils import read_yaml

    cli_utils.print_active_config()
    client = Client()
    yaml_data = read_yaml(filename)
    for pipeline_run_dict in yaml_data:
        steps = pipeline_run_dict.pop("steps")
        pipeline_run = PipelineRunModel.parse_obj(pipeline_run_dict)
        pipeline_run.updated = datetime.now()
        pipeline_run.user = Client().active_user.id
        pipeline_run.project = Client().active_project.id
        pipeline_run.stack_id = None
        pipeline_run.pipeline_id = None
        pipeline_run.mlmd_id = None
        client.zen_store.create_run(pipeline_run)
        for step_dict in steps:
            artifacts = step_dict.pop("output_artifacts")
            step = StepRunModel.parse_obj(step_dict)
            step.updated = datetime.now()
            step.mlmd_id = None
            step.mlmd_parent_step_ids = []
            client.zen_store.create_run_step(step)
            for artifact_dict in artifacts:
                artifact = ArtifactModel.parse_obj(artifact_dict)
                artifact.updated = datetime.now()
                artifact.mlmd_id = None
                artifact.mlmd_parent_step_id = None
                artifact.mlmd_producer_step_id = None
                client.zen_store.create_artifact(artifact)
    cli_utils.declare(
        f"Imported {len(yaml_data)} pipeline runs from {filename}."
    )


# TODO: support MySQL migration
@runs.command("migrate", help="Migrate pipeline runs from a MySQl DB file.")
@click.argument("database", type=str, required=True)
def migrate_pipeline_runs(database: str) -> None:
    """Migrate pipeline runs from a metadata store of ZenML < 0.20.0.

    Args:
        database: The metadata store database from which to migrate the pipeline
            runs.
    """
    from tfx.dsl.compiler.constants import PIPELINE_RUN_CONTEXT_TYPE_NAME
    from tfx.orchestration import metadata

    from zenml.zen_stores.metadata_store import MetadataStore

    cli_utils.print_active_config()
    client = Client()
    mlmd_config = metadata.sqlite_metadata_connection_config(database)
    metadata_store = MetadataStore(config=mlmd_config, is_legacy=True)
    pipeline_run_contexts = metadata_store.store.get_contexts_by_type(
        PIPELINE_RUN_CONTEXT_TYPE_NAME
    )
    step_mlmd_id_mapping: Dict[int, UUID] = {}
    artifact_mlmd_id_mapping: Dict[int, UUID] = {}
    for pipeline_run_context in sorted(
        pipeline_run_contexts, key=lambda x: cast(int, x.id)
    ):
        steps = metadata_store.get_pipeline_run_steps(
            pipeline_run_context.id
        ).values()
        step_statuses = [
            metadata_store.get_step_status(step.mlmd_id) for step in steps
        ]
        num_steps = len(steps)
        pipeline_run = PipelineRunModel(
            name=pipeline_run_context.name,
            pipeline_configuration={},
            status=ExecutionStatus.run_status(step_statuses, num_steps),
            num_steps=num_steps,
            user=client.active_user.id,
            project=client.active_project.id,
        )
        new_run = client.zen_store.create_run(pipeline_run)
        for step, step_status in sorted(
            zip(steps, step_statuses), key=lambda x: x[0].mlmd_id
        ):
            parent_step_ids = [
                step_mlmd_id_mapping[mlmd_parent_step_id]
                for mlmd_parent_step_id in step.mlmd_parent_step_ids
            ]
            inputs, outputs = metadata_store.get_step_artifacts(
                step_id=step.mlmd_id,
                step_parent_step_ids=step.mlmd_parent_step_ids,
                step_name=step.name,
            )
            input_artifacts = {
                input_name: artifact_mlmd_id_mapping[mlmd_artifact.mlmd_id]
                for input_name, mlmd_artifact in inputs.items()
            }
            step_run = StepRunModel(
                name=step.name,
                pipeline_run_id=new_run.id,
                parent_step_ids=parent_step_ids,
                input_artifacts=input_artifacts,
                status=step_status,
                entrypoint_name=step.entrypoint_name,
                parameters=step.parameters,
                step_configuration={},
                mlmd_parent_step_ids=[],
            )
            new_step = client.zen_store.create_run_step(step_run)
            step_mlmd_id_mapping[step.mlmd_id] = new_step.id
            for output_name, mlmd_artifact in sorted(
                outputs.items(), key=lambda x: x[1].mlmd_id
            ):
                producer_step_id = step_mlmd_id_mapping[
                    mlmd_artifact.mlmd_producer_step_id
                ]
                artifact = ArtifactModel(
                    name=output_name,
                    parent_step_id=new_step.id,
                    producer_step_id=producer_step_id,
                    type=mlmd_artifact.type,
                    uri=mlmd_artifact.uri,
                    materializer=mlmd_artifact.materializer,
                    data_type=mlmd_artifact.data_type,
                    is_cached=mlmd_artifact.is_cached,
                )
                new_artifact = client.zen_store.create_artifact(artifact)
                artifact_mlmd_id_mapping[
                    mlmd_artifact.mlmd_id
                ] = new_artifact.id
