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
"""Models representing users."""

from secrets import token_hex
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Dict,
    List,
    Optional,
    Type,
    Union,
)
from uuid import UUID

from pydantic import Field, root_validator

from zenml.constants import STR_FIELD_MAX_LENGTH
from zenml.models.v2.base.base import (
    BaseRequest,
    BaseResponse,
    BaseResponseBody,
    BaseResponseMetadata,
)
from zenml.models.v2.base.filter import BaseFilter
from zenml.models.v2.base.update import update_model

if TYPE_CHECKING:
    from passlib.context import CryptContext
    from sqlmodel.sql.expression import Select, SelectOfScalar

    from zenml.models.v2.base.filter import AnySchema
    from zenml.models.v2.core.role import RoleResponse
    from zenml.models.v2.core.team import TeamResponse

# ------------------ Request Model ------------------


class UserRequest(BaseRequest):
    """Request model for users."""

    # Analytics fields for user request models
    ANALYTICS_FIELDS: ClassVar[List[str]] = [
        "name",
        "full_name",
        "active",
        "email_opted_in",
    ]

    # Fields
    name: str = Field(
        title="The unique username for the account.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    full_name: str = Field(
        default="",
        title="The full name for the account owner. Only relevant for user "
        "accounts.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    email: Optional[str] = Field(
        default=None,
        title="The email address associated with the account.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    email_opted_in: Optional[bool] = Field(
        default=None,
        title="Whether the user agreed to share their email. Only relevant for "
        "user accounts",
        description="`null` if not answered, `true` if agreed, "
        "`false` if skipped.",
    )
    hub_token: Optional[str] = Field(
        default=None,
        title="JWT Token for the connected Hub account. Only relevant for user "
        "accounts.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    password: Optional[str] = Field(
        default=None,
        title="A password for the user.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    activation_token: Optional[str] = Field(
        default=None, max_length=STR_FIELD_MAX_LENGTH
    )
    external_user_id: Optional[UUID] = Field(
        default=None,
        title="The external user ID associated with the account.",
    )
    active: bool = Field(default=False, title="Whether the account is active.")

    class Config:
        """Pydantic configuration class."""

        # Validate attributes when assigning them
        validate_assignment = True

        # Forbid extra attributes to prevent unexpected behavior
        extra = "forbid"
        underscore_attrs_are_private = True

    @classmethod
    def _get_crypt_context(cls) -> "CryptContext":
        """Returns the password encryption context.

        Returns:
            The password encryption context.
        """
        from passlib.context import CryptContext

        return CryptContext(schemes=["bcrypt"], deprecated="auto")

    @classmethod
    def _create_hashed_secret(cls, secret: Optional[str]) -> Optional[str]:
        """Hashes the input secret and returns the hash value.

        Only applied if supplied and if not already hashed.

        Args:
            secret: The secret value to hash.

        Returns:
            The secret hash value, or None if no secret was supplied.
        """
        if secret is None:
            return None
        pwd_context = cls._get_crypt_context()
        return pwd_context.hash(secret)

    def create_hashed_password(self) -> Optional[str]:
        """Hashes the password.

        Returns:
            The hashed password.
        """
        return self._create_hashed_secret(self.password)

    def create_hashed_activation_token(self) -> Optional[str]:
        """Hashes the activation token.

        Returns:
            The hashed activation token.
        """
        return self._create_hashed_secret(self.activation_token)

    def generate_activation_token(self) -> str:
        """Generates and stores a new activation token.

        Returns:
            The generated activation token.
        """
        self.activation_token = token_hex(32)
        return self.activation_token


# ------------------ Update Model ------------------


