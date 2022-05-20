# Original License:
# Copyright 2019 Google LLC. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# New License:
#  Copyright (c) ZenML GmbH 2021. All Rights Reserved.
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

import os
from typing import TYPE_CHECKING, Any, ClassVar, Dict, List, Optional

import kfp
from google.cloud import aiplatform
from kfp import dsl
from kfp.compiler import Compiler as KFPCompiler
from kfp.v2.compiler import Compiler as KFPV2Compiler

from zenml.enums import StackComponentType
from zenml.integrations.kubeflow.orchestrators.kubeflow_entrypoint_configuration import (
    METADATA_UI_PATH_OPTION,
    KubeflowEntrypointConfiguration,
)
from zenml.integrations.vertex import VERTEX_ORCHESTRATOR_FLAVOR
from zenml.io import fileio
from zenml.io.utils import get_global_config_directory
from zenml.logger import get_logger
from zenml.orchestrators.base_orchestrator import BaseOrchestrator
from zenml.repository import Repository
from zenml.stack.stack_validator import StackValidator
from zenml.utils.docker_utils import get_image_digest
from zenml.utils.source_utils import get_source_root_path
import re

if TYPE_CHECKING:
    from tfx.proto.orchestration.pipeline_pb2 import Pipeline as Pb2Pipeline

    from zenml.pipelines.base_pipeline import BasePipeline
    from zenml.runtime_configuration import RuntimeConfiguration
    from zenml.stack import Stack
    from zenml.steps import BaseStep


logger = get_logger(__name__)


def _clean_pipeline_name(pipeline_name: str) -> str:
    """Clean pipeline name to be a valid Vertex AI Pipeline name.

    Arguments:
        pipeline_name: pipeline name to be cleaned.

    Returns:
        Cleaned pipeline name.
    """
    return pipeline_name.replace("_", "-").lower()


