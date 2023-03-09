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
"""Amazon SageMaker step operator flavor."""

from typing import TYPE_CHECKING, Optional, Type, Union, Dict, Any

from zenml.config.base_settings import BaseSettings
from zenml.integrations.aws import AWS_SAGEMAKER_STEP_OPERATOR_FLAVOR
from zenml.step_operators.base_step_operator import (
    BaseStepOperatorConfig,
    BaseStepOperatorFlavor,
)

if TYPE_CHECKING:
    from zenml.integrations.aws.step_operators import SagemakerStepOperator


class SagemakerStepOperatorSettings(BaseSettings):
    """Settings for the Sagemaker step operator.

    Attributes:
        experiment_name: The name for the experiment to which the job
            will be associated. If not provided, the job runs would be
            independent.
        input_data_s3_uri: S3 URI where training data is located if not locally,
            e.g. s3://my-bucket/my-data/train. How data will be made available
            to the container is configured with estimator_args.input_mode. Two possible
            input types:
                - str: S3 location where training data is saved.
                - dict[str, str]: (ChannelName, S3Location) which represent
                    channels (e.g. training, validation, testing) where
                    specific parts of the data are saved in S3.
        estimator_args: Arguments that are directly passed to the SageMaker
            Estimator. See
            https://sagemaker.readthedocs.io/en/stable/api/training/estimators.html#sagemaker.estimator.Estimator
            for a full list of arguments.
            For estimator_args.instance_type, check
            https://docs.aws.amazon.com/sagemaker/latest/dg/notebooks-available-instance-types.html
            for a list of available instance types.

    """
    experiment_name: Optional[str] = None
    input_data_s3_uri: Optional[Union[str, Dict[str, str]]] = None
    estimator_args: Dict[str, Any] = {}


class SagemakerStepOperatorConfig(  # type: ignore[misc] # https://github.com/pydantic/pydantic/issues/4173
    BaseStepOperatorConfig, SagemakerStepOperatorSettings
):
    """Config for the Sagemaker step operator.

    Attributes:
        role: The role that has to be assigned to the jobs which are
            running in Sagemaker.
        bucket: Name of the S3 bucket to use for storing artifacts
            from the job run. If not provided, a default bucket will be created
            based on the following format: "sagemaker-{region}-{aws-account-id}".
    """

    role: str
    bucket: Optional[str] = None

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


class SagemakerStepOperatorFlavor(BaseStepOperatorFlavor):
    """Flavor for the Sagemaker step operator."""

    @property
    def name(self) -> str:
        """Name of the flavor.

        Returns:
            The name of the flavor.
        """
        return AWS_SAGEMAKER_STEP_OPERATOR_FLAVOR

    @property
    def docs_url(self) -> Optional[str]:
        """A url to point at docs explaining this flavor.

        Returns:
            A flavor docs url.
        """
        from packaging.version import parse

        from zenml import __version__

        if parse(__version__) >= parse("0.34.0"):
            return self.generate_default_docs_url()

        old_docs_name = "amazon-sagemaker"
        return self.generate_default_docs_url(component_name=old_docs_name)

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
        return "https://public-flavor-logos.s3.eu-central-1.amazonaws.com/step_operator/sagemaker.png"

    @property
    def config_class(self) -> Type[SagemakerStepOperatorConfig]:
        """Returns SagemakerStepOperatorConfig config class.

        Returns:
            The config class.
        """
        return SagemakerStepOperatorConfig

    @property
    def implementation_class(self) -> Type["SagemakerStepOperator"]:
        """Implementation class.

        Returns:
            The implementation class.
        """
        from zenml.integrations.aws.step_operators import SagemakerStepOperator

        return SagemakerStepOperator
