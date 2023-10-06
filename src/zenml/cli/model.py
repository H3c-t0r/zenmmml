#  Copyright (c) ZenML GmbH 2023. All Rights Reserved.
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
"""CLI functionality to interact with Model WatchTower."""
# from functools import partial
from typing import Any, List, Optional

import click

# from uuid import UUID
# import click
from zenml.cli import utils as cli_utils
from zenml.cli.cli import TagGroup, cli
from zenml.client import Client
from zenml.enums import CliCategories, ModelStages
from zenml.logger import get_logger
from zenml.models.model_models import (
    ModelFilterModel,
    ModelRequestModel,
    ModelVersionArtifactFilterModel,
    ModelVersionFilterModel,
    ModelVersionPipelineRunFilterModel,
    ModelVersionUpdateModel,
)

# from zenml.utils.pagination_utils import depaginate

logger = get_logger(__name__)


@cli.group(cls=TagGroup, tag=CliCategories.MODEL_WATCHTOWER)
def model() -> None:
    """List, create or delete models in the Model WatchTower."""


@cli_utils.list_options(ModelFilterModel)
@model.command("list", help="List all models.")
def list_models(**kwargs: Any) -> None:
    """List all models.

    Args:
        **kwargs: Keyword arguments to filter models.
    """
    models = Client().list_models(ModelFilterModel(**kwargs))

    if not models:
        cli_utils.declare("No models found.")
        return

    cli_utils.print_pydantic_models(
        models,
        exclude_columns=["user", "workspace"],
        suppress_active_column=True,
    )


@model.command("register", help="Create a model.")
@click.option(
    "--name",
    "-n",
    help="The name of the model.",
    type=str,
    required=True,
)
@click.option(
    "--license",
    "-l",
    help="The license under which the model is created.",
    type=str,
    required=False,
)
@click.option(
    "--description",
    "-d",
    help="The description of the model.",
    type=str,
    required=False,
)
@click.option(
    "--audience",
    "-a",
    help="The target audience for the model.",
    type=str,
    required=False,
)
@click.option(
    "--use-cases",
    "-u",
    help="The use cases of the model.",
    type=str,
    required=False,
)
@click.option(
    "--tradeoffs",
    help="The tradeoffs of the model.",
    type=str,
    required=False,
)
@click.option(
    "--ethical",
    "-e",
    help="The ethical implications of the model.",
    type=str,
    required=False,
)
@click.option(
    "--limitations",
    help="The known limitations of the model.",
    type=str,
    required=False,
)
@click.option(
    "--tag",
    "-t",
    help="Tags associated with the model.",
    type=str,
    required=False,
    multiple=True,
)
def create_model(
    name: str,
    license: Optional[str],
    description: Optional[str],
    audience: Optional[str],
    use_cases: Optional[str],
    tradeoffs: Optional[str],
    ethical: Optional[str],
    limitations: Optional[str],
    tag: Optional[List[str]],
) -> None:
    """Create a model.

    Args:
        name: The name of the model.
        license: The license model created under.
        description: The description of the model.
        audience: The target audience of the model.
        use_cases: The use cases of the model.
        tradeoffs: The tradeoffs of the model.
        ethical: The ethical implications of the model.
        limitations: The know limitations of the model.
        tag: Tags associated with the model.
    """
    model = Client().create_model(
        ModelRequestModel(
            name=name,
            license=license,
            description=description,
            audience=audience,
            use_cases=use_cases,
            tradeoffs=tradeoffs,
            ethic=ethical,
            limitations=limitations,
            tags=tag,
            user=Client().active_user.id,
            workspace=Client().active_workspace.id,
        )
    )

    cli_utils.print_pydantic_models(
        [
            model,
        ],
        exclude_columns=["user", "workspace"],
        suppress_active_column=True,
    )