@update_model
class UserUpdate(UserRequest):
    """Update model for users."""

    @root_validator
    def user_email_updates(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """Validate that the UserUpdateModel conforms to the email-opt-in-flow.

        Args:
            values: The values to validate.

        Returns:
            The validated values.

        Raises:
            ValueError: If the email was not provided when the email_opted_in
                field was set to True.
        """
        # When someone sets the email, or updates the email and hasn't
        #  before explicitly opted out, they are opted in
        if values["email"] is not None:
            if values["email_opted_in"] is None:
                values["email_opted_in"] = True

        # It should not be possible to do opt in without an email
        if values["email_opted_in"] is True:
            if values["email"] is None:
                raise ValueError(
                    "Please provide an email, when you are opting-in with "
                    "your email."
                )
        return values


# ------------------ Response Model ------------------


class UserResponseBody(BaseResponseBody):
    """Response body for users."""


class UserResponseMetadata(BaseResponseMetadata):
    """Response metadata for users."""

    full_name: str = Field(
        default="",
        title="The full name for the account owner. Only relevant for user "
        "accounts.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    email: Optional[str] = Field(
        default="",
        title="The email address associated with the account. Only relevant "
        "for user accounts.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    email_opted_in: Optional[bool] = Field(
        default=None,
        title="Whether the user agreed to share their email. Only relevant for "
        "user accounts",
        description="`null` if not answered, `true` if agreed, "
        "`false` if skipped.",
    )
    active: bool = Field(default=False, title="Whether the account is active.")
    activation_token: Optional[str] = Field(
        default=None,
        max_length=STR_FIELD_MAX_LENGTH,
        title="The activation token for the user. Only relevant for user "
        "accounts.",
    )
    hub_token: Optional[str] = Field(
        default=None,
        title="JWT Token for the connected Hub account. Only relevant for user "
        "accounts.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    external_user_id: Optional[UUID] = Field(
        default=None,
        title="The external user ID associated with the account. Only relevant "
        "for user accounts.",
    )
    roles: Optional[List["RoleResponse"]] = Field(
        default=None, title="The list of roles for this user."
    )
    teams: Optional[List["TeamResponse"]] = Field(
        default=None, title="The list of teams for this user."
    )
    is_service_account: bool = Field(
        title="Indicates whether this is a service account or a user account."
    )


class UserResponse(BaseResponse[UserResponseBody, UserResponseMetadata]):
    """Response model for user and service accounts.

    This returns the activation_token that is required for the
    user-invitation-flow of the frontend. This also optionally includes the
    team the user is a part of. The email is returned optionally as well
    for use by the analytics on the client-side.
    """

    ANALYTICS_FIELDS: ClassVar[List[str]] = [
        "name",
        "full_name",
        "active",
        "email_opted_in",
        "is_service_account",
    ]

    name: str = Field(
        title="The unique username for the account.",
        max_length=STR_FIELD_MAX_LENGTH,
    )

    def get_hydrated_version(self) -> "UserResponse":
        """Get the hydrated version of this user."""
        from zenml.client import Client

        return Client().zen_store.get_user(self.id)

    # Body and metadata properties
    @property
    def full_name(self) -> str:
        """The `full_name` property."""
        return self.get_metadata().full_name

    @property
    def email(self) -> Optional[str]:
        """The `email` property."""
        return self.get_metadata().email

    @property
    def email_opted_in(self) -> Optional[bool]:
        """The `email_opted_in` property."""
        return self.get_metadata().email_opted_in

    @property
    def active(self) -> bool:
        """The `active` property."""
        return self.get_metadata().active

    @property
    def activation_token(self) -> Optional[str]:
        """The `activation_token` property."""
        return self.get_metadata().activation_token

    @property
    def hub_token(self) -> Optional[str]:
        """The `hub_token` property."""
        return self.get_metadata().hub_token

    @property
    def external_user_id(self) -> Optional[UUID]:
        """The `external_user_id` property."""
        return self.get_metadata().external_user_id

    @property
    def roles(self) -> Optional[List["RoleResponse"]]:
        """The `roles` property."""
        return self.get_metadata().roles

    @property
    def teams(self) -> Optional[List["TeamResponse"]]:
        """The `teams` property."""
        return self.get_metadata().teams

    @property
    def is_service_account(self) -> bool:
        """The `is_service_account` property."""
        return self.get_metadata().is_service_account

    # Helper methods
    @classmethod
    def _get_crypt_context(cls) -> "CryptContext":
        """Returns the password encryption context.

        Returns:
            The password encryption context.
        """
        from passlib.context import CryptContext

        return CryptContext(schemes=["bcrypt"], deprecated="auto")


# ------------------ Filter Model ------------------


class UserFilter(BaseFilter):
    """Model to enable advanced filtering of all Users."""

    name: Optional[str] = Field(
        default=None,
        description="Name of the user",
    )
    full_name: Optional[str] = Field(
        default=None,
        description="Full Name of the user",
    )
    email: Optional[str] = Field(
        default=None,
        description="Email of the user",
    )
    active: Optional[Union[bool, str]] = Field(
        default=None,
        description="Whether the user is active",
    )
    email_opted_in: Optional[Union[bool, str]] = Field(
        default=None,
        description="Whether the user has opted in to emails",
    )
    external_user_id: Optional[Union[UUID, str]] = Field(
        default=None,
        title="The external user ID associated with the account.",
    )

    def apply_filter(
        self,
        query: Union["Select[AnySchema]", "SelectOfScalar[AnySchema]"],
        table: Type["AnySchema"],
    ) -> Union["Select[AnySchema]", "SelectOfScalar[AnySchema]"]:
        """Override to filter out service accounts from the query.

        Args:
            query: The query to which to apply the filter.
            table: The query table.

        Returns:
            The query with filter applied.
        """
        query = super().apply_filter(query=query, table=table)
        query = query.where(
            getattr(table, "is_service_account") != True  # noqa: E712
        )

        return query
