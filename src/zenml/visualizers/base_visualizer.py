#  Copyright (c) ZenML GmbH 2021. All Rights Reserved.
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
"""Implementation of the base class for all ZenML visualizers."""

from abc import abstractmethod
from typing import Any

from zenml.logger import get_logger

logger = get_logger(__name__)


class BaseVisualizer:
    """Base class for all ZenML Visualizers."""

    def __init__(self) -> None:
        """Initializes the BaseVisualizer."""
        super().__init__()
        logger.warning(
            "Visualizers are deprecated and will be removed in a future "
            "release. Please view your data in the ZenML dashboard instead. "
            "To visualize artifacts within Jupyter notebooks, use the post "
            "execution `output.visualize()` method as described here: "
            "https://docs.zenml.io/starter-guide/pipelines/fetching-pipelines#visualizing-artifacts."
        )

    @abstractmethod
    def visualize(self, object: Any, *args: Any, **kwargs: Any) -> None:
        """Method to visualize objects.

        Args:
            object: The object to visualize.
            *args: Additional arguments.
            **kwargs: Additional keyword arguments.
        """
