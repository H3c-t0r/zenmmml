#  Copyright (c) ZenML GmbH 2024. All Rights Reserved.

#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:

#       https://www.apache.org/licenses/LICENSE-2.0

#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.
"""Functionality to deploy a ZenML stack to a cloud provider."""

import datetime
from abc import abstractmethod
from typing import Any, Optional, Tuple

from pydantic import BaseModel

from zenml.client import Client
from zenml.enums import StackComponentType, StackDeploymentProvider
from zenml.models import (
    StackResponse,
)
from zenml.utils.string_utils import random_str
from zenml.zen_stores.rest_zen_store import RestZenStore


class ZenMLCloudStackDeployment(BaseModel):
    """ZenML Cloud Stack CLI Deployment base class."""

    stack_name: str
    provider: StackDeploymentProvider

    @abstractmethod
    def description(self) -> str:
        """Return a description of the ZenML Cloud Stack Deployment.

        This will be displayed in the CLI when the user is prompted to deploy
        the ZenML stack.

        Returns:
            A description of the ZenML Cloud Stack Deployment.
        """

    @abstractmethod
    def deploy_instructions(self) -> str:
        """Return instructions on how to deploy the ZenML stack to the specified cloud provider.

        This will be displayed in the CLI before the user is prompted to deploy
        the ZenML stack.

        Returns:
            Instructions on how to deploy the ZenML stack to the specified cloud
            provider.
        """

    @abstractmethod
    def deploy_url(self) -> Tuple[str, str]:
        """Return the URL to deploy the ZenML stack to the specified cloud provider.

        The URL should point to a cloud provider console where the user can
        deploy the ZenML stack and should include as many pre-filled parameters
        as possible.

        Returns:
            The URL to deploy the ZenML stack to the specified cloud provider
            and a text description of the URL.
        """

    @abstractmethod
    def get_stack(self) -> Optional[StackResponse]:
        """Return the ZenML stack that was deployed and registered.

        The CLI will keep calling this method until a stack is found matching
        the deployment provider and stack name or until the user cancels the
        deployment.

        Returns:
            The ZenML stack that was deployed and registered or None if the
            stack was not found.
        """

    @abstractmethod
    def post_deploy_instructions(self, cancelled: bool) -> str:
        """Return instructions on what to do after the deployment is complete or cancelled.

        This will be displayed in the CLI after the deployment is complete or
        cancelled.

        Args:
            cancelled: Whether the deployment was cancelled by the user.

        Returns:
            Instructions on what to do after the deployment is complete or
            cancelled.
        """


class AWSZenMLCloudStackDeployment(ZenMLCloudStackDeployment):
    """AWS ZenML Cloud Stack Deployment."""

    date_start: datetime.datetime

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the AWS ZenML Cloud Stack Deployment.

        Args:
            *args: Additional arguments.
            **kwargs: Additional keyword arguments.
        """
        date_start = datetime.datetime.utcnow()
        kwargs["date_start"] = date_start
        super().__init__(*args, **kwargs)

    def description(self) -> str:
        """Return a description of the ZenML Cloud Stack Deployment.

        This will be displayed in the CLI when the user is prompted to deploy
        the ZenML stack.

        Returns:
            A description of the ZenML Cloud Stack Deployment.
        """
        return """
# AWS ZenML Cloud Stack Deployment

Provision and register a basic AWS ZenML stack authenticated and connected to
all the necessary cloud infrastructure resources required to run pipelines in
AWS.
"""

    def deploy_instructions(self) -> str:
        """Return instructions on how to deploy the ZenML stack to the specified cloud provider.

        This will be displayed in the CLI before the user is prompted to deploy
        the ZenML stack.

        Returns:
            Instructions on how to deploy the ZenML stack to the specified cloud
            provider.
        """
        return """
## Instructions

You will be redirected to the AWS console in your browser where you'll be asked
to log into your AWS account and create a CloudFormation ZenML stack. The stack
parameters will be pre-filled with the necessary information to connect ZenML to
your AWS account, so you should only need to review and confirm the stack.

After the CloudFormation stack is deployed, you can return to the CLI to view
details about the associated ZenML stack automatically registered with ZenML.

**NOTE**: The CloudFormation stack will create the following new resources in
your AWS account. Please ensure you have the necessary permissions and are aware
of any potential costs:

