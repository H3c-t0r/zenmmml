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
"""Models representing code references."""
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from pydantic import Field

from zenml.new_models.base import (
    BaseRequestModel,
    BaseResponseModel,
    BaseResponseModelMetadata,
)

if TYPE_CHECKING:
    from zenml.new_models.code_repository_models import (
        CodeRepositoryResponseModel,
    )


# ------------------ Request Model ------------------


class CodeReferenceRequestModel(BaseRequestModel):
    """Request model for code references."""
    commit: str = Field(description="The commit of the code reference.")
    subdirectory: str = Field(
        description="The subdirectory of the code reference."
    )
    code_repository: UUID = Field(
        description="The repository of the code reference."
    )


# ------------------ Update Model ------------------

# There is no update model for code references.


# ------------------ Response Model ------------------


class CodeReferenceResponseMetadataModel(BaseResponseModelMetadata):
    """Response metadata model for code references."""


class CodeReferenceResponseModel(BaseResponseModel):
    """Response model for code references."""

    # Entity fields
    commit: str = Field(description="The commit of the code reference.")
    subdirectory: str = Field(
        description="The subdirectory of the code reference."
    )
    code_repository: "CodeRepositoryResponseModel" = Field(
        description="The repository of the code reference."
    )

    # Metadata related field, method and properties
    metadata: Optional["CodeReferenceResponseMetadataModel"]

    def get_hydrated_version(self) -> "CodeReferenceResponseModel":
        # TODO: Implement it with the parameterized calls
        from zenml.client import Client

        return Client().get_code_reference(self.id, hydrate=True)