@model.command("delete", help="Delete a model.")
@click.argument("model_name_or_id")
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Don't ask for confirmation.",
)
def delete_model(
    model_name_or_id: str,
    yes: bool = False,
) -> None:
    """Delete a model.

    Args:
        model_name_or_id: The ID or name of the model to delete.
        yes: If set, don't ask for confirmation.
    """
    if not yes:
        confirmation = cli_utils.confirmation(
            f"Are you sure you want to delete model '{model_name_or_id}'?"
        )
        if not confirmation:
            cli_utils.declare("Model deletion canceled.")
            return

    try:
        Client().delete_model(
            model_name_or_id=model_name_or_id,
        )
    except (KeyError, ValueError) as e:
        cli_utils.error(str(e))
    else:
        cli_utils.declare(f"Model '{model_name_or_id}' deleted.")


@model.group
def version() -> None:
    """List or view model versions in the Model Watchtower."""


@cli_utils.list_options(ModelVersionFilterModel)
@click.argument("model_name_or_id")
@version.command("list", help="List all model versions.")
def list_model_versions(model_name_or_id: str, **kwargs: Any) -> None:
    """List all model versions.

    Args:
        model_name_or_id: The ID or name of the model containing version.
        **kwargs: Keyword arguments to filter models.
    """
    model_id = Client().get_model(model_name_or_id=model_name_or_id).id
    model_versions = Client().list_model_versions(
        ModelVersionFilterModel(model_id=model_id, **kwargs)
    )

    if not model_versions:
        cli_utils.declare("No model versions found.")
        return

    cli_utils.print_pydantic_models(
        model_versions,
        columns=[
            "id",
            "name",
            "number",
            "description",
            "stage",
            "artifact_objects_count",
            "model_objects_count",
            "deployments_count",
            "pipeline_runs_count",
            "updated",
        ],
        suppress_active_column=True,
    )


@version.command("update", help="Update model version stage.")
@click.argument("model_name_or_id")
@click.argument("model_version_name_or_number_or_id")
@click.option(
    "--stage",
    "-s",
    type=click.Choice(ModelStages),
    help="The stage of the model version.",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Don't ask for confirmation, if stage already occupied.",
)
def update_model_version(
    model_name_or_id: str,
    model_version_name_or_number_or_id: str,
    stage: str,
    force: bool = False,
) -> None:
    """Update model version stage.

    Args:
        model_name_or_id: The ID or name of the model containing version.
        model_version_name_or_number_or_id: The ID, number or name of the model version.
        stage: The stage of the model version to be set.
        force: Whether existing model version in target stage should be silently archived.
    """
    model_version = Client().get_model_version(
        model_name_or_id=model_name_or_id,
        model_version_name_or_number_or_id=model_version_name_or_number_or_id,
    )
    try:
        Client().update_model_version(
            model_version_id=model_version.id,
            model_version_update_model=ModelVersionUpdateModel(
                model=model_version.model.id, stage=stage, force=force
            ),
        )
    except RuntimeError:
        if not force:
            cli_utils.print_pydantic_models(
                Client().list_model_versions(
                    ModelVersionFilterModel(
                        stage=stage,
                        model_id=model_version.model.id,
                    )
                ),
                columns=[
                    "id",
                    "name",
                    "number",
                    "description",
                    "stage",
                    "artifact_objects_count",
                    "model_objects_count",
                    "deployments_count",
                    "pipeline_runs_count",
                    "updated",
                ],
                suppress_active_column=True,
            )
            confirmation = cli_utils.confirmation(
                f"Are you sure you want to promote model version to '{stage}'? "
                "This stage is already taken by another model version and if you "
                "will proceed the current model version in this stage will be "
                "archived."
            )
            if not confirmation:
                cli_utils.declare("Model version stage update canceled.")
                return
            Client().update_model_version(
                model_version_id=model_version.id,
                model_version_update_model=ModelVersionUpdateModel(
                    model=model_version.model.id, stage=stage, force=True
                ),
            )
    cli_utils.declare(
        f"Model version '{model_version.name}' stage updated to '{stage}'."
    )


@version.group
def artifact() -> None:
    """List artifacts related to model versions in the Model WatchTower."""


