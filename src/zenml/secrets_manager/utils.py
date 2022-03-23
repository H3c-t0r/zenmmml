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
import base64
from zenml import secret
from zenml.secret.base_secret import BaseSecretSchema
from zenml.constants import ZENML_SCHEMA_NAME
from typing import Any, List, Optional, Dict


def encode_string(string: str) -> str:
    """Base64 encode a string.

    Args:
        string: String to encode
    """
    encoded_bytes = base64.b64encode(string.encode("utf-8"))
    return str(encoded_bytes, "utf-8")


def encode_secret(secret: BaseSecretSchema) -> Dict[str, str]:
    """Base64 encode all values within a secret.

    Args:
        secret: Secret containing key-value pairs
    """
    encoded_secret = {k: encode_string(v) for k, v in secret.content.items()}
    encoded_secret[ZENML_SCHEMA_NAME] = secret.type.value
    return encoded_secret


def decode_string(string: str) -> str:
    """Base64 decode a string.

    Args:
        string: String to decode
    """
    decoded_bytes = base64.b64decode(string)
    return str(decoded_bytes, "utf-8")


def decode_secret_dict(secret_dict: Dict[str, str]) -> Dict[str, str]:
    """Base64 decode a Secret.

    Args:
        secret_dict: dict containing key-value pairs to decode
    """
    zenml_schema_name = secret_dict.pop(ZENML_SCHEMA_NAME)

    decoded_secret = {k: decode_string(v) for k, v in secret_dict.items()}
    return decoded_secret, zenml_schema_name
