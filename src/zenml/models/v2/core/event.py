#  Copyright (c) ZenML GmbH 2024. All Rights Reserved.
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
"""Collection of all models concerning event configurations."""
from typing import Dict, Any

from pydantic import Field

from zenml import BaseRequest
from zenml.constants import STR_FIELD_MAX_LENGTH


# ------------------ Request Model ------------------

class EventMatchRequest(BaseRequest):
    """BaseModel for all Events."""

    event_type: str = Field(
        title="The type of event.",
        max_length=STR_FIELD_MAX_LENGTH,
    )

    # TODO: refine and type this ?
    configuration: Dict[str, Any] = {}


# ------------------ Update Model ------------------

@update_model
class TriggerUpdate(TriggerRequest):
    """Update model for stacks."""


# ------------------ Response Model ------------------

class TriggerResponseBody(WorkspaceScopedResponseBody):
    """ResponseBody for triggers."""
    event: Event = Field(
        title="The event that activates this trigger.",
    )
    action: Action = Field(
        title="The actions that is executed by this trigger.",
    )
    created: datetime = Field(
        title="The timestamp when this trigger was created."
    )
    updated: datetime = Field(
        title="The timestamp when this trigger was last updated.",
    )


class TriggerResponseMetadata(WorkspaceScopedResponseMetadata):
    """Response metadata for triggers."""

    description: str = Field(
        default="",
        title="The description of the trigger",
        max_length=STR_FIELD_MAX_LENGTH,
    )


class TriggerResponse(
    WorkspaceScopedResponse[TriggerResponseBody, TriggerResponseMetadata]
):
    """Response model for models."""

    name: str = Field(
        title="The name of the model",
        max_length=STR_FIELD_MAX_LENGTH,
    )


# ------------------ Filter Model ------------------


class TriggerFilter(WorkspaceScopedFilter):
    """Model to enable advanced filtering of all TriggerModels."""
    name: str = Field(
        title="The name of the Trigger.", max_length=STR_FIELD_MAX_LENGTH
    )
    description: str = Field(
        default="",
        title="The description of the trigger",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    # Enable filtering by event and action ?
