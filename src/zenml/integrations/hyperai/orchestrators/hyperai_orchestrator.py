#  Copyright (c) ZenML GmbH 2022. All Rights Reserved.
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
"""Implementation of the ZenML HyperAI orchestrator."""

import copy
import json
import os
import tempfile
import sys
import time
from typing import TYPE_CHECKING, Any, Dict, Optional, Type, Union, cast
from uuid import uuid4
import yaml

from pydantic import validator

from zenml.config.base_settings import BaseSettings
from zenml.config.global_config import GlobalConfiguration
from zenml.constants import (
    ENV_ZENML_LOCAL_STORES_PATH,
)
from zenml.entrypoints import StepEntrypointConfiguration
from zenml.enums import StackComponentType
from zenml.integrations.hyperai import (
    HYPERAI_RESOURCE_TYPE
)
from zenml.logger import get_logger
from zenml.models import ServiceConnectorRequirements
from zenml.orchestrators import (
    BaseOrchestratorConfig,
    BaseOrchestratorFlavor,
    ContainerizedOrchestrator,
)
from zenml.stack import Stack, StackValidator
from zenml.utils import string_utils

if TYPE_CHECKING:
    from zenml.models import PipelineDeploymentResponse

logger = get_logger(__name__)

ENV_ZENML_HYPERAI_RUN_ID = "ZENML_HYPERAI_ORCHESTRATOR_RUN_ID"


class HyperAIOrchestrator(ContainerizedOrchestrator):
    """Orchestrator responsible for running pipelines on HyperAI instances.
    """

    @property
    def config(self) -> HyperAIOrchestratorConfig:
        """Returns the `HyperAIOrchestratorConfig` config.

        Returns:
            The configuration.
        """
        return cast(HyperAIOrchestratorConfig, self._config)

    @property
    def settings_class(self) -> Optional[Type["BaseSettings"]]:
        """Settings class for the HyperAI orchestrator.

        Returns:
            The settings class.
        """
        return HyperAIOrchestratorSettings

    @property
    def validator(self) -> Optional[StackValidator]:
        """Ensures there is an image builder in the stack.

        Returns:
            A `StackValidator` instance.
        """
        return StackValidator(
            required_components={
                StackComponentType.CONTAINER_REGISTRY,
                StackComponentType.IMAGE_BUILDER,
            }
        )

    def get_orchestrator_run_id(self) -> str:
        """Returns the active orchestrator run id.

        Raises:
            RuntimeError: If the environment variable specifying the run id
                is not set.

        Returns:
            The orchestrator run id.
        """
        try:
            return os.environ[ENV_ZENML_HYPERAI_RUN_ID]
        except KeyError:
            raise RuntimeError(
                "Unable to read run id from environment variable "
                f"{ENV_ZENML_HYPERAI_RUN_ID}."
            )

    def prepare_or_run_pipeline(
        self,
        deployment: "PipelineDeploymentResponse",
        stack: "Stack",
        environment: Dict[str, str],
    ) -> Any:
        """Sequentially runs all pipeline steps in Docker containers on a HyperAI instance
        orchestrated via Docker Compose.

        Assumes that:
        - A HyperAI (hyperai.ai) instance is running on the configured IP address.
        - The HyperAI instance has been configured to allow SSH connections from the
            machine running the pipeline.
        - Docker and Docker Compose are installed on the HyperAI instance.
        - A key pair has been generated and the public key has been added to the
            HyperAI instance's `authorized_keys` file.
        - The private key is available in a HyperAI service connector linked to this
            orchestrator.

        Args:
            deployment: The pipeline deployment to prepare or run.
            stack: The stack the pipeline will run on.
            environment: Environment variables to set in the orchestration
                environment.

        Raises:
            RuntimeError: If a step fails.
        """
        if deployment.schedule:
            logger.warning(
                "HyperAI orchestrator currently does not support the"
                "use of schedules. The `schedule` will be ignored "
                "and the pipeline will be run immediately."
            )

        # Basic Docker Compose definition
        compose_definition = {
            "version": "3",
            "services": {}
        }

        # Add each step as a service to the Docker Compose definition
        dependency = None
        for step_name, step in deployment.step_configurations.items():

            # Get image
            image = self.get_image(deployment=deployment, step_name=step_name)

            # Get settings
            step_settings = cast(
                HyperAIOrchestratorSettings, self.get_settings(step)
            )

            # Make Compose service definition for step
            compose_definition["services"][step_name] = {
                "image": image,
                "container_name": step_name,
                "entrypoint": StepEntrypointConfiguration.get_entrypoint_command(),
                "command": StepEntrypointConfiguration.get_entrypoint_arguments(
                    step_name=step_name, deployment_id=deployment.id
                ),
                "environment": environment,
                "volumes": [
                    f"{mount_from}:{mount_to}"
                    for mount_from, mount_to in step_settings.mounts_from_to.items()
                ]
            }

            # Add dependency on previous step if it exists
            if dependency:
                compose_definition["services"][step_name]["depends_on"] = {
                    dependency: {
                        "condition": "service_completed_successfully"
                    }
                }

            # Set current step as dependency for next step
            dependency = step_name

        # Can we add multi dependency?

        # Convert into yaml
        compose_definition = yaml.dump(compose_definition)

        # Connect to configured HyperAI instance
        paramiko_client: paramiko.SSHClient
        if connector := self.get_connector():
            paramiko_client = connector.connect()
            if not isinstance(paramiko_client, paramiko.SSHClient):
                raise RuntimeError(
                    f"Expected to receive a `paramiko.SSHClient` object from the "
                    f"linked connector, but got type `{type(paramiko_client)}`."
                )
        else:
            raise RuntimeError(
                "You must link a HyperAI service connector to the orchestrator."
            )

        # Set up pipeline-runs directory if it doesn't exist
        directory_name = "/home/zenml/pipeline-runs"
        stdin, stdout, stderr = paramiko_client.exec_command(
            f"mkdir -p {directory_name}"
        )

        # Get pipeline run id and create directory for it
        orchestrator_run_id = self.get_orchestrator_run_id()
        directory_name = f"{directory_name}/{orchestrator_run_id}"
        stdin, stdout, stderr = paramiko_client.exec_command(
            f"mkdir -p {directory_name}"
        )
        
        # Create temporary file and write Docker Compose file to it
        with tempfile.NamedTemporaryFile(mode="w", delete=True, delete_on_close=False) as f:

            # Write Docker Compose file to temporary file
            with f.file as f_:
                f_.write(compose_definition)

            # Scp Docker Compose file to HyperAI instance
            scp_client = paramiko_client.open_sftp()
            scp_client.put(
                f.name,
                f"{directory_name}/docker-compose.yaml"
            )
            scp_client.close()

        # Run Docker Compose file
        stdin, stdout, stderr = paramiko_client.exec_command(
            f"cd {directory_name} && docker compose up"
        )


