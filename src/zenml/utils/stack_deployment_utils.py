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
import urllib.parse
from abc import abstractmethod
from typing import Optional

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
    def deploy_url(self) -> str:
        """Return the URL to deploy the ZenML stack to the specified cloud provider.

        The URL should point to a cloud provider console where the user can
        deploy the ZenML stack and should include as many pre-filled parameters
        as possible.

        Returns:
            The URL to deploy the ZenML stack to the specified cloud provider.
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

    def __init__(self, *args, **kwargs):
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
Clicking on the link below will take you to the AWS console where you'll be
asked to log into your AWS account and provision a CloudFormation ZenML stack.

**NOTE**: this stack will create the following new resources in your AWS
account. Please ensure you have the necessary permissions and are aware of any
potential costs:

- An S3 bucket to store pipeline artifacts.
- An ECR repository to store pipeline Docker images.
- Sagemaker resources to run pipelines.
- An IAM user, IAM role and AWS access key with the minimum necessary
permissions to access the above resources to run pipelines.

The CloudFormation stack will automatically create an AWS secret key that
will be shared with ZenML to give it permissions to access the resources created
by the stack. You can revoke these permissions at any time by deleting the
CloudFormation stack.
"""

    def deploy_url(self) -> str:
        """Return the URL to deploy the ZenML stack to the specified cloud provider.

        The URL should point to a cloud provider console where the user can
        deploy the ZenML stack and should include as many pre-filled parameters
        as possible.

        Returns:
            The URL to deploy the ZenML stack to the specified cloud provider.
        """
        client = Client()
        assert isinstance(client.zen_store, RestZenStore)
        api_token = client.zen_store.get_api_token(
            expires_minutes=60,
        )
        params = dict(
            stackName=self.stack_name,
            templateURL="https://zenml-cf-templates.s3.eu-central-1.amazonaws.com/aws-ecr-s3-sagemaker.yaml",
            ResourceNameSuffix=random_str(6).lower(),
            ZenMLServerURL=client.zen_store.config.url,
            ZenMLServerAPIToken=api_token,
        )
        # Encode the parameters as URL query parameters
        query_params = "&".join(
            [urllib.parse.quote_plus(f"{k}={v}") for k, v in params.items()]
        )

        return (
            f"https://console.aws.amazon.com/cloudformation/home?"
            f"region=eu-central-1#/stacks/create/review?{query_params}"
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
        stacks = client.list_stacks(
            created=f"gt:{self.date_start.isoformat()}",
            size=50,
        )

        if not stacks.items:
            return None

        # Set the start date to the earliest stack creation date to
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

                return False

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
The ZenML stack has been successfully deployed and registered. You can delete
the CloudFormation at any time to revoke ZenML's access to your AWS account and
to clean up the resources created by the stack by using the AWS CloudFormation
console.
"""


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
