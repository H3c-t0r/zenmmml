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
"""Utility class to help with interacting with the dashboard."""
from typing import Optional

from zenml import constants
from zenml.client import Client
from zenml.enums import EnvironmentType, StoreType
from zenml.environment import get_environment
from zenml.logger import get_logger
from zenml.models import (
    ComponentResponseModel,
    SecretResponseModel,
    StackResponseModel,
)
from zenml.models.pipeline_run_models import PipelineRunResponseModel

logger = get_logger(__name__)


def get_base_url() -> Optional[str]:
    """Function to get the base workspace-scoped url.

    Returns:
        the base url if the client is using a rest zen store, else None
    """
    client = Client()

    if client.zen_store.type == StoreType.REST:
        url = (
            client.zen_store.url
            + f"{constants.WORKSPACES}/{client.active_workspace.name}"
        )
        return url

    return None


def get_stack_url(stack: StackResponseModel) -> None:
    """Function to get the dashboard URL of a given stack model.

    Args:
        stack: the response model of the given stack.
    """
    base_url = get_base_url()
    if base_url:
        stack_url = base_url + f"{constants.STACKS}/{stack.id}/configuration"
        logger.info(f"Dashboard URL for the stack: {stack_url}")

    else:
        logger.warning(
            "You can display all of your stacks on the `ZenML Dashboard`. "
            "Run `zenml up` to spin it up locally."
        )


def get_component_url(component: ComponentResponseModel) -> None:
    """Function to get the dashboard URL of a given component model.

    Args:
        component: the response model of the given component.
    """
    base_url = get_base_url()

    if base_url:
        component_url = (
            base_url
            + f"{constants.STACK_COMPONENTS}/{component.type.value}/{component.id}"
        )
        logger.info(f"Dashboard URL for the component: {component_url}")

    else:
        logger.warning(
            "You can display all of your components on the `ZenML Dashboard`. "
            "Dashboard. Run `zenml up` to spin it up locally."
        )


def get_run_url(run: PipelineRunResponseModel) -> None:
    """Function to get the dashboard URL of a given pipeline run.

    Args:
        run: the response model of the given pipeline run.
    """
    base_url = get_base_url()

    if base_url:
        run_url = (
            base_url
            + f"{constants.PIPELINES}/{run.pipeline.id}{constants.RUNS}/{run.id}/dag"
            if run.pipeline
            else f"/all-runs/{run.id}/dag"
        )
        logger.info(f"Dashboard URL for the run: {run_url}")

    else:
        logger.warning(
            "You can display all of your uns on the `ZenML Dashboard`. "
            "Run `zenml up` to spin it up locally."
        )


def get_secret_url(secret: SecretResponseModel) -> None:
    """Function to get the dashboard URL of a given secret.

    Args:
        secret: the response model of the given secret.
    """
    base_url = get_base_url()

    if base_url:
        secret_url = base_url + f"{constants.SECRETS}/{secret.id}"

        logger.info(f"Dashboard URL for the secret: {secret_url}")

    else:
        logger.warning(
            "You can display all of your secrets on the `ZenML Dashboard`. "
            "Run `zenml up` to spin it up locally."
        )


def show_dashboard(url: str) -> None:
    """Show the ZenML dashboard at the given URL.

    In native environments, the dashboard is opened in the default browser.
    In notebook environments, the dashboard is embedded in an iframe.

    Args:
        url: URL of the ZenML dashboard.
    """
    environment = get_environment()
    if environment in (EnvironmentType.NOTEBOOK, EnvironmentType.COLAB):
        from IPython.core.display import display
        from IPython.display import IFrame

        display(IFrame(src=url, width="100%", height=720))

    elif environment in (EnvironmentType.NATIVE, EnvironmentType.WSL):
        if constants.handle_bool_env_var(
            constants.ENV_AUTO_OPEN_DASHBOARD, default=True
        ):
            try:
                import webbrowser

                if environment == EnvironmentType.WSL:
                    webbrowser.get("wslview %s").open(url)
                else:
                    webbrowser.open(url)
                logger.info(
                    "Automatically opening the dashboard in your "
                    "browser. To disable this, set the env variable "
                    "AUTO_OPEN_DASHBOARD=false."
                )
            except Exception as e:
                logger.error(e)
        else:
            logger.info(
                "To open the dashboard in a browser automatically, "
                "set the env variable AUTO_OPEN_DASHBOARD=true."
            )

    else:
        logger.info(f"The ZenML dashboard is available at {url}.")
