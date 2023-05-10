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
"""Models representing steps of pipeline runs."""

from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field

from zenml.config.step_configurations import Step
from zenml.enums import ExecutionStatus
from zenml.models.base_models import (
    WorkspaceScopedRequestModel,
    WorkspaceScopedResponseModel,
)
from zenml.models.constants import STR_FIELD_MAX_LENGTH, TEXT_FIELD_MAX_LENGTH
from zenml.models.filter_models import WorkspaceScopedFilterModel
from zenml.models.logs_models import LogsRequestModel, LogsResponseModel

if TYPE_CHECKING:
    from zenml.models import ArtifactResponseModel, RunMetadataResponseModel


# ---- #
# BASE #
# ---- #


class StepRunBaseModel(BaseModel):
    """Base model for step runs."""

    name: str = Field(
        title="The name of the pipeline run step.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    step: Step
    pipeline_run_id: UUID
    original_step_run_id: Optional[UUID] = None
    status: ExecutionStatus
    parent_step_ids: List[UUID] = []
    cache_key: Optional[str] = Field(
        title="The cache key of the step run.",
        default=None,
        max_length=STR_FIELD_MAX_LENGTH,
    )
    docstring: Optional[str] = Field(
        title="The docstring of the step function or class.",
        default=None,
        max_length=TEXT_FIELD_MAX_LENGTH,
    )
    source_code: Optional[str] = Field(
        title="The source code of the step function or class.",
        default=None,
        max_length=TEXT_FIELD_MAX_LENGTH,
    )
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


# -------- #
# RESPONSE #
# -------- #


class StepRunResponseModel(StepRunBaseModel, WorkspaceScopedResponseModel):
    """Response model for step runs."""

    input_artifacts: Dict[str, "ArtifactResponseModel"] = {}
    output_artifacts: Dict[str, "ArtifactResponseModel"] = {}
    metadata: Dict[str, "RunMetadataResponseModel"] = Field(
        default={},
        title="Metadata associated with this step run.",
    )
    step_logs: Optional["LogsResponseModel"] = None


# ------ #
# FILTER #
# ------ #


class StepRunFilterModel(WorkspaceScopedFilterModel):
    """Model to enable advanced filtering of all Artifacts."""

    name: Optional[str] = Field(
        default=None,
        description="Name of the step run",
    )
    entrypoint_name: Optional[str] = Field(
        default=None,
        description="Entrypoint name of the step run",
    )
    code_hash: Optional[str] = Field(
        default=None,
        description="Code hash for this step run",
    )
    cache_key: Optional[str] = Field(
        default=None,
        description="Cache key for this step run",
    )
    status: Optional[str] = Field(
        default=None,
        description="Status of the Step Run",
    )
    start_time: Optional[Union[datetime, str]] = Field(
        default=None, description="Start time for this run"
    )
    end_time: Optional[Union[datetime, str]] = Field(
        default=None, description="End time for this run"
    )
    pipeline_run_id: Optional[Union[UUID, str]] = Field(
        default=None, description="Pipeline run of this step run"
    )
    original_step_run_id: Optional[Union[UUID, str]] = Field(
        default=None, description="Original id for this step run"
    )
    user_id: Optional[Union[UUID, str]] = Field(
        default=None, description="User that produced this step run"
    )
    workspace_id: Optional[Union[UUID, str]] = Field(
        default=None, description="Workspace of this step run"
    )
    num_outputs: Optional[int] = Field(
        default=None,
        description="Amount of outputs for this Step Run",
    )


# ------- #
# REQUEST #
# ------- #


class StepRunRequestModel(StepRunBaseModel, WorkspaceScopedRequestModel):
    """Request model for step runs."""

    input_artifacts: Dict[str, UUID] = {}
    output_artifacts: Dict[str, UUID] = {}
    step_logs: Optional["LogsRequestModel"] = None


# ------ #
# UPDATE #
# ------ #


class StepRunUpdateModel(BaseModel):
    """Update model for step runs."""

    output_artifacts: Dict[str, UUID] = {}
    status: Optional[ExecutionStatus] = None
    end_time: Optional[datetime] = None