@artifact.command("list", help="List all artifacts of a model version.")
@click.argument("model_name_or_id")
@click.argument("model_version_name_or_number_or_id")
@click.option(
    "--only-artifacts",
    "-a",
    is_flag=True,
    default=False,
    help="Show only artifact objects.",
)
@click.option(
    "--only-model-objects",
    "-m",
    is_flag=True,
    default=False,
    help="Show only model objects.",
)
@click.option(
    "--only-deployments",
    "-d",
    is_flag=True,
    default=False,
    help="Show only deployments.",
)
@cli_utils.list_options(ModelVersionArtifactFilterModel)
def list_model_version_artifacts(
    model_name_or_id: str,
    model_version_name_or_number_or_id: str,
    only_artifacts: bool,
    only_model_objects: bool,
    only_deployments: bool,
    **kwargs: Any,
) -> None:
    """List all artifacts of a model version.

    Args:
        model_name_or_id: The ID or name of the model containing version.
        model_version_name_or_number_or_id: The name, number or ID of the model version.
        only_artifacts: Show only artifact objects.
        only_model_objects: Show only model objects.
        only_deployments: Show only deployments.
        **kwargs: Keyword arguments to filter models.
    """
    if sum([only_artifacts, only_model_objects, only_deployments]) > 1:
        cli_utils.declare(
            "Only one of --only-artifacts, --only-model-objects, or --only-deployments can be set."
        )
        return

    model_version = Client().get_model_version(
        model_name_or_id=model_name_or_id,
        model_version_name_or_number_or_id=model_version_name_or_number_or_id,
    )

    if (
        (
            not model_version.artifact_object_ids
            and not model_version.model_object_ids
            and not model_version.deployment_ids
        )
        or (only_artifacts and not model_version.artifact_object_ids)
        or (only_model_objects and not model_version.model_object_ids)
        or (only_deployments and not model_version.deployment_ids)
    ):
        cli_utils.declare("No artifacts attached to model version found.")
        return

    for (
        title,
        _only_artifacts,
        _only_model_objects,
        _only_deployments,
        condition,
    ) in [
        [
            "Artifacts",
            True,
            False,
            False,
            model_version.artifact_object_ids
            and not (only_model_objects or only_deployments),
        ],
        [
            "Model objects",
            False,
            True,
            False,
            model_version.model_object_ids
            and not (only_artifacts or only_deployments),
        ],
        [
            "Deployments",
            False,
            False,
            True,
            model_version.deployment_ids
            and not (only_artifacts or only_model_objects),
        ],
    ]:
        if condition:
            links = Client().list_model_version_artifact_links(
                ModelVersionArtifactFilterModel(
                    model_id=model_version.model.id,
                    model_version_id=model_version.id,
                    only_artifacts=_only_artifacts,
                    only_model_objects=_only_model_objects,
                    only_deployments=_only_deployments,
                    **kwargs,
                )
            )

            cli_utils.title(title)
            cli_utils.print_pydantic_models(
                links,
                columns=[
                    "pipeline_name",
                    "step_name",
                    "name",
                    "link_version",
                    "artifact",
                    "created",
                ],
                suppress_active_column=True,
            )


@version.group
def run() -> None:
    """List pipeline runs related to model versions in the Model Watchtower."""


@run.command("list", help="List all pipeline runs of a model version.")
@click.argument("model_name_or_id")
@click.argument("model_version_name_or_number_or_id")
@cli_utils.list_options(ModelVersionPipelineRunFilterModel)
def list_model_version_pipeline_runs(
    model_name_or_id: str,
    model_version_name_or_number_or_id: str,
    **kwargs: Any,
) -> None:
    """List all artifacts of a model version.

    Args:
        model_name_or_id: The ID or name of the model containing version.
        model_version_name_or_number_or_id: The name, number or ID of the model version.
        **kwargs: Keyword arguments to filter models.
    """
    model_version = Client().get_model_version(
        model_name_or_id=model_name_or_id,
        model_version_name_or_number_or_id=model_version_name_or_number_or_id,
    )

    if not model_version.pipeline_run_ids:
        cli_utils.declare("No pipeline runs attached to model version found.")
        return

    links = Client().list_model_version_pipeline_run_links(
        ModelVersionPipelineRunFilterModel(
            model_id=model_version.model.id,
            model_version_id=model_version.id,
            **kwargs,
        )
    )

    cli_utils.print_pydantic_models(
        links,
        columns=[
            "name",
            "pipeline_run",
            "created",
        ],
        suppress_active_column=True,
    )
