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
import json
import os
import subprocess
from typing import (
    ClassVar, List, Optional, Union,
    TYPE_CHECKING, Sequence
)

from pydantic import validator

from zenml.integrations.spark import SPARK_KUBERNETES_STEP_OPERATOR
from zenml.io.fileio import copy
from zenml.logger import get_logger
from zenml.repository import Repository
from zenml.runtime_configuration import RuntimeConfiguration
from zenml.step_operators import BaseStepOperator, entrypoint
from zenml.utils.pipeline_docker_image_builder import PipelineDockerImageBuilder
from zenml.utils.source_utils import get_source_root_path

from zenml.config.docker_configuration import DockerConfiguration
if TYPE_CHECKING:
    from zenml.config.resource_configuration import ResourceConfiguration
logger = get_logger(__name__)

LOCAL_ENTRYPOINT = entrypoint.__file__
APP_DIR = "/app/"
CONTAINER_ZENML_CONFIG_DIR = ".zenconfig"
ENTRYPOINT_NAME = "zenml_spark_entrypoint.py"


class KubernetesSparkStepOperator(BaseStepOperator, PipelineDockerImageBuilder):
    # Instance parameters
    master: str
    deploy_mode: str = "cluster"

    # Parameters for kubernetes
    kubernetes_namespace: Optional[str] = None
    kubernetes_service_account: Optional[str] = None

    # Additional parameters for the spark submit
    submit_args: Optional[List[str]] = None

    # Class configuration
    FLAVOR: ClassVar[str] = SPARK_KUBERNETES_STEP_OPERATOR

    @validator("submit_args", pre=True)
    def _convert_json_string(
        cls, value: Union[None, str, List[str]]
    ) -> Optional[List[str]]:
        """Converts potential JSON strings passed via the CLI to a list.

        Args:
            value: The value to convert.

        Returns:
            The converted value.

        Raises:
            TypeError: If the value is not a `str`, `List` or `None`.
            ValueError: If the value is an invalid json string or a json string
                that does not decode into a list.
        """
        if isinstance(value, str):
            try:
                list_ = json.loads(value)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid json string '{value}'") from e

            if not isinstance(list_, List):
                raise ValueError(
                    f"Json string '{value}' did not decode into a list."
                )

            return list_
        elif isinstance(value, List) or value is None:
            return value
        else:
            raise TypeError(f"{value} is not a json string or a list.")

    @staticmethod
    def _generate_zenml_pipeline_dockerfile(
        parent_image: str,
        docker_configuration: DockerConfiguration,
        requirements_files: Sequence[str] = (),
        entrypoint: Optional[str] = None,
    ) -> List[str]:
        dockerfile = PipelineDockerImageBuilder._generate_zenml_pipeline_dockerfile(
            parent_image,
            docker_configuration,
            requirements_files,
            entrypoint,
        )
        return [dockerfile[0]] + [
            "USER root",  # required to install the requirements
            "RUN apt-get -y update",  # TODO: To be removed
            "RUN apt-get -y install git",  # TODO: To be removed
        ] + dockerfile[1:]

    def _create_base_command(self):
        """Create the base command for spark-submit."""
        command = [
            "spark-submit",
            "--master",
            f"k8s://{self.master}",
            "--deploy-mode",
            self.deploy_mode,
        ]
        return command

    def _create_configurations(self, image_name: str):
        """Build the configuration parameters for the spark-submit command."""
        configurations = [
            f"--conf spark.kubernetes.container.image={image_name}",
        ]
        if self.kubernetes_namespace:
            configurations.extend(
                [
                    "--conf",
                    f"spark.kubernetes.namespace={self.kubernetes_namespace}",
                ]
            )
        if self.kubernetes_service_account:
            configurations.extend(
                [
                    "--conf",
                    f"spark.kubernetes.authenticate.driver.serviceAccountName={self.kubernetes_service_account}",
                ]
            )

        repo = Repository()
        artifact_store = repo.active_stack.artifact_store

        from zenml.integrations.s3 import S3_ARTIFACT_STORE_FLAVOR

        if artifact_store.FLAVOR == S3_ARTIFACT_STORE_FLAVOR:
            configurations.extend(
                [
                    "--conf spark.hadoop.fs.s3a.fast.upload=true",
                    "--conf spark.hadoop.fs.s3.impl=org.apache.hadoop.fs.s3a.S3AFileSystem",
                    "--conf spark.hadoop.fs.AbstractFileSystem.s3.impl=org.apache.hadoop.fs.s3a.S3A",
                    "--conf spark.hadoop.fs.s3a.aws.credentials.provider=com.amazonaws.auth.DefaultAWSCredentialsProviderChain"
                ]
            )
            key, secret, _ = artifact_store._get_credentials()
            if key and secret:
                configurations.extend(
                    [
                        f"--conf spark.hadoop.fs.s3a.access.key={key}",
                        f"--conf spark.hadoop.fs.s3a.secret.key={secret}",
                    ]
                )
            else:
                raise RuntimeError(
                    "When you use an Spark step operator with an S3 artifact "
                    "store, please make sure that your artifact store has"
                    "defined the required credentials namely the access key "
                    "and the secret access key."
                )

        else:
            logger.warning(
                "In most cases, the spark step operator requires additional "
                "configuration based on the artifact store flavor you are "
                "using. With this in mind, when you use this step operator "
                "with certain artifact store flavor, ZenML takes care of the "
                "pre-configuration. However, the artifact store flavor "
                f"'{artifact_store.FLAVOR}' featured in this stack is not "
                f"known to this step operator and it might require additional "
                f"configuration."
            )

        if self.submit_args:
            for submit_arg in self.submit_args:
                configurations.append(f"--conf {submit_arg}")

        return configurations

    @staticmethod
    def _create_spark_app_command(entrypoint_command):
        """Build the python entrypoint command for the spark-submit."""
        command = [
            f"local://{APP_DIR}{ENTRYPOINT_NAME}"
        ]

        for arg in [
            "--main_module",
            "--step_source_path",
            "--execution_info_path",
            "--input_artifact_types_path",
        ]:
            i = entrypoint_command.index(arg)
            command.extend([arg, entrypoint_command[i + 1]])

        return command

    def launch(
        self,
        pipeline_name: str,
        run_name: str,
        entrypoint_command: List[str],
        resource_configuration: "ResourceConfiguration",
        docker_configuration: "DockerConfiguration"
    ) -> None:
        """Launch the spark job with spark-submit."""
        # Build the docker image to use for spark on Kubernetes

        entrypoint_path = os.path.join(
            get_source_root_path(),
            ENTRYPOINT_NAME
        )
        copy(LOCAL_ENTRYPOINT, entrypoint_path, overwrite=True)

        image_name = self.build_and_push_docker_image(
            pipeline_name=pipeline_name,
            docker_configuration=docker_configuration,
            stack=Repository().active_stack,
            runtime_configuration=RuntimeConfiguration(),
        )

        # Base command
        base_command = self._create_base_command()

        # Add configurations
        configurations = self._create_configurations(image_name=image_name)
        base_command.extend(configurations)

        # Add the spark app
        spark_app_command = self._create_spark_app_command(entrypoint_command)
        base_command.extend(spark_app_command)

        command = " ".join(base_command)

        # Execute the command
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            shell=True,
        )

        stdout, stderr = process.communicate()

        if process.returncode != 0:
            raise RuntimeError(stderr)
        print(stdout)
