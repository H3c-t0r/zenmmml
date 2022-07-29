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
"""Implementation of the Azure Secrets Manager integration."""

import base64
from typing import Any, ClassVar, List

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

from zenml.exceptions import SecretExistsError
from zenml.integrations.azure import AZURE_SECRETS_MANAGER_FLAVOR
from zenml.logger import get_logger
from zenml.secret.base_secret import BaseSecretSchema
from zenml.secret.secret_schema_class_registry import SecretSchemaClassRegistry
from zenml.secrets_managers.base_secrets_manager import BaseSecretsManager, SecretsManagerScope

logger = get_logger(__name__)

ZENML_SCHEMA_NAME = "zenml-schema-name"
ZENML_GROUP_KEY = "zenml-group-key"
ZENML_KEY_NAME = "zenml-key-name"


class AzureSecretsManager(BaseSecretsManager):
    """Class to interact with the Azure secrets manager.

    Attributes:
        key_vault_name: Name of an Azure Key Vault that this secrets manager
            will use to store secrets.
    """

    key_vault_name: str

    # Class configuration
    FLAVOR: ClassVar[str] = AZURE_SECRETS_MANAGER_FLAVOR
    CLIENT: ClassVar[Any] = None


    def _validate_scope(cls, scope: SecretsManagerScope) -> None:
        """Validate the scope value.

        Subclasses should override this method to implement their own scope
        validation logic (e.g. raise an exception if a scope is not supported
        or log a warning if a deprecated scope is used).

        Args:
            scope: Scope value.
        """
        if scope != SecretsManagerScope.NONE:
            logger.warning(
                f"Unscoped support for the {cls.FLAVOR} Secrets Manager is "
                f"deprecated and will be removed in a future release. You "
                f"should use the `global` scope instead."
            )

    @classmethod
    def _ensure_client_connected(cls, vault_name: str) -> None:
        if cls.CLIENT is None:
            KVUri = f"https://{vault_name}.vault.azure.net"

            credential = DefaultAzureCredential()
            cls.CLIENT = SecretClient(vault_url=KVUri, credential=credential)

    def register_secret(self, secret: BaseSecretSchema) -> None:
        """Registers a new secret.

        Args:
            secret: the secret to register

        Raises:
            SecretExistsError: if the secret already exists
        """
        self._ensure_client_connected(self.key_vault_name)

        if secret.name in self.get_all_secret_keys():
            raise SecretExistsError(
                f"A Secret with the name '{secret.name}' already exists."
            )

        self.update_secret(secret)

    def get_secret(self, secret_name: str) -> BaseSecretSchema:
        """Get a secret by its name.

        Args:
            secret_name: the name of the secret to get

        Returns:
            The secret.

        Raises:
            RuntimeError: if the secret does not exist
            ValueError: if the secret is named 'name'
        """
        self._ensure_client_connected(self.key_vault_name)

        secret_contents = {}
        zenml_schema_name = ""

        for secret_property in self.CLIENT.list_properties_of_secrets():
            tags = secret_property.tags

            if tags and tags.get(ZENML_GROUP_KEY) == secret_name:
                secret_key = tags.get(ZENML_KEY_NAME)
                if not secret_key:
                    raise ValueError("Missing secret key tag.")

                if secret_key == "name":
                    raise ValueError("The secret's key cannot be 'name'.")

                response = self.CLIENT.get_secret(secret_property.name)
                secret_contents[secret_key] = response.value

                zenml_schema_name = tags.get(ZENML_SCHEMA_NAME)

        if not secret_contents:
            raise RuntimeError(f"No secrets found within the {secret_name}")

        secret_contents["name"] = secret_name

        secret_schema = SecretSchemaClassRegistry.get_class(
            secret_schema=zenml_schema_name
        )
        return secret_schema(**secret_contents)

    def get_all_secret_keys(self) -> List[str]:
        """Get all secret keys.

        Returns:
            A list of all secret keys
        """
        self._ensure_client_connected(self.key_vault_name)

        set_of_secrets = set()

        for secret_property in self.CLIENT.list_properties_of_secrets():
            tags = secret_property.tags
            if tags and ZENML_GROUP_KEY in tags:
                set_of_secrets.add(tags.get(ZENML_GROUP_KEY))

        return list(set_of_secrets)

    def update_secret(self, secret: BaseSecretSchema) -> None:
        """Update an existing secret by creating new versions of the existing secrets.

        Args:
            secret: the secret to update
        """
        self._ensure_client_connected(self.key_vault_name)

        for key, value in secret.content.items():
            encoded_key = base64.b64encode(
                f"{secret.name}-{key}".encode()
            ).hex()
            azure_secret_name = f"zenml-{encoded_key}"

            self.CLIENT.set_secret(azure_secret_name, value)
            self.CLIENT.update_secret_properties(
                azure_secret_name,
                tags={
                    ZENML_GROUP_KEY: secret.name,
                    ZENML_KEY_NAME: key,
                    ZENML_SCHEMA_NAME: secret.TYPE,
                },
            )

            logger.debug("Wrote secret: %s", azure_secret_name)

    def delete_secret(self, secret_name: str) -> None:
        """Delete an existing secret. by name.

        In Azure a secret is a single k-v pair. Within ZenML a secret is a
        collection of k-v pairs. As such, deleting a secret will iterate through
        all secrets and delete the ones with the secret_name as label.

        Args:
            secret_name: the name of the secret to delete
        """
        self._ensure_client_connected(self.key_vault_name)

        # Go through all Azure secrets and delete the ones with the secret_name
        #  as label.
        for secret_property in self.CLIENT.list_properties_of_secrets():
            response = self.CLIENT.get_secret(secret_property.name)
            tags = response.properties.tags
            if tags and tags.get(ZENML_GROUP_KEY) == secret_name:
                self.CLIENT.begin_delete_secret(secret_property.name).result()

    def delete_all_secrets(self) -> None:
        """Delete all existing secrets."""
        self._ensure_client_connected(self.key_vault_name)

        # List all secrets.
        for secret_property in self.CLIENT.list_properties_of_secrets():
            response = self.CLIENT.get_secret(secret_property.name)
            tags = response.properties.tags
            if tags and (ZENML_GROUP_KEY in tags or ZENML_SCHEMA_NAME in tags):
                logger.info(
                    "Deleted key-value pair {`%s`, `***`} from secret " "`%s`",
                    secret_property.name,
                    tags.get(ZENML_GROUP_KEY),
                )
                self.CLIENT.begin_delete_secret(secret_property.name).result()
