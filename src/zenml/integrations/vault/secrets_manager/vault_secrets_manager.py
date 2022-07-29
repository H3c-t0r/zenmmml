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
"""Implementation of the HashiCorp Vault Secrets Manager integration."""
import re
from typing import Any, ClassVar, List, Optional, Set

import hvac  # type: ignore[import]
from hvac.exceptions import InvalidPath

from zenml.constants import ZENML_SCHEMA_NAME
from zenml.exceptions import SecretExistsError
from zenml.integrations.vault import VAULT_SECRETS_MANAGER_FLAVOR
from zenml.logger import get_logger
from zenml.secret.base_secret import BaseSecretSchema
from zenml.secret.secret_schema_class_registry import SecretSchemaClassRegistry
from zenml.secrets_managers.base_secrets_manager import BaseSecretsManager
from zenml.secrets_managers.utils import secret_to_dict

logger = get_logger(__name__)


class VaultSecretsManager(BaseSecretsManager):
    """Class to interact with the Vault secrets manager - Key/value Engine.

    Attributes:
        url: The url of the Vault server.
        token: The token to use to authenticate with Vault.
        cert: The path to the certificate to use to authenticate with Vault.
        verify: Whether to verify the certificate or not.
        mount_point: The mount point of the secrets manager.
    """

    # Class configuration
    FLAVOR: ClassVar[str] = VAULT_SECRETS_MANAGER_FLAVOR
    SUPPORTS_SCOPING: ClassVar[bool] = True
    CLIENT: ClassVar[Any] = None

    url: str
    token: str
    mount_point: str
    cert: Optional[str]
    verify: Optional[str]

    @classmethod
    def _ensure_client_connected(cls, url: str, token: str) -> None:
        """Ensure the client is connected.

        This function initializes the client if it is not initialized.

        Args:
            url: The url of the Vault server.
            token: The token to use to authenticate with Vault.
        """
        if cls.CLIENT is None:
            # Create a Vault Secrets Manager client
            cls.CLIENT = hvac.Client(
                url=url,
                token=token,
            )

    def _ensure_client_is_authenticated(self) -> None:
        """Ensure the client is authenticated.

        Raises:
            RuntimeError: If the client is not initialized or authenticated.
        """
        self._ensure_client_connected(url=self.url, token=self.token)

        if not self.CLIENT.is_authenticated():
            raise RuntimeError(
                "There was an error authenticating with Vault. Please check "
                "your configuration."
            )
        else:
            pass

    def _get_scoped_secret_name(self, name: str) -> str:
        """Convert a ZenML secret name into a Vault scoped secret name.

        Args:
            name: the name of the secret

        Returns:
            The Vault scoped secret name
        """
        return "/".join(self._get_scoped_secret_path(name))

    @staticmethod
    def _sanitize_secret_name(secret_name: str) -> str:
        """Sanitize the secret name to be used in Vault.

        Args:
            secret_name: The secret name to sanitize.

        Returns:
            The sanitized secret name.
        """
        sanitized_secret_name = re.sub(r"[^0-9a-zA-Z_\.]+", "_", secret_name)
        if sanitized_secret_name!=secret_name:
            logger.warning("The Secret name `%s` contains characters that "
                           "might not be supported. The secret name has been "
                           "sanitized to: `%s` ", secret_name,
                           sanitized_secret_name)
        return sanitized_secret_name

    def register_secret(self, secret: BaseSecretSchema) -> None:
        """Registers a new secret.

        Args:
            secret: The secret to register.

        Raises:
            SecretExistsError: If the secret already exists.
        """
        self._ensure_client_is_authenticated()

        sanitized_secret_name = self._sanitize_secret_name(secret.name)

        try:
            self.get_secret(sanitized_secret_name)
        except KeyError:
            raise SecretExistsError(
                f"A Secret with the name '{sanitized_secret_name}' already exists."
            )

        secret_path = self._get_scoped_secret_name(sanitized_secret_name)
        secret_value = secret_to_dict(secret, encode=False)

        self.CLIENT.secrets.kv.v2.create_or_update_secret(
            path=secret_path,
            mount_point=self.mount_point,
            secret=secret_value,
        )

        logger.info("Created secret: %s", f"{secret_path}")
        logger.info("Added value to secret.")

    def get_secret(self, secret_name: str) -> BaseSecretSchema:
        """Gets the value of a secret.

        Args:
            secret_name: The name of the secret to get.

        Returns:
            The secret.

        Raises:
            KeyError: If the secret does not exist.
        """
        self._ensure_client_is_authenticated()

        sanitized_secret_name = self._sanitize_secret_name(secret_name)
        secret_path = self._get_scoped_secret_name(sanitized_secret_name)

        try:
            secret_items = (
                self.CLIENT.secrets.kv.v2.read_secret_version(
                    path=secret_path,
                    mount_point=self.mount_point,
                )
                .get("data", {})
                .get("data", {})
            )
        except InvalidPath as e:
            raise KeyError(e)

        zenml_schema_name = secret_items.pop(ZENML_SCHEMA_NAME)

        secret_schema = SecretSchemaClassRegistry.get_class(
            secret_schema=zenml_schema_name
        )
        secret_items["name"] = secret_name
        return secret_schema(**secret_items)

    def get_all_secret_keys(self) -> List[str]:
        """List all secrets in Vault without any reformatting.

        This function tries to get all secrets from Vault and returns
        them as a list of strings (all secrets' names).

        Returns:
            A list of all secrets in the secrets manager.
        """
        self._ensure_client_is_authenticated()

        set_of_secrets: Set[str] = set()
        secret_path = "/".join(self._get_scope_path())
        try:
            secrets = self.CLIENT.secrets.kv.v2.list_secrets(
                path=secret_path, mount_point=self.mount_point
            )
        except hvac.exceptions.InvalidPath:
            logger.error(
                f"There are no secrets created within the scope `{secret_path}`"
            )
            return list(set_of_secrets)

        secrets_keys = secrets.get("data", {}).get("keys", [])
        for secret_key in secrets_keys:
            # vault scopes end with / and are not themselves secrets
            if "/" not in secret_key:
                set_of_secrets.add(secret_key)
        return list(set_of_secrets)

    def update_secret(self, secret: BaseSecretSchema) -> None:
        """Update an existing secret.

        Args:
            secret: The secret to update.

        Raises:
            KeyError: If the secret does not exist.
        """
        self._ensure_client_is_authenticated()

        sanitized_secret_name = self._sanitize_secret_name(secret.name)

        if sanitized_secret_name in self.get_all_secret_keys():
            secret_path = self._get_scoped_secret_name(sanitized_secret_name)
            secret_value = secret_to_dict(secret, encode=False)

            self.CLIENT.secrets.kv.v2.create_or_update_secret(
                path=secret_path,
                mount_point=self.mount_point,
                secret=secret_value,
            )
        else:
            raise KeyError(
                f"A Secret with the name '{sanitized_secret_name}'"
                f" does not exist."
            )

        logger.info("Updated secret: %s", secret_path)
        logger.info("Added value to secret.")

    def delete_secret(self, secret_name: str) -> None:
        """Delete an existing secret.

        Args:
            secret_name: The name of the secret to delete.
        """
        self._ensure_client_is_authenticated()

        sanitized_secret_name = self._sanitize_secret_name(secret_name)
        secret_path = self._get_scoped_secret_name(sanitized_secret_name)

        self.CLIENT.secrets.kv.v2.delete_metadata_and_all_versions(
            path=secret_path,
            mount_point=self.mount_point,
        )

        logger.info("Deleted secret: %s", f"{secret_path}")

    def delete_all_secrets(self) -> None:
        """Delete all existing secrets."""
        self._ensure_client_is_authenticated()

        for secret_name in self.get_all_secret_keys():
            self.delete_secret(secret_name)

        logger.info("Deleted all secrets.")