- An S3 bucket registered as a [ZenML artifact store](https://docs.zenml.io/stack-components/artifact-stores/s3).
- An ECR repository registered as a [ZenML container registry](https://docs.zenml.io/stack-components/container-registries/aws).
- Sagemaker registered as a [ZenML orchestrator](https://docs.zenml.io/stack-components/orchestrators/sagemaker).
- An IAM user and IAM role with the minimum necessary permissions to access the
above resources.
- An AWS access key used to give access to ZenML to connect to the above
resources through a [ZenML service connector](https://docs.zenml.io/how-to/auth-management/aws-service-connector).

The CloudFormation stack will automatically create an AWS secret key and
will share it with ZenML to give it permissions to access the resources created
by the stack. You can revoke these permissions at any time by deleting the
CloudFormation stack.
"""

    def deploy_url(self) -> Tuple[str, str]:
        """Return the URL to deploy the ZenML stack to the specified cloud provider.

        The URL should point to a cloud provider console where the user can
        deploy the ZenML stack and should include as many pre-filled parameters
        as possible.

        Returns:
            The URL to deploy the ZenML stack to the specified cloud provider
            and a text description of the URL.
        """
        client = Client()
        assert isinstance(client.zen_store, RestZenStore)
        api_token = client.zen_store.get_api_token(
            expires_minutes=60,
        )
        params = dict(
            stackName=self.stack_name,
            templateURL="https://zenml-cf-templates.s3.eu-central-1.amazonaws.com/aws-ecr-s3-sagemaker.yaml",
            param_ResourceName=f"zenml-{random_str(6).lower()}",
            param_ZenMLServerURL=client.zen_store.config.url,
            param_ZenMLServerAPIToken=api_token,
        )
        # Encode the parameters as URL query parameters
        query_params = "&".join([f"{k}={v}" for k, v in params.items()])

        return (
            f"https://console.aws.amazon.com/cloudformation/home?"
            f"region=eu-central-1#/stacks/create/review?{query_params}",
            "AWS CloudFormation Console",
        )

    def get_stack(self) -> Optional[StackResponse]:
        """Return the ZenML stack that was deployed and registered.

        The CLI will keep calling this method until a stack is found matching
        the deployment provider and stack name or until the user cancels the
        deployment.

        Returns:
            The ZenML stack that was deployed and registered or None if the
            stack was not found.
        """
        client = Client()

        # It's difficult to find a stack that matches the CloudFormation
        # deployment 100% because the user can change the stack name and the
        # stack name suffix before they deploy the stack.
        #
        # We try to find a full AWS stack that matches the deployment provider
        # that was registered after this deployment was created.

        # Get all recent stacks
        # remove milliseconds from the date
        stacks = client.list_stacks(
            created=f"gt:{str(self.date_start.replace(microsecond=0))}",
            sort_by="desc:created",
            size=50,
        )

        if not stacks.items:
            return None

        # Set the start date to the latest stack creation date to
        # avoid fetching the same stacks again
        self.date_start = stacks.items[0].created

        # Find the stack that matches the deployment provider
        for stack in stacks.items:

            def check_component(
                component_type: StackComponentType, expected_flavor: str
            ) -> bool:
                """Check if the stack has a component of the expected type and flavor.

                Args:
                    component_type: The expected component type.
                    expected_flavor: The expected component flavor.

                Returns:
                    True if the stack has a component of the expected type and
                    flavor and is linked to a service connector, False
                    otherwise.
                """
                if component_type not in stack.components:
                    return False

                if len(stack.components[component_type]) != 1:
                    return False

                component = stack.components[component_type][0]

                if component.flavor != expected_flavor:
                    return False

                if component.connector is None:
                    return False

                return True

            if not check_component(StackComponentType.ARTIFACT_STORE, "s3"):
                continue

            if not check_component(
                StackComponentType.ORCHESTRATOR, "sagemaker"
            ):
                continue

            if not check_component(
                StackComponentType.CONTAINER_REGISTRY, "aws"
            ):
                continue

            return stack

        return None

    def post_deploy_instructions(self, cancelled: bool) -> str:
        """Return instructions on what to do after the deployment is complete or cancelled.

        This will be displayed in the CLI after the deployment is complete or
        cancelled.

        Args:
            cancelled: Whether the deployment was cancelled by the user.

        Returns:
            Instructions on what to do after the deployment is complete or
            cancelled.
        """
        if not cancelled:
            return """
## Follow-up

The ZenML stack has been successfully deployed and registered. You can delete
the CloudFormation at any time to revoke ZenML's access to your AWS account and
to clean up the resources created by the stack by using the AWS CloudFormation
console.

"""
        return ""


STACK_DEPLOYMENT_PROVIDERS = {
    StackDeploymentProvider.AWS: AWSZenMLCloudStackDeployment,
}


def get_stack_deployment(
    provider: StackDeploymentProvider, stack_name: Optional[str] = None
) -> ZenMLCloudStackDeployment:
    """Get the ZenML Cloud Stack Deployment class for the specified provider.

    Args:
        provider: The stack deployment provider.
        stack_name: The stack name.

    Returns:
        The ZenML Cloud Stack Deployment class for the specified provider.
    """
    stack_name = stack_name or f"zenml-{provider.value}-stack"
    return STACK_DEPLOYMENT_PROVIDERS[provider](
        stack_name=stack_name, provider=provider
    )
