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
"""SQL Model Implementations for Pipeline Schedules."""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

from sqlmodel import Field, Relationship

from zenml.models.schedule_model import (
    ScheduleRequestModel,
    ScheduleResponseModel,
    ScheduleUpdateModel,
)
from zenml.zen_stores.schemas.base_schemas import NamedSchema
from zenml.zen_stores.schemas.component_schemas import StackComponentSchema
from zenml.zen_stores.schemas.pipeline_schemas import PipelineSchema
from zenml.zen_stores.schemas.project_schemas import ProjectSchema
from zenml.zen_stores.schemas.schema_utils import build_foreign_key_field
from zenml.zen_stores.schemas.user_schemas import UserSchema

if TYPE_CHECKING:
    from zenml.zen_stores.schemas.pipeline_run_schemas import PipelineRunSchema


class ScheduleSchema(NamedSchema, table=True):
    """SQL Model for schedules."""

    __tablename__ = "schedule"

    project_id: UUID = build_foreign_key_field(
        source=__tablename__,
        target=ProjectSchema.__tablename__,
        source_column="project_id",
        target_column="id",
        ondelete="CASCADE",
        nullable=False,
    )
    project: "ProjectSchema" = Relationship(back_populates="schedules")

    user_id: Optional[UUID] = build_foreign_key_field(
        source=__tablename__,
        target=UserSchema.__tablename__,
        source_column="user_id",
        target_column="id",
        ondelete="SET NULL",
        nullable=True,
    )
    user: "UserSchema" = Relationship(back_populates="schedules")

    pipeline_id: Optional[UUID] = build_foreign_key_field(
        source=__tablename__,
        target=PipelineSchema.__tablename__,
        source_column="pipeline_id",
        target_column="id",
        ondelete="CASCADE",
        nullable=True,
    )
    pipeline: "PipelineSchema" = Relationship(back_populates="schedules")

    orchestrator_id: Optional[UUID] = build_foreign_key_field(
        source=__tablename__,
        target=StackComponentSchema.__tablename__,
        source_column="orchestrator_id",
        target_column="id",
        ondelete="SET NULL",
        nullable=True,
    )
    orchestrator: "StackComponentSchema" = Relationship(
        back_populates="schedules"
    )

    active: bool
    cron_expression: Optional[str] = Field(nullable=True)
    start_time: Optional[datetime] = Field(nullable=True)
    end_time: Optional[datetime] = Field(nullable=True)
    interval_second: Optional[float] = Field(nullable=True)
    catchup: bool

    runs: List["PipelineRunSchema"] = Relationship(
        back_populates="schedule",
    )

    @classmethod
    def from_create_model(cls, model: ScheduleRequestModel) -> "ScheduleSchema":
        """Create a `ScheduleSchema` from a `ScheduleRequestModel`.

        Args:
            model: The `ScheduleRequestModel` to create the schema from.

        Returns:
            The created `ScheduleSchema`.
        """
        if model.interval_second is not None:
            interval_second = model.interval_second.total_seconds()
        else:
            interval_second = None
        return cls(
            name=model.name,
            project_id=model.project,
            user_id=model.user,
            pipeline_id=model.pipeline_id,
            orchestrator_id=model.orchestrator_id,
            active=model.active,
            cron_expression=model.cron_expression,
            start_time=model.start_time,
            end_time=model.end_time,
            interval_second=interval_second,
            catchup=model.catchup,
        )

    def from_update_model(self, model: ScheduleUpdateModel) -> "ScheduleSchema":
        """Update a `ScheduleSchema` from a `ScheduleUpdateModel`.

        Args:
            model: The `ScheduleUpdateModel` to update the schema from.

        Returns:
            The updated `ScheduleSchema`.
        """
        if model.interval_second is not None:
            interval_second = model.interval_second.total_seconds()
        else:
            interval_second = None
        self.name = model.name
        self.active = model.active
        self.cron_expression = model.cron_expression
        self.start_time = model.start_time
        self.end_time = model.end_time
        self.interval_second = interval_second
        self.catchup = model.catchup
        self.updated = datetime.now()
        return self

    def to_model(self) -> ScheduleResponseModel:
        """Convert a `ScheduleSchema` to a `ScheduleResponseModel`.

        Returns:
            The created `ScheduleResponseModel`.
        """
        if self.interval_second is not None:
            interval_second = timedelta(seconds=self.interval_second)
        else:
            interval_second = None
        return ScheduleResponseModel(
            id=self.id,
            name=self.name,
            project=self.project.to_model(),
            user=self.user.to_model(),
            pipeline_id=self.pipeline_id,
            orchestrator_id=self.orchestrator_id,
            active=self.active,
            cron_expression=self.cron_expression,
            start_time=self.start_time,
            end_time=self.end_time,
            interval_second=interval_second,
            catchup=self.catchup,
            created=self.created,
            updated=self.updated,
        )
