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
"""Functionality for OpenAI standard hooks."""

import io
import sys

import openai
from rich.console import Console

from zenml import get_step_context
from zenml.client import Client
from zenml.logger import get_logger

logger = get_logger(__name__)


def openai_alerter_failure_hook_helper(
    exception: BaseException,
    model_name: str,
) -> None:
    """Standard failure hook that sends a message to an Alerter.

    Your OpenAI API key must be stored in the secret store under the name
    "openai" and with the key "api_key".

    Args:
        exception: The exception that was raised.
        model_name: The OpenAI model to use for the chatbot.
    """
    client = Client()
    context = get_step_context()

    # get the api_key from the secret store
    try:
        openai_secret = client.get_secret(
            "openai", allow_partial_name_match=False
        )
        openai_api_key = openai_secret.secret_values.get("api_key")
    except (KeyError, NotImplementedError):
        openai_api_key = None

    alerter = client.active_stack.alerter
    if alerter and openai_api_key:
        output_captured = io.StringIO()
        original_stdout = sys.stdout
        sys.stdout = output_captured
        console = Console()
        console.print_exception(show_locals=False)

        sys.stdout = original_stdout
        rich_traceback = output_captured.getvalue()

        response = openai.ChatCompletion.create(  # type: ignore
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": f"This is an error message (following an exception of type '{type(exception)}') I encountered while executing a ZenML step. Please suggest ways I might fix the problem. Feel free to give code snippets as examples, and note that your response will be piped to a Slack bot so make sure the formatting is appropriate: {exception} -- {rich_traceback}. Thank you!",
                }
            ],
        )
        suggestion = response["choices"][0]["message"]["content"]
        message = "*Failure Hook Notification! Step failed!*" + "\n\n"
        message += f"Run name: `{context.pipeline_run.name}`" + "\n"
        message += f"Step name: `{context.step_run.name}`" + "\n"
        message += f"Parameters: `{context.step_run.config.parameters}`" + "\n"
        message += f"Exception: `({type(exception)}) {exception}`" + "\n\n"
        message += (
            f"*OpenAI ChatGPT's suggestion (model = `{model_name}`) on how to fix it:*\n `{suggestion}`"
            + "\n"
        )
        alerter.post(message)
    elif not openai_api_key:
        logger.warning(
            "Specified OpenAI failure hook but no OpenAI API key found. Skipping..."
        )
    else:
        logger.warning(
            "Specified OpenAI failure hook but no alerter configured in the stack. Skipping..."
        )


def openai_chatgpt_alerter_failure_hook(
    exception: BaseException,
) -> None:
    """Alerter hook that uses the OpenAI ChatGPT model.

    Args:
        exception: The exception that was raised.
    """
    openai_alerter_failure_hook_helper(exception, "gpt-3.5-turbo")


def openai_gpt4_alerter_failure_hook(
    exception: BaseException,
) -> None:
    """Alerter hook that uses the OpenAI GPT-4 model.

    Args:
        exception: The exception that was raised.
    """
    openai_alerter_failure_hook_helper(exception, "gpt-4")
