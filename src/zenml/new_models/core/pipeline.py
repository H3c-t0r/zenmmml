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
"""Models representing pipelines."""

from typing import TYPE_CHECKING, Any, List, Optional, Union
from uuid import UUID

from pydantic import Field

from zenml.config.pipeline_spec import PipelineSpec
from zenml.constants import STR_FIELD_MAX_LENGTH, TEXT_FIELD_MAX_LENGTH
from zenml.enums import ExecutionStatus
from zenml.new_models.base import (
    WorkspaceScopedFilter,
    WorkspaceScopedRequest,
    WorkspaceScopedResponse,
    WorkspaceScopedResponseBody,
    WorkspaceScopedResponseMetadata,
    hydrated_property,
    update_model,
)

if TYPE_CHECKING:
    from zenml.new_models.core.pipeline_run import (
        PipelineRunResponse,
    )


# ------------------ Request Model ------------------


class PipelineRequest(WorkspaceScopedRequest):
    """Request model for pipelines."""

    name: str = Field(
        title="The name of the pipeline.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    version: str = Field(
        title="The version of the pipeline.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    version_hash: str = Field(
        title="The version hash of the pipeline.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    docstring: Optional[str] = Field(
        title="The docstring of the pipeline.",
        max_length=TEXT_FIELD_MAX_LENGTH,
    )
    spec: PipelineSpec = Field(title="The spec of the pipeline.")


# ------------------ Update Model ------------------


@update_model
class PipelineUpdate(PipelineRequest):
    """Update model for pipelines."""


# ------------------ Response Model ------------------


class PipelineResponseBody(WorkspaceScopedResponseBody):
    """Response body for pipelines."""

    status: Optional[List[ExecutionStatus]] = Field(
        default=None, title="The status of the last 3 Pipeline Runs."
    )


class PipelineResponseMetadata(WorkspaceScopedResponseMetadata):
    """Response metadata for pipelines."""

    version: str = Field(
        title="The version of the pipeline.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    version_hash: str = Field(
        title="The version hash of the pipeline.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    spec: PipelineSpec = Field(title="The spec of the pipeline.")
    docstring: Optional[str] = Field(
        title="The docstring of the pipeline.",
        max_length=TEXT_FIELD_MAX_LENGTH,
    )


class PipelineResponse(WorkspaceScopedResponse):
    """Response model for pipelines."""

    name: str = Field(
        title="The name of the pipeline.",
        max_length=STR_FIELD_MAX_LENGTH,
    )

    # Body and metadata pair
    body: "PipelineResponseBody"
    metadata: Optional["PipelineResponseMetadata"]

    def get_hydrated_version(self) -> "PipelineResponse":
        """Get the hydrated version of this pipeline"""
        from zenml.client import Client

        return Client().get_pipeline(self.id)

    # Helper methods
    def get_runs(self, **kwargs: Any) -> List["PipelineRunResponse"]:
        """Get runs of this pipeline.

        Can be used to fetch runs other than `self.runs` and supports
        fine-grained filtering and pagination.

        Args:
            **kwargs: Further arguments for filtering or pagination that are
                passed to `client.list_pipeline_runs()`.

        Returns:
            List of runs of this pipeline.
        """
        from zenml.client import Client

        return Client().list_pipeline_runs(pipeline_id=self.id, **kwargs).items

    @property
    def runs(self) -> List["PipelineRunResponse"]:
        """Returns the 20 most recent runs of this pipeline in descending order.

        Returns:
            The 20 most recent runs of this pipeline in descending order.
        """
        return self.get_runs()

    @property
    def num_runs(self) -> int:
        """Returns the number of runs of this pipeline.

        Returns:
            The number of runs of this pipeline.
        """
        from zenml.client import Client

        return Client().list_pipeline_runs(pipeline_id=self.id, size=1).total

    @property
    def last_run(self) -> "PipelineRunResponse":
        """Returns the last run of this pipeline.

        Returns:
            The last run of this pipeline.

        Raises:
            RuntimeError: If no runs were found for this pipeline.
        """
        runs = self.get_runs(size=1)
        if not runs:
            raise RuntimeError(
                f"No runs found for pipeline '{self.name}' with id {self.id}."
            )
        return runs[0]

    @property
    def last_successful_run(self) -> "PipelineRunResponse":
        """Returns the last successful run of this pipeline.

        Returns:
            The last successful run of this pipeline.

        Raises:
            RuntimeError: If no successful runs were found for this pipeline.
        """
        runs = self.get_runs(status=ExecutionStatus.COMPLETED, size=1)
        if not runs:
            raise RuntimeError(
                f"No successful runs found for pipeline '{self.name}' with id "
                f"{self.id}."
            )
        return runs[0]

    # Body and metadata properties
    @property
    def status(self):
        """The `status` property."""
        return self.body.status

    @hydrated_property
    def version_hash(self):
        """The `version_hash` property."""
        return self.metadata.version_hash

    @hydrated_property
    def docstring(self):
        """The `docstring` property."""
        return self.metadata.docstring

    @hydrated_property
    def spec(self):
        """The `spec` property."""
        return self.metadata.spec

    @hydrated_property
    def version(self):
        """The `version` property."""
        return self.metadata.version


# ------------------ Filter Model ------------------


class PipelineFilter(WorkspaceScopedFilter):
    """Model to enable advanced filtering of all Workspaces."""

    name: Optional[str] = Field(
        default=None,
        description="Name of the Pipeline",
    )
    version: Optional[str] = Field(
        default=None,
        description="Version of the Pipeline",
    )
    version_hash: Optional[str] = Field(
        default=None,
        description="Version hash of the Pipeline",
    )
    docstring: Optional[str] = Field(
        default=None,
        description="Docstring of the Pipeline",
    )
    workspace_id: Optional[Union[UUID, str]] = Field(
        default=None, description="Workspace of the Pipeline"
    )
    user_id: Optional[Union[UUID, str]] = Field(
        default=None, description="User of the Pipeline"
    )
