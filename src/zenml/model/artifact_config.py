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
"""Artifact Config classes to support Model WatchTower feature."""
from typing import TYPE_CHECKING, Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, PrivateAttr, validator

from zenml import get_step_context
from zenml.exceptions import StepContextError
from zenml.logger import get_logger
from zenml.model.model_config import ModelConfig
from zenml.model.model_stages import ModelStages
from zenml.models.model_models import (
    ModelVersionArtifactFilterModel,
    ModelVersionArtifactRequestModel,
)

if TYPE_CHECKING:
    from zenml.models import ModelResponseModel, ModelVersionResponseModel

logger = get_logger(__name__)


class ArtifactConfig(BaseModel):
    """Used to link a generic Artifact to the model version."""

    model_name: Optional[str]
    model_version_name: Optional[str]
    model_stage: Optional[ModelStages]
    artifact_name: Optional[str]
    overwrite: bool = False

    _pipeline_name: str = PrivateAttr()
    _step_name: str = PrivateAttr()

    @validator("model_stage")
    def _validate_stage(
        cls, model_stage: ModelStages, values: Dict[str, Any]
    ) -> ModelStages:
        if (
            model_stage is not None
            and values.get("model_version_name", None) is not None
        ):
            raise ValueError(
                "Cannot set both `model_version_name` and `model_stage`."
            )
        return model_stage

    @property
    def _model_config(self) -> ModelConfig:
        """Property that returns the model configuration.

        Returns:
            ModelConfig: The model configuration.

        Raises:
            RuntimeError: If model configuration cannot be acquired from @step
                or @pipeline or build on the fly from fields of this class.
        """
        try:
            context = get_step_context().model_config
        except StepContextError:
            context = None
        # Check if a specific model name is provided and it doesn't match the context name
        if (
            self.model_name is not None
            and (
                self.model_version_name is not None
                or self.model_stage is not None
            )
        ) and (context is None or context.name != self.model_name):
            # Create a new ModelConfig instance with the provided model name and version
            on_the_fly_config = ModelConfig(
                name=self.model_name,
                version=self.model_version_name,
                stage=self.model_stage,
                create_new_model_version=False,
            )
            return on_the_fly_config

        if context is None:
            raise RuntimeError(
                "No model configuration found in @step or @pipeline. "
                "You can configure ModelConfig inside ArtifactConfig as well, but "
                "`model_name` and (`model_version_name` or `model_stage`) must be provided."
            )
        # Return the model from the context
        return context

    @property
    def model(self) -> "ModelResponseModel":
        """Get the `ModelResponseModel`.

        Returns:
            ModelResponseModel: The fetched or created model.
        """
        return self._model_config.get_or_create_model()

    @property
    def model_version(self) -> "ModelVersionResponseModel":
        """Get the `ModelVersionResponseModel`.

        Returns:
            ModelVersionResponseModel: The model version.
        """
        return self._model_config.get_or_create_model_version()

    def _link_to_model_version(
        self,
        artifact_uuid: UUID,
        is_model_object: bool = False,
        is_deployment: bool = False,
    ) -> None:
        """Link artifact to the model version.

        This method is used on exit from the step context to link artifact to the model version.

        Args:
            artifact_uuid: The UUID of the artifact to link.
            is_model_object: Whether the artifact is a model object. Defaults to False.
            is_deployment: Whether the artifact is a deployment. Defaults to False.
        """
        from zenml.client import Client

        # Create a ZenML client
        client = Client()

        artifact_name = self.artifact_name
        if artifact_name is None:
            artifact = client.zen_store.get_artifact(artifact_id=artifact_uuid)
            artifact_name = artifact.name

        # Create a request model for the model version artifact link
        request = ModelVersionArtifactRequestModel(
            user=client.active_user.id,
            workspace=client.active_workspace.id,
            name=artifact_name,
            artifact=artifact_uuid,
            model=self.model.id,
            model_version=self.model_version.id,
            is_model_object=is_model_object,
            is_deployment=is_deployment,
            overwrite=self.overwrite,
            pipeline_name=self._pipeline_name,
            step_name=self._step_name,
        )

        # Create the model version artifact link using the ZenML client
        existing_links = client.zen_store.list_model_version_artifact_links(
            ModelVersionArtifactFilterModel(
                user_id=client.active_user.id,
                workspace_id=client.active_workspace.id,
                name=artifact_name,
                model_id=self.model.id,
                model_version_id=self.model_version.id,
                only_artifacts=not (is_model_object or is_deployment),
                only_deployments=is_deployment,
                only_model_objects=is_model_object,
            )
        )
        if len(existing_links):
            if self.overwrite:
                # delete all model version artifact links by name
                logger.warning(
                    f"Existing artifact link(s) `{artifact_name}` found and will be deleted."
                )
                client.zen_store.delete_model_version_artifact_link(
                    model_name_or_id=self.model.id,
                    model_version_name_or_id=self.model_version.id,
                    model_version_artifact_link_name_or_id=artifact_name,
                )
            else:
                logger.info(
                    f"Artifact link `{artifact_name}` already exists, adding new version."
                )
        client.zen_store.create_model_version_artifact_link(request)

    def link_to_model(
        self,
        artifact_uuid: UUID,
    ) -> None:
        """Link artifact to the model version.

        Args:
            artifact_uuid (UUID): The UUID of the artifact to link.
        """
        self._link_to_model_version(
            artifact_uuid,
            is_model_object=False,
            is_deployment=False,
        )


class ModelArtifactConfig(ArtifactConfig):
    """Used to link a Model Object to the model version."""

    save_to_model_registry: bool = True

    def link_to_model(
        self,
        artifact_uuid: UUID,
    ) -> None:
        """Link model object to the model version.

        Args:
            artifact_uuid (UUID): The UUID of the artifact to link.
        """
        self._link_to_model_version(
            artifact_uuid,
            is_model_object=True,
            is_deployment=False,
        )


class DeploymentArtifactConfig(ArtifactConfig):
    """Used to link a Deployment to the model version."""

    def link_to_model(
        self,
        artifact_uuid: UUID,
    ) -> None:
        """Link deployment to the model version.

        Args:
            artifact_uuid (UUID): The UUID of the artifact to link.
        """
        self._link_to_model_version(
            artifact_uuid,
            is_model_object=False,
            is_deployment=True,
        )
