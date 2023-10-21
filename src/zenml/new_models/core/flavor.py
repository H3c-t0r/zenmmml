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
"""Models representing flavors."""

from typing import TYPE_CHECKING, Any, ClassVar, Dict, List, Optional, Union
from uuid import UUID

from pydantic import Field

from zenml.constants import STR_FIELD_MAX_LENGTH
from zenml.enums import StackComponentType
from zenml.new_models.base import (
    BaseRequest,
    BaseResponse,
    BaseResponseBody,
    BaseResponseMetadata,
    WorkspaceScopedFilter,
    hydrated_property,
    update_model,
)

if TYPE_CHECKING:
    from zenml.new_models.core.user import UserResponse
    from zenml.new_models.core.workspace import WorkspaceResponse
    from zenml.new_models.service_connector_type import (
        ServiceConnectorRequirements,
    )

# ------------------ Request Model ------------------


class FlavorRequest(BaseRequest):
    """Request model for flavors"""

    ANALYTICS_FIELDS: ClassVar[List[str]] = [
        "type",
        "integration",
    ]

    name: str = Field(
        title="The name of the Flavor.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    type: StackComponentType = Field(title="The type of the Flavor.")
    config_schema: Dict[str, Any] = Field(
        title="The JSON schema of this flavor's corresponding configuration.",
    )
    connector_type: Optional[str] = Field(
        default=None,
        title="The type of the connector that this flavor uses.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    connector_resource_type: Optional[str] = Field(
        default=None,
        title="The resource type of the connector that this flavor uses.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    connector_resource_id_attr: Optional[str] = Field(
        default=None,
        title="The name of an attribute in the stack component configuration "
        "that plays the role of resource ID when linked to a service "
        "connector.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    source: str = Field(
        title="The path to the module which contains this Flavor.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    integration: Optional[str] = Field(
        title="The name of the integration that the Flavor belongs to.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    logo_url: Optional[str] = Field(
        default=None,
        title="Optionally, a url pointing to a png,"
        "svg or jpg can be attached.",
    )
    docs_url: Optional[str] = Field(
        default=None,
        title="Optionally, a url pointing to docs, within docs.zenml.io.",
    )
    sdk_docs_url: Optional[str] = Field(
        default=None,
        title="Optionally, a url pointing to SDK docs,"
        "within sdkdocs.zenml.io.",
    )
    is_custom: bool = Field(
        title="Whether or not this flavor is a custom, user created flavor.",
        default=True,
    )
    user: Optional[UUID] = Field(
        default=None, title="The id of the user that created this resource."
    )
    workspace: Optional[UUID] = Field(
        default=None, title="The workspace to which this resource belongs."
    )


# ------------------ Update Model ------------------


@update_model
class FlavorUpdate(FlavorRequest):
    """Update model for flavors."""


# ------------------ Response Model ------------------


class FlavorResponseBody(BaseResponseBody):
    """Response body for flavor."""

    user: Union["UserResponse", None] = Field(
        title="The user that created this resource.", nullable=True
    )
    type: StackComponentType = Field(title="The type of the Flavor.")
    integration: Optional[str] = Field(
        title="The name of the integration that the Flavor belongs to.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    logo_url: Optional[str] = Field(
        default=None,
        title="Optionally, a url pointing to a png,"
        "svg or jpg can be attached.",
    )


class FlavorResponseMetadata(BaseResponseMetadata):
    """Response metadata for flavors"""

    workspace: Optional["WorkspaceResponse"] = Field(
        title="The project of this resource."
    )
    config_schema: Dict[str, Any] = Field(
        title="The JSON schema of this flavor's corresponding configuration.",
    )
    connector_type: Optional[str] = Field(
        default=None,
        title="The type of the connector that this flavor uses.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    connector_resource_type: Optional[str] = Field(
        default=None,
        title="The resource type of the connector that this flavor uses.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    connector_resource_id_attr: Optional[str] = Field(
        default=None,
        title="The name of an attribute in the stack component configuration "
        "that plays the role of resource ID when linked to a service "
        "connector.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    source: str = Field(
        title="The path to the module which contains this Flavor.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    docs_url: Optional[str] = Field(
        default=None,
        title="Optionally, a url pointing to docs, within docs.zenml.io.",
    )
    sdk_docs_url: Optional[str] = Field(
        default=None,
        title="Optionally, a url pointing to SDK docs,"
        "within sdkdocs.zenml.io.",
    )
    is_custom: bool = Field(
        title="Whether or not this flavor is a custom, user created flavor.",
        default=True,
    )


class FlavorResponse(BaseResponse):
    """Response model for flavors"""

    # Analytics
    ANALYTICS_FIELDS: ClassVar[List[str]] = [
        "id",
        "type",
        "integration",
    ]

    name: str = Field(
        title="The name of the Flavor.",
        max_length=STR_FIELD_MAX_LENGTH,
    )

    # Body and metadata pair
    body: "FlavorResponseBody"
    metadata: Optional["FlavorResponseMetadata"]

    def get_hydrated_version(self) -> "FlavorResponse":
        """Get the hydrated version of the flavor"""
        from zenml.client import Client

        return Client().get_flavor(self.id)

    # Helper methods
    @property
    def connector_requirements(
        self,
    ) -> Optional["ServiceConnectorRequirements"]:
        """Returns the connector requirements for the flavor.

        Returns:
            The connector requirements for the flavor.
        """
        from zenml.new_models.service_connector_type import (
            ServiceConnectorRequirements,
        )

        if not self.connector_resource_type:
            return None

        return ServiceConnectorRequirements(
            connector_type=self.connector_type,
            resource_type=self.connector_resource_type,
            resource_id_attr=self.connector_resource_id_attr,
        )

    # Body and metadata properties
    @property
    def user(self):
        """The `user` property."""
        return self.body.user

    @property
    def type(self):
        """The `type` property."""
        return self.body.type

    @property
    def integration(self):
        """The `integration` property."""
        return self.body.integration

    @property
    def logo_url(self):
        """The `logo_url` property."""
        return self.body.logo_url

    @hydrated_property
    def workspace(self):
        """The `workspace` property."""
        return self.metadata.workspace

    @hydrated_property
    def config_schema(self):
        """The `config_schema` property."""
        return self.metadata.config_schema

    @hydrated_property
    def connector_type(self):
        """The `connector_type` property."""
        return self.metadata.connector_type

    @hydrated_property
    def connector_resource_type(self):
        """The `connector_resource_type` property."""
        return self.metadata.connector_resource_type

    @hydrated_property
    def connector_resource_id_attr(self):
        """The `connector_resource_id_attr` property."""
        return self.metadata.connector_resource_id_attr

    @hydrated_property
    def source(self):
        """The `source` property."""
        return self.metadata.source

    @hydrated_property
    def docs_url(self):
        """The `docs_url` property."""
        return self.metadata.docs_url

    @hydrated_property
    def sdk_docs_url(self):
        """The `sdk_docs_url` property."""
        return self.metadata.sdk_docs_url

    @hydrated_property
    def is_custom(self):
        """The `is_custom` property."""
        return self.metadata.is_custom


# ------------------ Filter Model ------------------


class FlavorFilter(WorkspaceScopedFilter):
    """Model to enable advanced filtering of all Flavors."""

    name: Optional[str] = Field(
        default=None,
        description="Name of the flavor",
    )
    type: Optional[str] = Field(
        default=None,
        description="Stack Component Type of the stack flavor",
    )
    integration: Optional[str] = Field(
        default=None,
        description="Integration associated with the flavor",
    )
    workspace_id: Optional[Union[UUID, str]] = Field(
        default=None, description="Workspace of the stack"
    )
    user_id: Optional[Union[UUID, str]] = Field(
        default=None, description="User of the stack"
    )
