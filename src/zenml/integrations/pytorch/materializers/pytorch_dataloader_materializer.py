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
"""Implementation of the PyTorch DataLoader materializer."""

from typing import TYPE_CHECKING, Any, ClassVar, Dict, Tuple, Type

from torch.utils.data.dataloader import DataLoader

from zenml.enums import ArtifactType
from zenml.integrations.pytorch.materializers.base_pytorch_materializer import (
    BasePyTorchMaterliazer,
)

if TYPE_CHECKING:
    from zenml.metadata.metadata_types import MetadataType

DEFAULT_FILENAME = "entire_dataloader.pt"


class PyTorchDataLoaderMaterializer(BasePyTorchMaterliazer):
    """Materializer to read/write PyTorch dataloaders."""

    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (DataLoader,)
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA
    FILENAME: ClassVar[str] = DEFAULT_FILENAME

    def extract_metadata(self, dataloader: Any) -> Dict[str, "MetadataType"]:
        """Extract metadata from the given `DataLoader` object.

        Args:
            dataloader: The `DataLoader` object to extract metadata from.

        Returns:
            The extracted metadata as a dictionary.
        """
        metadata = super().extract_metadata(dataloader)
        metadata["num_samples"] = len(dataloader.dataset)
        metadata["batch_size"] = dataloader.batch_size
        metadata["num_batches"] = len(dataloader)
        return metadata
