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
"""SQLModel implementation of server settings tables."""

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import TEXT, Column
from sqlmodel import Field, SQLModel

from zenml.constants import (
    DEFAULT_DISPLAY_USER_SURVEYS,
    DEFAULT_DISPLAY_WHATS_NEW,
    DEFAULT_SERVER_NAME,
)
from zenml.models import (
    ServerSettingsResponse,
    ServerSettingsResponseBody,
    ServerSettingsResponseMetadata,
    ServerSettingsResponseResources,
    ServerSettingsUpdate,
)


class ServerSettingsSchema(SQLModel, table=True):
    """SQL Model for settings."""

    __tablename__ = "server_settings"

    name: str = Field(default=DEFAULT_SERVER_NAME, primary_key=True)
    display_whats_new: bool = DEFAULT_DISPLAY_WHATS_NEW
    display_user_surveys: bool = DEFAULT_DISPLAY_USER_SURVEYS
    onboarding_state: Optional[str] = Field(
        default=None, sa_column=Column(TEXT, nullable=True)
    )
    updated: datetime = Field(default_factory=datetime.utcnow)

    def update(
        self, server_settings_update: ServerSettingsUpdate
    ) -> "ServerSettingsSchema":
        """Update a `ServerSettingsSchema` from a `ServerSettingsUpdate`.

        Args:
            server_settings_update: The `ServerSettingsUpdate` from which
                to update the schema.

        Returns:
            The updated `ServerSettingsSchema`.
        """
        for field, value in server_settings_update.dict(
            exclude_unset=True
        ).items():
            if field == "onboarding_state":
                if value is not None:
                    setattr(self, field, json.dumps(value))
            else:
                setattr(self, field, value)

        self.updated = datetime.utcnow()

        return self

    def to_model(
        self,
        include_metadata: bool = False,
        include_resources: bool = False,
        **kwargs: Any,
    ) -> ServerSettingsResponse:
        """Convert an `ServerSettingsSchema` to an `ServerSettingsResponse`.

        Args:
            include_metadata: Whether the metadata will be filled.
            include_resources: Whether the resources will be filled.
            **kwargs: Keyword arguments to allow schema specific logic


        Returns:
            The created `ServerSettingsResponse`.
        """
        body = ServerSettingsResponseBody(
            name=self.name,
            display_whats_new=self.display_whats_new,
            display_user_surveys=self.display_user_surveys,
            onboarding_state=json.loads(self.onboarding_state)
            if self.onboarding_state
            else {},
        )

        metadata = None
        resources = None

        if include_metadata:
            metadata = ServerSettingsResponseMetadata()

        if include_resources:
            resources = ServerSettingsResponseResources()

        return ServerSettingsResponse(
            body=body, metadata=metadata, resources=resources
        )
