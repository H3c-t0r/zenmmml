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
"""Build configuration class."""

import hashlib
from typing import Dict, Optional

from pydantic import BaseModel

from zenml.config import DockerSettings


class BuildConfiguration(BaseModel):
    """Configuration of Docker builds.

    Attributes:
        key: The key to store the build.
        settings: Settings for the build.
        step_name: Name of the step for which this image will be built.
        entrypoint: Optional entrypoint for the image.
        extra_files: Extra files to include in the Docker image.
    """

    key: str
    settings: DockerSettings
    step_name: Optional[str] = None
    entrypoint: Optional[str] = None
    extra_files: Dict[str, str] = {}

    @property
    def settings_checksum(self) -> str:
        """Checksum for all build settings.

        Returns:
            The checksum.
        """
        hash_ = hashlib.md5()
        hash_.update(self.settings.json().encode())
        if self.entrypoint:
            hash_.update(self.entrypoint.encode())

        for destination, source in self.extra_files.items():
            hash_.update(destination.encode())
            hash_.update(source.encode())

        return hash_.hexdigest()
