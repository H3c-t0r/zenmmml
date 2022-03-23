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
from abc import ABC, abstractmethod
from typing import List, Optional

from zenml.enums import SecretsManagerFlavor
from zenml.secret.base_secret import BaseSecretSchema
from zenml.stack import StackComponent


class BaseSecretsManager(StackComponent, ABC):
    """Base class for all ZenML secrets managers."""

    @property
    @abstractmethod
    def flavor(self) -> SecretsManagerFlavor:
        """The secrets manager flavor."""

    @abstractmethod
    def register_secret(self, secret: "BaseSecretSchema") -> None:
        """Registers a new secret."""

    @abstractmethod
    def get_secret(self, secret_name: str) -> BaseSecretSchema:
        """Gets the value of a secret."""

    @abstractmethod
    def get_all_secret_keys(self) -> List[str]:
        """Get all secret keys."""

    @abstractmethod
    def update_secret(self, secret: BaseSecretSchema) -> None:
        """Update an existing secret."""

    @abstractmethod
    def delete_secret(self, secret_name: str) -> None:
        """Delete an existing secret."""

    @abstractmethod
    def delete_all_secrets(self, force: bool = False) -> None:
        """Delete all existing secrets."""

    @abstractmethod
    def get_value_by_key(self, key: str, secret_name: str) -> Optional[str]:
        """Get value for a particular key within a Secret."""
