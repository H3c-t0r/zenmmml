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
"""Models representing artifacts."""

from typing import TYPE_CHECKING, ClassVar, Dict, List, Optional, Union
from uuid import UUID

from pydantic import Field

from zenml.config.source import Source, convert_source_validator
from zenml.constants import STR_FIELD_MAX_LENGTH
from zenml.enums import ArtifactType
from zenml.new_models.base import (
    WorkspaceScopedFilter,
    WorkspaceScopedRequest,
    WorkspaceScopedResponse,
    WorkspaceScopedResponseBody,
    WorkspaceScopedResponseMetadata,
    hydrated_property,
)

if TYPE_CHECKING:
    from zenml.new_models.core.artifact_visualization import (
        ArtifactVisualizationRequest,
        ArtifactVisualizationResponse,
    )
    from zenml.new_models.core.run_metadata import (
        RunMetadataResponse,
    )


# ------------------ Request Model ------------------


class ArtifactRequest(WorkspaceScopedRequest):
    """Request model for artifacts."""

    name: str = Field(
        title="Name of the output in the parent step.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    type: ArtifactType = Field(title="Type of the artifact.")
    artifact_store_id: Optional[UUID] = Field(
        title="ID of the artifact store in which this artifact is stored.",
        default=None,
    )
    uri: str = Field(
        title="URI of the artifact.", max_length=STR_FIELD_MAX_LENGTH
    )
    materializer: Source = Field(
        title="Materializer class to use for this artifact.",
    )
    data_type: Source = Field(
        title="Data type of the artifact.",
    )
    visualizations: Optional[List["ArtifactVisualizationRequest"]] = Field(
        default=None, title="Visualizations of the artifact."
    )

    _convert_source = convert_source_validator("materializer", "data_type")


# ------------------ Update Model ------------------

# There is no update model for artifacts.

# ------------------ Response Model ------------------


class ArtifactResponseBody(WorkspaceScopedResponseBody):
    """Response body for artifacts."""

    uri: str = Field(
        title="URI of the artifact.", max_length=STR_FIELD_MAX_LENGTH
    )
    type: ArtifactType = Field(title="Type of the artifact.")


class ArtifactResponseMetadata(WorkspaceScopedResponseMetadata):
    """Response metadata for artifacts."""

    artifact_store_id: Optional[UUID] = Field(
        title="ID of the artifact store in which this artifact is stored.",
        default=None,
    )
    producer_step_run_id: Optional[UUID] = Field(
        title="ID of the step run that produced this artifact.",
        default=None,
    )
    visualizations: Optional[List["ArtifactVisualizationResponse"]] = Field(
        default=None, title="Visualizations of the artifact."
    )
    run_metadata: Dict[str, "RunMetadataResponse"] = Field(
        default={}, title="Metadata of the artifact."
    )
    materializer: Source = Field(
        title="Materializer class to use for this artifact.",
    )
    data_type: Source = Field(
        title="Data type of the artifact.",
    )

    _convert_source = convert_source_validator("materializer", "data_type")


class ArtifactResponse(WorkspaceScopedResponse):
    """Response model for artifacts."""

    name: str = Field(
        title="Name of the output in the parent step.",
        max_length=STR_FIELD_MAX_LENGTH,
    )

    # Body and metadata pair
    body: "ArtifactResponseBody"
    metadata: Optional["ArtifactResponseMetadata"]

    def get_hydrated_version(self) -> "ArtifactResponse":
        """Get the hydrated version of this artifact."""
        from zenml.client import Client

        return Client().get_artifact(self.id)

    # Body and metadata properties
    @property
    def uri(self):
        """The `uri` property."""
        return self.body.uri

    @property
    def type(self):
        """The `type` property."""
        return self.body.type

    @hydrated_property
    def artifact_store_id(self):
        """The `artifact_store_id` property."""
        return self.metadata.artifact_store_id

    @hydrated_property
    def producer_step_run_id(self):
        """The `producer_step_run_id` property."""
        return self.metadata.producer_step_run_id

    @hydrated_property
    def visualizations(self):
        """The `visualizations` property."""
        return self.metadata.visualizations

    @hydrated_property
    def run_metadata(self):
        """The `metadata` property."""
        return self.metadata.run_metadata

    @hydrated_property
    def materializer(self):
        """The `materializer` property."""
        return self.metadata.materializer

    @hydrated_property
    def data_type(self):
        """The `data_type` property."""
        return self.metadata.data_type


# ------------------ Filter Model ------------------


class ArtifactFilter(WorkspaceScopedFilter):
    """Model to enable advanced filtering of all Artifacts."""

    # `only_unused` refers to a property of the artifacts relationship
    #  rather than a field in the db, hence it needs to be handled
    #  explicitly
    FILTER_EXCLUDE_FIELDS: ClassVar[List[str]] = [
        *WorkspaceScopedFilter.FILTER_EXCLUDE_FIELDS,
        "only_unused",
    ]

    name: Optional[str] = Field(
        default=None,
        description="Name of the artifact",
    )
    uri: Optional[str] = Field(
        default=None,
        description="Uri of the artifact",
    )
    materializer: Optional[str] = Field(
        default=None,
        description="Materializer used to produce the artifact",
    )
    type: Optional[str] = Field(
        default=None,
        description="Type of the artifact",
    )
    data_type: Optional[str] = Field(
        default=None,
        description="Datatype of the artifact",
    )
    artifact_store_id: Optional[Union[UUID, str]] = Field(
        default=None, description="Artifact store for this artifact"
    )
    workspace_id: Optional[Union[UUID, str]] = Field(
        default=None, description="Workspace for this artifact"
    )
    user_id: Optional[Union[UUID, str]] = Field(
        default=None, description="User that produced this artifact"
    )
    only_unused: Optional[bool] = Field(
        default=False, description="Filter only for unused artifacts"
    )
