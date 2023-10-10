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

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Dict, Optional
from uuid import UUID

from pydantic import Field

from zenml.new_models.base.base_models import (
    BaseRequestModel,
    BaseResponseModel,
    BaseResponseModelMetadata,
)
from zenml.new_models.base.utils import hydrated_property

if TYPE_CHECKING:
    from zenml.new_models.core.user_models import UserResponseModel
    from zenml.new_models.core.workspace_models import WorkspaceResponseModel


# ---------------------- Request Models ----------------------


class UserScopedRequestModel(BaseRequestModel):
    """Base user-owned request model.

    Used as a base class for all domain models that are "owned" by a user.
    """

    user: UUID = Field(title="The id of the user that created this resource.")

    def get_analytics_metadata(self) -> Dict[str, Any]:
        """Fetches the analytics metadata for user scoped models.

        Returns:
            The analytics metadata.
        """
        metadata = super().get_analytics_metadata()
        metadata["user_id"] = self.user
        return metadata


class WorkspaceScopedRequestModel(UserScopedRequestModel):
    """Base workspace-scoped request domain model.

    Used as a base class for all domain models that are workspace-scoped.
    """

    workspace: UUID = Field(
        title="The workspace to which this resource belongs."
    )

    def get_analytics_metadata(self) -> Dict[str, Any]:
        """Fetches the analytics metadata for workspace scoped models.

        Returns:
            The analytics metadata.
        """
        metadata = super().get_analytics_metadata()
        metadata["workspace_id"] = self.workspace
        return metadata


class ShareableRequestModel(WorkspaceScopedRequestModel):
    """Base shareable workspace-scoped domain model.

    Used as a base class for all domain models that are workspace-scoped and are
    shareable.
    """

    is_shared: bool = Field(
        default=False,
        title=(
            "Flag describing if this resource is shared with other users in "
            "the same workspace."
        ),
    )

    def get_analytics_metadata(self) -> Dict[str, Any]:
        """Fetches the analytics metadata for workspace scoped models.

        Returns:
            The analytics metadata.
        """
        metadata = super().get_analytics_metadata()
        metadata["is_shared"] = self.is_shared
        return metadata


# ---------------------- Response Models ----------------------


# User-scoped models
class UserScopedResponseMetadataModel(BaseResponseModelMetadata):
    """Base user-owned metadata model."""


class UserScopedResponseModel(BaseResponseModel):
    """Base user-owned domain model.

    Used as a base class for all domain models that are "owned" by a user.
    """

    # Entity fields
    user: Optional["UserResponseModel"] = Field(
        title="The user who created this resource."
    )

    # Metadata related field, method and properties
    metadata: Optional["UserScopedResponseMetadataModel"] = Field(
        title="The metadata related to this resource."
    )

    @abstractmethod
    def get_hydrated_version(self) -> "UserScopedResponseModel":
        """Abstract method that needs to be implemented to hydrate the instance.

        Each response model has a metadata field. The purpose of this
        is to populate this field by making an additional call to the API.
        """

    # Analytics
    def get_analytics_metadata(self) -> Dict[str, Any]:
        """Fetches the analytics metadata for user scoped models.

        Returns:
            The analytics metadata.
        """
        metadata = super().get_analytics_metadata()
        if self.user is not None:
            metadata["user_id"] = self.user.id
        return metadata


# Workspace-scoped models
class WorkspaceScopedResponseMetadataModel(UserScopedResponseMetadataModel):
    """Base workspace-scoped metadata model."""

    workspace: "WorkspaceResponseModel" = Field(
        title="The workspace of this resource."
    )


class WorkspaceScopedResponseModel(UserScopedResponseModel):
    """Base workspace-scoped domain model.

    Used as a base class for all domain models that are workspace-scoped.
    """

    # Metadata related field, method and properties
    metadata: Optional["WorkspaceScopedResponseMetadataModel"]

    @abstractmethod
    def get_hydrated_version(self) -> "WorkspaceScopedResponseModel":
        """Abstract method that needs to be implemented to hydrate the instance.

        Each response model has a metadata field. The purpose of this
        is to populate this field by making an additional call to the API.
        """

    @hydrated_property
    def workspace(self):
        """The workspace property."""
        return self.metadata.workspace


# Shareable models
class SharableResponseMetadataModel(WorkspaceScopedResponseMetadataModel):
    """Base shareable workspace-scoped metadata model."""


class ShareableResponseModel(WorkspaceScopedResponseModel):
    """Base shareable workspace-scoped domain model.

    Used as a base class for all domain models that are workspace-scoped and are
    shareable.
    """

    # Entity properties
    is_shared: bool = Field(
        title=(
            "Flag describing if this resource is shared with other users in "
            "the same workspace."
        ),
    )
    # Metadata related field, method and properties
    metadata: Optional["SharableResponseMetadataModel"]

    @abstractmethod
    def get_hydrated_version(self) -> "ShareableResponseModel":
        """Abstract method that needs to be implemented to hydrate the instance.

        Each response model has a metadata field. The purpose of this
        is to populate this field by making an additional call to the API.
        """

    # Analytics
    def get_analytics_metadata(self) -> Dict[str, Any]:
        """Fetches the analytics metadata for workspace scoped models.

        Returns:
            The analytics metadata.
        """
        metadata = super().get_analytics_metadata()
        metadata["is_shared"] = self.is_shared
        return metadata