class VertexOrchestrator(BaseOrchestrator):
    """Orchestrator responsible for running pipelines on Vertex AI.

    Attributes:
        region: the name of GCP region where the pipeline job will be executed.
            Vertex AI Pipelines is available in the following regions: https://cloud.google.com/vertex-ai/docs/general/locations#feature-availability
        project: GCP project name. If `None`, the project will be inferred from
            the environment.
        customer_managed_encryption_key:
        base_image:
    """

    region: str
    pipeline_root: str
    project: Optional[str] = None
    customer_managed_encryption_key: Optional[str] = None

    base_image: Optional[str] = None

    FLAVOR: ClassVar[str] = VERTEX_ORCHESTRATOR_FLAVOR

    @property
    def validator(self) -> Optional[StackValidator]:
        """Validates that the stack contains a container registry."""

        return StackValidator(
            required_components={StackComponentType.CONTAINER_REGISTRY}
        )

    def get_docker_image_name(self, pipeline_name: str) -> str:
        """Returns the full docker image name including registry and tag."""

        base_image_name = f"zenml-vertex:{pipeline_name}"
        container_registry = Repository().active_stack.container_registry

        if container_registry:
            registry_uri = container_registry.uri.rstrip("/")
            return f"{registry_uri}/{base_image_name}"

        return base_image_name

    @property
    def root_directory(self) -> str:
        """Returns path to the root directory for all files concerning this orchestrator."""
        return os.path.join(
            get_global_config_directory(), "kubeflow", str(self.uuid)
        )

    @property
    def pipeline_directory(self) -> str:
        """Returns path to a directory in which the kubeflow pipelines files are
        stored."""
        return os.path.join(self.root_directory, "pipelines")

    def prepare_pipeline_deployment(
        self,
        pipeline: "BasePipeline",
        stack: "Stack",
        runtime_configuration: "RuntimeConfiguration",
    ) -> None:
        """Build a Docker image for the current environment and uploads it to a
        container registry if configured."""
        from zenml.utils import docker_utils

        repo = Repository()
        container_registry = repo.active_stack.container_registry

        if not container_registry:
            raise RuntimeError("Missing container registry")

        image_name = self.get_docker_image_name(pipeline.name)

        requirements = {*stack.requirements(), *pipeline.requirements}

        logger.debug(
            "Vertex AI Pipelines service docker container requirements %s",
            requirements,
        )

        docker_utils.build_docker_image(
            build_context_path=get_source_root_path(),
            image_name=image_name,
            dockerignore_path=pipeline.dockerignore_file,
            requirements=requirements,
            base_image=self.base_image,
        )
        container_registry.push_image(image_name)

    def prepare_or_run_pipeline(
        self,
        sorted_steps: List["BaseStep"],
        pipeline: "BasePipeline",
        pb2_pipeline: "Pb2Pipeline",
        stack: "Stack",
        runtime_configuration: "RuntimeConfiguration",
    ) -> Any:
        """Creates a KFP JSON pipeline as intermediary representation of the pipeline
        which is then deployed to Vertex AI Pipelines service.

        How it works:
        -------------
        Before this method is called the `prepare_pipeline_deployment()` method
        builds a Docker image that contains the code for the pipeline, all steps
        the context around these files.

        Based on this Docker image a callable is created which builds container_ops
        for each step (`_construct_kfp_pipeline`). The function `kfp.components.load_component_from_text`
        is used to create the `ContainerOp`, because using the `dsl.ContainerOp`
        class directly is deprecated when using the Kubeflow SDK v2. The step
        entrypoint command with the entrypoint arguments is the command that will
        be executed by the container created using the previously created Docker
        image.

        This callable is then compiled into a JSON file that is used as the intermediary
        representation of the Kubeflow pipeline.

        This file then is submited to the Vertex AI Pipelines service for execution.
        """

        image_name = self.get_docker_image_name(pipeline.name)
        image_name = get_image_digest(image_name) or image_name

        def _construct_kfp_pipeline() -> None:
            step_name_to_container_op: Dict[str, dsl.ContainerOp] = {}

            for step in sorted_steps:
                # The command will be needed to eventually call the python step
                # within the docker container
                command = (
                    KubeflowEntrypointConfiguration.get_entrypoint_command()
                )

                # The arguments are passed to configure the entrypoint of the
                # docker container when the step is called.
                metadata_ui_path = "/outputs/mlpipeline-ui-metadata.json"
                arguments = (
                    KubeflowEntrypointConfiguration.get_entrypoint_arguments(
                        step=step,
                        pb2_pipeline=pb2_pipeline,
                        **{METADATA_UI_PATH_OPTION: metadata_ui_path},
                    )
                )

                # Create the container op for the step
                container_op = kfp.components.load_component_from_text(
                    f"""
                    name: {step.name}
                    implementation:
                        container:
                            image: {image_name}
                            command: {command + arguments}"""
                )()

                upstream_step_names = self.get_upstream_step_names(
                    step=step, pb2_pipeline=pb2_pipeline
                )
                for upstream_step_name in upstream_step_names:
                    upstream_container_op = step_name_to_container_op[
                        upstream_step_name
                    ]
                    container_op.after(upstream_container_op)

                step_name_to_container_op[step.name] = container_op

        # Save the generated pipeline to a file.
        assert runtime_configuration.run_name
        fileio.makedirs(self.pipeline_directory)
        pipeline_file_path = os.path.join(
            self.pipeline_directory,
            f"{runtime_configuration.run_name}.json",
        )

        # Compile the pipeline using the Kubeflow SDK V2 compiler that allows
        # to generate a JSON representation of the pipeline that can be later
        # upload to Vertex AI Pipelines service.
        logger.debug(
            "Compiling pipeline using Kubeflow SDK V2 compiler and saving it to %s",
            pipeline_file_path,
        )
        KFPV2Compiler().compile(
            pipeline_func=_construct_kfp_pipeline,
            package_path=pipeline_file_path,
            pipeline_name=_clean_pipeline_name(pipeline.name),
        )

        # Using the Google Cloud AIPlatform client, upload and execute the pipeline
        # on the Vertex AI Pipelines service.
        self._upload_and_run_pipeline(
            pipeline_name=pipeline.name,
            pipeline_file_path=pipeline_file_path,
            runtime_configuration=runtime_configuration,
            enable_cache=pipeline.enable_cache,
        )

    def _upload_and_run_pipeline(
        self,
        pipeline_name: str,
        pipeline_file_path: str,
        runtime_configuration: "RuntimeConfiguration",
        enable_cache: bool,
    ) -> None:
        """Uploads and run the pipeline on the Vertex AI Pipelines service.

        Args:
            pipeline_name: Name of the pipeline.
            pipeline_file_path: Path of the JSON file containing the compiled
                Kubeflow pipeline (compiled with Kubeflow SDK v2).
            runtime_configuration: Runtime configuration of the pipeline run.
            enable_cache: Whether caching is enabled for this pipeline run.
        """

        # We have to replace the hyphens in the pipeline name with underscores
        # and lower case the string, because the Vertex AI Pipelines service
        # requires this format.
        job_id = _clean_pipeline_name(runtime_configuration.run_name)

        # Instantiate the Vertex AI Pipelines job
        run = aiplatform.PipelineJob(
            display_name=pipeline_name,
            template_path=pipeline_file_path,
            job_id=job_id,
            pipeline_root=self.pipeline_root,
            parameter_values=None,
            enable_caching=enable_cache,
            encryption_spec_key_name=self.customer_managed_encryption_key,
            labels=None,
            credentials=None,
            project=self.project,
            location=self.region,
        )

        logger.info(
            "Submitting pipeline job '%s' to Vertex AI Pipelines service",
            job_id,
        )

        # Submit the job to Vertex AI Pipelines service.
        run.submit()