class HyperAIOrchestratorSettings(BaseSettings):
    """HyperAI orchestrator settings.

    Attributes:
        mounts_from_to: A dictionary mapping from paths on the HyperAI instance
            to paths within the Docker container. This allows users to mount
            directories from the HyperAI instance into the Docker container that runs
            on it.
    """

    mounts_from_to: Dict[str, str] = {}


class HyperAIOrchestratorConfig(  # type: ignore[misc] # https://github.com/pydantic/pydantic/issues/4173
    BaseOrchestratorConfig, HyperAIOrchestratorSettings
):
    """HyperAI orchestrator config."""

    @property
    def is_remote(self) -> bool:
        """Checks if this stack component is running remotely.

        This designation is used to determine if the stack component can be
        used with a local ZenML database or if it requires a remote ZenML
        server.

        Returns:
            True if this config is for a remote component, False otherwise.
        """
        return True


class HyperAIOrchestratorFlavor(BaseOrchestratorFlavor):
    """Flavor for the HyperAI orchestrator."""

    @property
    def name(self) -> str:
        """Name of the orchestrator flavor.

        Returns:
            Name of the orchestrator flavor.
        """
        return "hyperai"

    @property
    def service_connector_requirements(
        self,
    ) -> Optional[ServiceConnectorRequirements]:
        """Service connector resource requirements for service connectors.

        Specifies resource requirements that are used to filter the available
        service connector types that are compatible with this flavor.

        Returns:
            Requirements for compatible service connectors, if a service
            connector is required for this flavor.
        """
        return ServiceConnectorRequirements(resource_type=HYPERAI_RESOURCE_TYPE)

    @property
    def docs_url(self) -> Optional[str]:
        """A url to point at docs explaining this flavor.

        Returns:
            A flavor docs url.
        """
        return self.generate_default_docs_url()

    @property
    def sdk_docs_url(self) -> Optional[str]:
        """A url to point at SDK docs explaining this flavor.

        Returns:
            A flavor SDK docs url.
        """
        return self.generate_default_sdk_docs_url()

    @property
    def logo_url(self) -> str:
        """A url to represent the flavor in the dashboard.

        Returns:
            The flavor logo.
        """
        return "https://public-flavor-logos.s3.eu-central-1.amazonaws.com/connectors/hyperai/hyperai.png"

    @property
    def config_class(self) -> Type[BaseOrchestratorConfig]:
        """Config class for the base orchestrator flavor.

        Returns:
            The config class.
        """
        return HyperAIOrchestratorConfig

    @property
    def implementation_class(self) -> Type["HyperAIOrchestrator"]:
        """Implementation class for this flavor.

        Returns:
            Implementation class for this flavor.
        """
        return HyperAIOrchestrator
