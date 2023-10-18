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
"""Models representing run metadata."""

from typing import Optional, Union
from uuid import UUID

from pydantic import Field

from zenml.constants import STR_FIELD_MAX_LENGTH, TEXT_FIELD_MAX_LENGTH
from zenml.metadata.metadata_types import MetadataType, MetadataTypeEnum
from zenml.new_models.base import (
    WorkspaceScopedFilter,
    WorkspaceScopedRequest,
    WorkspaceScopedResponse,
    WorkspaceScopedResponseBody,
    WorkspaceScopedResponseMetadata,
    hydrated_property,
)

# ------------------ Request Model ------------------


class RunMetadataRequest(WorkspaceScopedRequest):
    """Request model for run metadata."""

    pipeline_run_id: Optional[UUID] = Field(
        title="The ID of the pipeline run that this metadata belongs to.",
    )
    step_run_id: Optional[UUID] = Field(
        title="The ID of the step run that this metadata belongs to."
    )
    artifact_id: Optional[UUID] = Field(
        title="The ID of the artifact that this metadata belongs to."
    )
    stack_component_id: Optional[UUID] = Field(
        title="The ID of the stack component that this metadata belongs to."
    )
    value: MetadataType = Field(
        title="The value of the metadata.",
        max_length=TEXT_FIELD_MAX_LENGTH,
    )
    type: MetadataTypeEnum = Field(
        title="The type of the metadata.",
        max_length=STR_FIELD_MAX_LENGTH,
    )


# ------------------ Update Model ------------------

# There is no update model for run metadata.

# ------------------ Response Model ------------------


class RunMetadataResponseBody(WorkspaceScopedResponseBody):
    """Response body for run metadata."""

    key: str = Field(
        title="The key of the metadata.",
        max_length=STR_FIELD_MAX_LENGTH,
    )


class RunMetadataResponseMetadata(WorkspaceScopedResponseMetadata):
    """Response metadata for run metadata."""

    pipeline_run_id: Optional[UUID] = Field(
        title="The ID of the pipeline run that this metadata belongs to.",
    )
    step_run_id: Optional[UUID] = Field(
        title="The ID of the step run that this metadata belongs to."
    )
    artifact_id: Optional[UUID] = Field(
        title="The ID of the artifact that this metadata belongs to."
    )
    stack_component_id: Optional[UUID] = Field(
        title="The ID of the stack component that this metadata belongs to."
    )
    value: MetadataType = Field(
        title="The value of the metadata.",
        max_length=TEXT_FIELD_MAX_LENGTH,
    )
    type: MetadataTypeEnum = Field(
        title="The type of the metadata.",
        max_length=STR_FIELD_MAX_LENGTH,
    )


class RunMetadataResponse(WorkspaceScopedResponse):
    """Response model for run metadata."""

    # Body and metadata pair
    body: "RunMetadataResponseBody"
    metadata: Optional["RunMetadataResponseMetadata"]

    def get_hydrated_version(self) -> "RunMetadataResponse":
        """Get the hydrated version of this run metadata."""
        from zenml.client import Client

        return Client().get_run_metadata(self.id)

    # Body and metadata properties
    @property
    def key(self):
        """The `key` property."""
        return self.body.key

    @hydrated_property
    def pipeline_run_id(self):
        """The `pipeline_run_id` property."""
        return self.metadata.pipeline_run_id

    @hydrated_property
    def step_run_id(self):
        """The `step_run_id` property."""
        return self.metadata.step_run_id

    @hydrated_property
    def artifact_id(self):
        """The `artifact_id` property."""
        return self.metadata.artifact_id

    @hydrated_property
    def stack_component_id(self):
        """The `stack_component_id` property."""
        return self.metadata.stack_component_id

    @hydrated_property
    def value(self):
        """The `value` property."""
        return self.metadata.value

    @hydrated_property
    def type(self):
        """The `type` property."""
        return self.metadata.type


# ------------------ Filter Model ------------------


class RunMetadataFilter(WorkspaceScopedFilter):
    """Model to enable advanced filtering of run metadata."""

    pipeline_run_id: Optional[Union[str, UUID]] = None
    step_run_id: Optional[Union[str, UUID]] = None
    artifact_id: Optional[Union[str, UUID]] = None
    stack_component_id: Optional[Union[str, UUID]] = None
    key: Optional[str] = None
    type: Optional[Union[str, MetadataTypeEnum]] = None
